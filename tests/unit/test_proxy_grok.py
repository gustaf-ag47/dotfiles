"""grok-build adapter tests for bin/claude-token-proxy's cross-provider quota oracle.

Offline and credential-free: every network call is mocked via `proxy.get_json`,
the OAuth credential is an in-memory dict (never a real ~/.pi/agent/auth.json or
~/.grok/auth.json), and ProxyIsolationMixin redirects CONTROL_DIR/USAGE_STATE_FILE
to a temp directory so no real cache is ever written.
"""
import base64
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import urllib.error

from tests.unit.proxy_fixture import ProxyIsolationMixin

PATH = Path(__file__).resolve().parents[2] / 'bin/claude-token-proxy'
LOADER = importlib.machinery.SourceFileLoader('proxy_grok_subject', str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
proxy = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(proxy)

NOW = time.time()


def fake_jwt(payload, canary='GROKPROXYCANARY'):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.{canary}"


GROK_JWT = fake_jwt({'email': 'proxy-grok@example.test', 'sub': 'user-PROXYSECRET'})
GROK_AUTH = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': (NOW + 600) * 1000}}


def billing_payload(**config_overrides):
    config = {'monthlyLimit': 100, 'used': 10, 'creditUsagePercent': 10,
              'currentPeriod': {'type': 'USAGE_PERIOD_TYPE_MONTHLY', 'end': '2099-01-01T00:00:00Z'}}
    config.update(config_overrides)
    return {'config': config}


def user_payload(**overrides):
    data = {'email': 'proxy-grok@example.test', 'subscriptionTier': 'SuperGrok'}
    data.update(overrides)
    return data


class GrokBuildAdapterTests(unittest.TestCase):
    def test_no_credential_is_unavailable_without_any_request(self):
        with patch.object(proxy, 'get_json') as fetch:
            result = proxy.grok_build({})
        fetch.assert_not_called()
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'Log in to grok-build in Pi.'})

    def test_expired_oauth_does_not_refresh_or_request(self):
        auth = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': 1}}
        with patch.object(proxy, 'get_json') as fetch:
            result = proxy.grok_build(auth)
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('proxy-grok@example.test', result['reason'])
        self.assertIn('never refreshes', result['reason'])

    def test_window_parses_and_headers_match_the_live_proven_shape(self):
        with patch.object(proxy, 'get_json', side_effect=[user_payload(), billing_payload()]) as fetch:
            result = proxy.grok_build(GROK_AUTH)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['account'], {'email': 'proxy-grok@example.test', 'plan': 'SuperGrok'})
        self.assertEqual(result['windows'][0]['used_percent'], 10)
        headers = fetch.call_args_list[0].args[1]
        self.assertEqual(headers['X-XAI-Token-Auth'], 'xai-grok-cli')
        self.assertEqual(headers['x-grok-client-identifier'], 'pi')
        self.assertEqual(headers['Authorization'], 'Bearer ' + GROK_JWT)
        self.assertNotIn('PROXYSECRET', json.dumps(result))

    def test_http_error_never_leaks_response_body(self):
        with patch.object(proxy, 'get_json', side_effect=urllib.error.HTTPError('u', 401, 'bad SECRETBODY', {}, None)):
            result = proxy.grok_build(GROK_AUTH)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('HTTP 401', result['reason'])
        self.assertNotIn('SECRETBODY', json.dumps(result))

    def test_unrecognized_schema_is_ok_with_unknown_percent_not_zero(self):
        with patch.object(proxy, 'get_json', side_effect=[{}, {'config': {}}]):
            result = proxy.grok_build(GROK_AUTH)
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['windows'][0]['used_percent'])


class ProviderRegistryTests(ProxyIsolationMixin, unittest.TestCase):
    proxy = proxy

    def test_grok_build_is_registered_in_the_cross_provider_oracle(self):
        self.assertIn('grok-build', proxy.PROVIDER_ADAPTERS)
        self.assertIs(proxy.PROVIDER_ADAPTERS['grok-build'], proxy.grok_build)
        self.assertIn('cli-chat-proxy.grok.com', proxy.PROVIDER_SOURCES['grok-build'])
        self.assertEqual(proxy.PROVIDER_CONFIDENCE['grok-build'], 'low')
        self.assertIn('grok-build', proxy.PROVIDER_STATE)

    def test_refresh_providers_reports_grok_without_touching_anthropic_routing(self):
        with patch.object(proxy, 'read_auth', return_value=GROK_AUTH), \
                patch.object(proxy, 'get_json', side_effect=[user_payload(), billing_payload(),
                                                              urllib.error.HTTPError('u', 401, 'x', {}, None),
                                                              urllib.error.HTTPError('u', 401, 'x', {}, None)]):
            proxy.refresh_providers()
        self.assertEqual(proxy.PROVIDER_STATE['grok-build']['status'], 'ok')
        self.assertIn('source', proxy.PROVIDER_STATE['grok-build'])

    def test_usage_endpoint_exposes_grok_build_under_providers(self):
        import threading
        import urllib.request

        server = proxy.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.object(proxy, 'read_auth', return_value=GROK_AUTH), \
                    patch.object(proxy, 'get_json', side_effect=[user_payload(), billing_payload()]):
                proxy.refresh_providers()
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/_usage') as response:
                payload = json.load(response)
            self.assertIn('grok-build', payload['providers'])
            self.assertEqual(payload['providers']['grok-build']['status'], 'ok')
            self.assertNotIn('PROXYSECRET', json.dumps(payload))
        finally:
            server.shutdown()
            server.server_close()

    def test_grok_failure_does_not_break_other_providers(self):
        def broken(_):
            raise ValueError('secret-grok-proxy-value')
        with patch.object(proxy, 'read_auth', return_value={}), \
                patch.dict(proxy.PROVIDER_ADAPTERS, {'grok-build': broken}):
            proxy.refresh_providers()
        self.assertEqual(proxy.PROVIDER_STATE['grok-build']['status'], 'unavailable')
        self.assertNotIn('secret-grok-proxy-value', json.dumps(proxy.PROVIDER_STATE))


if __name__ == '__main__':
    unittest.main()
