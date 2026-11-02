import json
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import threading
import urllib.request
from unittest.mock import Mock
import unittest
from unittest.mock import patch
from tests.unit._helpers import load_script
from tests.unit.proxy_fixture import ProxyIsolationMixin

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('inspector_proxy_subject', str(ROOT / 'bin/claude-token-proxy'))
proxy = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(proxy)
inspector = load_script('inspector_cli_subject', ROOT / 'scripts/llm_inspector.py')


class SnapshotTests(ProxyIsolationMixin, unittest.TestCase):
    proxy = proxy

    def setUp(self):
        super().setUp()
        proxy.SERVED.clear()
        proxy.CONFIG_META.clear()
        proxy.INSPECT_EVENTS.clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        directory = Path(self.directory.name)
        self.routes = directory / 'routes.json'
        self.classes = directory / 'classes.json'
        self.routes.write_text(json.dumps({'claude-opus-5-5': [['openai-codex', 'gpt-test']]}))
        self.classes.write_text(json.dumps({'interactive': {'routes': [['anthropic', 'claude-opus-5-5']]}}))
        for key, value in {'ROUTES_FILE': self.routes, 'CLASSES_FILE': self.classes,
                           'ROUTES_MTIME': None, 'CLASSES_MTIME': None,
                           'ROUTES': {}, 'CLASSES': {}}.items():
            p = patch.object(proxy, key, value); p.start(); self.addCleanup(p.stop)
        self.token = proxy.Tok('sk-ant-oat-test-secret')
        self.token.label = 'test@example.test'
        self.token.u7 = .36
        self.token.u7_reset = '2099-01-01T00:00:00Z'
        self.token.header_observed_at['u7'] = 1000
        proxy.STATE[:] = [self.token]

    def test_snapshot_is_read_only_and_preserves_observation_age(self):
        with patch.object(proxy, 'upstream', side_effect=AssertionError('no network')), \
             patch.object(proxy, 'probe', side_effect=AssertionError('no model probes')), \
             patch.object(proxy, 'read_auth', side_effect=AssertionError('no credential reads')):
            result = proxy.inspector_payload()
        self.assertEqual(result['schema'], 'llm-inspector.v1')
        window = result['accounts'][0]['windows'][1]
        self.assertEqual(window['remaining_percent'], 64)
        self.assertEqual(window['observed_at'], 1000)
        self.assertNotIn(self.token.token, json.dumps(result))
        self.assertIsNone(result['session']['last_served'])
        self.assertEqual(result['routing']['account_preview']['would_pick'], self.token.fp)

    def test_attribution_is_session_scoped_and_only_records_acceptance(self):
        proxy.record_served('a', self.token, 'claude-opus-5-5', 401)
        self.assertFalse(proxy.SERVED)
        proxy.record_served('a', self.token, 'claude-opus-5-5', 200)
        row = proxy.inspector_payload(session='a')['session']['last_served']
        self.assertEqual(row['account'], self.token.fp)
        self.assertIn('completion not tracked', row['evidence'])
        self.assertIsNone(proxy.inspector_payload(session='b')['session']['last_served'])
        self.assertNotIn('a', proxy.SERVED)

    def test_attribution_bounded_and_expires(self):
        for i in range(1005): proxy.record_served(str(i), self.token, 'model', 200)
        self.assertEqual(len(proxy.SERVED), 1000)
        with patch.object(proxy.time, 'time', return_value=10**11):
            self.assertIsNone(proxy.inspector_payload(session='1004')['session']['last_served'])

    def test_bad_config_keeps_loaded_revision_and_reports_disk_revision(self):
        original = proxy.inspector_payload()['config']['tables']['routes']['loaded_revision']
        self.routes.write_text('{invalid')
        proxy.ROUTES_MTIME = None
        result = proxy.inspector_payload()
        config = result['config']['tables']['routes']
        self.assertEqual(config['loaded_revision'], original)
        self.assertNotEqual(config['disk_revision'], original)
        self.assertTrue(config['pending'])
        self.assertTrue(result['config']['routes'])
        self.assertEqual(config['error'], 'JSONDecodeError')

    def test_class_ceiling_validation_preserves_last_good_policy(self):
        proxy.inspector_payload()
        self.classes.write_text(json.dumps({'interactive': {'ceiling': {'anthropic': {'oi_max_used': 'bad'}}}}))
        proxy.CLASSES_MTIME = None
        result = proxy.inspector_payload()
        self.assertTrue(result['config']['tables']['classes']['pending'])
        self.assertEqual(result['config']['classes']['interactive']['routes'][0][0], 'anthropic')

    def test_expired_quota_is_unknown(self):
        self.token.u7_reset = '2000-01-01T00:00:00Z'
        self.assertIsNone(proxy.inspector_payload()['accounts'][0]['windows'][1]['remaining_percent'])

    def test_http_endpoint_is_loopback_and_never_forwards(self):
        server = proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(proxy, 'upstream', side_effect=AssertionError('must not forward')):
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/_inspect?session=pi-test') as response:
                    data = json.load(response)
                self.assertEqual(data['schema'], 'llm-inspector.v1')
                self.assertIsNone(data['session']['last_served'])
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=2)
        handler = object.__new__(proxy.Handler)
        handler.path = '/_inspect'
        handler.client_address = ('192.0.2.1', 1)
        handler._send_json = Mock()
        handler.do_GET()
        self.assertEqual(handler._send_json.call_args.args[0], 403)

    def test_non_claude_model_has_no_account_prediction(self):
        result = proxy.inspector_payload(model='gpt-example')
        self.assertFalse(result['routing']['account_applicable'])
        self.assertIsNone(result['routing']['account_preview']['would_pick'])

    def test_snapshot_redacts_nested_strings_and_terminal_controls(self):
        self.token.label = 'sk-ant-oat-SECRET\x1b'
        result = proxy.inspector_payload()
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['accounts'][0]['label'], '[redacted]')

    def test_events_deduplicate_and_are_bounded_and_sanitized(self):
        proxy.inspect_event('auth', state='sk-ant-oat-secret\x1b[31m')
        proxy.inspect_event('auth', state='sk-ant-oat-secret\x1b[31m')
        self.assertEqual(proxy.INSPECT_EVENTS[-1]['count'], 2)
        self.assertNotIn('sk-ant', json.dumps(proxy.INSPECT_EVENTS))
        for i in range(120): proxy.inspect_event('test', number=i)
        self.assertEqual(len(proxy.INSPECT_EVENTS), 100)


