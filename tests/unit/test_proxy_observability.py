import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

PATH = Path(__file__).resolve().parents[2] / 'bin/claude-token-proxy'
LOADER = importlib.machinery.SourceFileLoader('proxy_observability_subject', str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
proxy = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(proxy)


class LedgerTests(unittest.TestCase):
    def test_bound_and_reset_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            tok = proxy.Tok('sk-ant-oat-test')
            tok.u5 = .2
            tok.u5_reset = '2099-01-01T00:00:00+00:00'
            proxy.SAMPLES.clear()
            for _ in range(220):
                proxy.record_sample(tok)
            self.assertEqual(len(proxy.SAMPLES[tok.fp]['5h']), 200)
            tok.u5_reset = '2000-01-01T00:00:00+00:00'
            proxy.SAMPLES[tok.fp]['5h'] = [[1, .1]]
            proxy.record_sample(tok)
            self.assertEqual(len(proxy.SAMPLES[tok.fp]['5h']), 1)

    def test_forecast_outcomes(self):
        now = 100000
        self.assertEqual(proxy.forecast([], .2, now + 3600, now)['forecast'], 'unknown')
        waste = proxy.forecast([[now-3600, .1], [now, .2]], .2, now+3600, now)
        self.assertEqual(waste['forecast'], 'waste')
        exhaust = proxy.forecast([[now-3600, .5], [now, .8]], .8, now+7200, now)
        self.assertEqual(exhaust['forecast'], 'exhaust')
        self.assertEqual(exhaust['exhaust_at'], now+2400)
        self.assertEqual(proxy.forecast([[now-3600, .7], [now, .8]], .8, now+3600, now)['forecast'], 'on_track')

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
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_event_validates_json_and_shape(self):
        for body, content_type in ((b'{', 'application/json'), (b'{}', 'text/plain')):
            req = urllib.request.Request(self.url + '/_event', data=body, headers={'Content-Type': content_type})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            self.assertEqual(error.exception.code, 400)
        req = urllib.request.Request(self.url + '/_event', data=b'{"kind":"provider_switch"}', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

    def test_usage_includes_routing_observability_fields(self):
        with urllib.request.urlopen(self.url + '/_usage') as response:
            data = json.load(response)
        self.assertIn('forecast', data['routing'])
        self.assertIn('recent', data['routing'])
        self.assertIn('forecast', data['providers']['openai-codex'])
