"""5h capacity, boundary routing and post-move burst ramp."""
import io
import json
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.unit.proxy_fixture import ProxyIsolationMixin
from scripts import llm_usage

proxy = SourceFileLoader('proxy_5h', str(Path(__file__).parents[2] / 'bin/claude-token-proxy')).load_module()


class CapacityTests(unittest.TestCase):
    def test_capacity_synthetic_usage(self):
        data = {'routing': {'active_sessions': 2}, 'tokens': [
            {'fp': 'a', 'u5': .2, 'forecast': {'5h': {'burn_per_hour': .2}}},
            {'fp': 'b', 'u5': .8, 'forecast': {'5h': {'burn_per_hour': .4}}},
            {'fp': 'c', 'u5': None, 'forecast': {'5h': {'burn_per_hour': None}}}]}
        result = llm_usage.capacity_report(data, 2)
        self.assertEqual(result['accounts'], {'a': 2, 'b': 0, 'c': 0})
        self.assertEqual(result['capacity'], 2)
        self.assertEqual(llm_usage.capacity_report({'tokens': data['tokens']}, 1)['capacity'], 2)
        self.assertEqual(llm_usage.capacity_report({'tokens': []})['capacity'], 0)
        with mock.patch.object(llm_usage, 'get_json', return_value=data), \
             mock.patch.object(sys, 'argv', ['llm-usage', '--capacity', '--json']), \
             mock.patch('sys.stdout', new_callable=io.StringIO) as output:
            llm_usage.main()
            self.assertEqual(json.loads(output.getvalue())['capacity'], 2)


class RoutingTests(ProxyIsolationMixin, unittest.TestCase):
    proxy = proxy

    def setUp(self):
        super().setUp()
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        proxy.RAMPS.clear()
        self.old_mode = proxy.PICK_MODE
        proxy.PICK_MODE = 'pressure'
        self.old_control = proxy.CONTROL_DIR
        self.tmp = TemporaryDirectory()
        proxy.CONTROL_DIR = Path(self.tmp.name)
        self.a, self.b = proxy.Tok('account-a'), proxy.Tok('account-b')
        reset = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        for t, u5 in ((self.a, .8), (self.b, .05)):
            t.u5, t.u5_reset, t.u7 = u5, reset, .02
            proxy.STATE.append(t)

    def tearDown(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        proxy.RAMPS.clear()
        proxy.PICK_MODE = self.old_mode
        proxy.CONTROL_DIR = self.old_control
        self.tmp.cleanup()

    def test_boundary_move_and_preview_parity(self):
        proxy.LAST_PICK[('s', 'base')] = (self.a.fp, time.time())
        self.assertEqual(proxy.rank_pool('claude-haiku-4-5', session_key='s', messages_len=8)['would_pick'], self.a.fp)
        self.assertIs(proxy.pick(model='claude-haiku-4-5', session_key='s', boundary=False), self.a)
        self.assertEqual(proxy.rank_pool('claude-haiku-4-5', session_key='s', messages_len=2)['would_pick'], self.b.fp)
        self.assertIs(proxy.pick(model='claude-haiku-4-5', session_key='s', boundary=True), self.b)
        self.assertEqual(proxy.usage_payload()['routing']['active_sessions'], 1)

    def test_ramp_third_waits_outside_picker_lock_then_expires(self):
        proxy.append_route({'from_fp': self.a.fp, 'to_fp': self.b.fp, 'reason': '5h'})
        started = threading.Event()
        release = threading.Event()
        running = 0
        guard = threading.Lock()
        observations = []

        def slow_upstream(*args):
            nonlocal running
            with guard:
                running += 1
                observations.append((time.monotonic(), proxy.LOCK.locked()))
                if running == 2:
                    started.set()
            release.wait(2)
            return None, None

        with mock.patch.object(proxy, 'upstream', side_effect=slow_upstream):
            threads = [threading.Thread(target=proxy.ramp_upstream, args=(self.b, 'POST', '/', {}, b'')) for _ in range(2)]
            for thread in threads:
                thread.start()
            self.assertTrue(started.wait(1))
            third = threading.Thread(target=proxy.ramp_upstream, args=(self.b, 'POST', '/', {}, b''))
            third.start()
            time.sleep(.1)
            self.assertEqual(len(observations), 2)
            self.assertTrue(proxy.LOCK.acquire(timeout=.1))
            proxy.LOCK.release()
            release.set()
            for thread in threads + [third]:
                thread.join(2)
            self.assertEqual(len(observations), 3)
            self.assertFalse(any(locked for _, locked in observations))
            with proxy.RAMP_LOCK:
                proxy.RAMPS[self.b.fp] = (time.time() - 1, threading.Semaphore(2))
            proxy.ramp_upstream(self.b, 'POST', '/', {}, b'')
            self.assertEqual(proxy.IN_FLIGHT[self.b.fp], 0)