class MonitorTests(unittest.TestCase):
    def snapshot(self):
        return {'schema': inspector.SCHEMA, 'accounts': [], 'routing': {}, 'config': {}, 'host': 'test'}

    def test_failure_preserves_old_data_and_fetch_time(self):
        m = inspector.Monitor('http://127.0.0.1:8788', 'model', 'interactive')
        with patch.object(inspector, 'local_snapshot', return_value=self.snapshot()): m.refresh()
        before = m.rows['local']['fetched_at']
        with patch.object(inspector, 'local_snapshot', side_effect=OSError()): m.refresh()
        self.assertEqual(m.rows['local']['fetched_at'], before)
        self.assertEqual(m.rows['local']['snapshot']['host'], 'test')
        self.assertIn('STALE', '\n'.join(inspector.render_monitor(m.rows, 'fleet')))

    def test_remote_target_cannot_inject_shell(self):
        for target in ['-oProxyCommand=evil', 'host; touch /tmp/bad', 'host$(evil)', 'user@host\ncommand']:
            with self.assertRaises(ValueError): inspector.remote_snapshot({'target': target}, 'model', 'class')

    def test_loopback_only(self):
        for url in ['https://example.com', 'http://example.com', 'http://a:b@localhost', 'http://localhost/path']:
            with self.assertRaises(ValueError): inspector.loopback_url(url)
        self.assertEqual(inspector.loopback_url('http://127.0.0.1:8788'), 'http://127.0.0.1:8788')

    def test_schema_checked(self):
        with self.assertRaises(ValueError): inspector.validate({'schema': 2})
        self.assertEqual(inspector.validate(self.snapshot())['host'], 'test')

    def test_fleet_configuration_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'fleet.json'
            p.write_text('{"hosts":[{"name":"local","target":"host"}]}')
            with self.assertRaises(ValueError): inspector.fleet_hosts(p)

    def test_control_characters_and_tokens_redacted(self):
        self.assertNotIn('\x1b', inspector.safe('\x1b[31m'))
        self.assertEqual(inspector.safe('sk-ant-oat-secret'), '[redacted]')


if __name__ == '__main__': unittest.main()
