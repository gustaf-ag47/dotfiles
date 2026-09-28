import importlib.machinery
import importlib.util
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[2] / 'bin/claude-token-proxy'
LOADER = importlib.machinery.SourceFileLoader('proxy_observability_subject', str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
proxy = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(proxy)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        proxy.SAMPLES.clear()

    def test_bounds_and_window_reset(self):
        tok = proxy.Tok('sk-ant-oat-test')
        tok.u5 = .2
        tok.u5_reset = '2099-01-01T00:00:00+00:00'
        for _ in range(220):
            proxy.record_sample(tok)
        self.assertEqual(len(proxy.SAMPLES[tok.fp]['5h']), 200)
        tok.u5_reset = '2000-01-01T00:00:00+00:00'
        proxy.record_sample(tok)
        self.assertEqual(len(proxy.SAMPLES[tok.fp]['5h']), 1)

    def test_forecast_outcomes(self):
        now = 100000
        self.assertEqual(proxy.forecast([], .2, now + 3600, now)['forecast'], 'unknown')
        self.assertEqual(proxy.forecast([[now-3600, .1], [now, .2]], .2, now+3600, now)['forecast'], 'waste')
        exhaust = proxy.forecast([[now-3600, .5], [now, .8]], .8, now+7200, now)
        self.assertEqual(exhaust['forecast'], 'exhaust')
        self.assertEqual(exhaust['exhaust_at'], now+2400)
        self.assertEqual(proxy.forecast([[now-3600, .7], [now, .8]], .8, now+3600, now)['forecast'], 'on_track')

    def test_codex_refresh_samples_enable_forecast(self):
        now = 2_000_000
        result = {'status': 'ok', 'windows': [{'name': 'primary_window', 'used_percent': 50,
                  'reset_at': now + 100_000}]}
        with patch.object(proxy, 'read_auth', return_value={}), \
             patch.object(proxy, 'safe_query', return_value=result), \
             patch.object(proxy, 'save_usage_state', return_value=True), \
             patch.object(proxy.time, 'time', return_value=now):
            proxy.refresh_providers()
        series = proxy.SAMPLES['codex:primary_window']['primary_window']
        self.assertEqual(series, [[now, .5]])
        proxy.record_external_sample('codex:primary_window', 'primary_window', .7, now+100_000, now+3600)
        provider_forecast = proxy.forecast(series + [[now+3600, .7]], .7, now+100_000, now+3600)
        self.assertEqual(provider_forecast['forecast'], 'exhaust')

    def test_log_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            proxy.CONTROL_DIR = Path(directory)
            proxy.ROUTING_LOG = proxy.CONTROL_DIR / 'routing.log'
            proxy.ROUTING_LOG.write_text('x' * 1_000_001)
            proxy.append_route({'ts': 'now', 'reason': 'test'})
            self.assertTrue(proxy.ROUTING_LOG.with_suffix('.log.1').exists())
            self.assertEqual(proxy.recent_routes()[-1]['reason'], 'test')


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_event_rejects_non_json_and_malformed_json(self):
        for body, kind in ((b'{', 'application/json'), (b'{}', 'text/plain')):
            req = urllib.request.Request(self.url + '/_event', data=body, headers={'Content-Type': kind})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            self.assertEqual(error.exception.code, 400)

    def test_usage_exposes_observability_fields(self):
        with urllib.request.urlopen(self.url + '/_usage') as response:
            payload = json.load(response)
        self.assertIn('forecast', payload['routing'])
        self.assertIn('recent', payload['routing'])
        self.assertIn('forecast', payload['providers']['openai-codex'])
