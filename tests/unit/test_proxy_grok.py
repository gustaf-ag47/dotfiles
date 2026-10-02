"""grok-build adapter tests for bin/claude-token-proxy's cross-provider quota oracle.

Offline and credential-free: every network call is mocked via `proxy.get_json`,
the OAuth credential is an in-memory dict (never a real ~/.pi/agent/auth.json or
~/.grok/auth.json), and ProxyIsolationMixin redirects CONTROL_DIR/USAGE_STATE_FILE
to a temp directory so no real cache is ever written. `GrokCliBridgeIntegrationTests`
points `GROK_OAUTH_BRIDGE` at a throwaway script under a temp dir and sets a temp
`GROK_HOME`, genuinely exercising the real subprocess path rather than mocking it
away -- isolation there comes from the temp paths, not from stubbed functionality.
"""
import base64
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
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
    def test_no_credential_falls_back_to_cli_seam_and_reports_its_reason(self):
        with patch.object(proxy, 'get_json') as fetch, \
                patch.object(proxy, 'grok_cli_fallback_token', return_value=(None, 'no cli session')) as cli:
            result = proxy.grok_build({})
        fetch.assert_not_called()
        cli.assert_called_once_with()
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'no cli session'})

    def test_expired_pi_oauth_does_not_refresh_request_or_fall_back_to_cli(self):
        auth = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': 1}}
        with patch.object(proxy, 'get_json') as fetch, patch.object(proxy, 'grok_cli_fallback_token') as cli:
            result = proxy.grok_build(auth)
        fetch.assert_not_called()
        cli.assert_not_called()
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


class GrokCliFallbackTests(unittest.TestCase):
    """Isolated tests for the `grok_build_token` decision logic (mocked seam).
    Real subprocess behavior is covered in `GrokCliBridgeIntegrationTests`.
    """

    def test_present_valid_pi_credential_skips_the_cli_fallback_entirely(self):
        with patch.object(proxy, 'grok_cli_fallback_token') as cli:
            access, email, source, error = proxy.grok_build_token(GROK_AUTH)
        cli.assert_not_called()
        self.assertEqual((access, email, source, error), (GROK_JWT, 'proxy-grok@example.test', 'pi-auth.json', None))

    def test_absent_pi_credential_uses_the_cli_fallback_token(self):
        cli_jwt = fake_jwt({'email': 'cli-session@example.test'}, canary='CLICANARY')
        with patch.object(proxy, 'grok_cli_fallback_token', return_value=(cli_jwt, None)) as cli:
            access, email, source, error = proxy.grok_build_token({})
        cli.assert_called_once_with()
        self.assertEqual((access, email, source, error), (cli_jwt, 'cli-session@example.test', 'grok-cli-session', None))

    def test_cli_fallback_token_feeds_the_real_quota_request(self):
        cli_jwt = fake_jwt({'email': 'cli-session@example.test'}, canary='CLICANARY2')
        with patch.object(proxy, 'grok_cli_fallback_token', return_value=(cli_jwt, None)), \
                patch.object(proxy, 'get_json', side_effect=[user_payload(email='cli-session@example.test'),
                                                              billing_payload()]) as fetch:
            result = proxy.grok_build({})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['credential_source'], 'grok-cli-session')
        self.assertEqual(fetch.call_args_list[0].args[1]['Authorization'], 'Bearer ' + cli_jwt)
        self.assertNotIn('CLICANARY2', json.dumps(result))


class GrokCliBridgeIntegrationTests(unittest.TestCase):
    """Exercises the real `grok_cli_fallback_token` subprocess/file-reading
    path against a temp `GROK_HOME`, with `GROK_OAUTH_BRIDGE` pointed at a
    throwaway bridge script under a temp directory -- nothing mocked. The
    script re-implements the sibling feat/grok-pi-auth contract (fixed entry
    key, auth_mode == "oidc", expires_at skew, bare token on stdout or
    non-zero exit) as a test double for this file's own subprocess-plumbing
    assertions; it is not shipped by the adapter.
    """

    BRIDGE_SOURCE = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
home = Path(os.environ.get("GROK_HOME") or os.path.expanduser("~/.grok"))
try:
    data = json.loads((home / "auth.json").read_text())
except (OSError, ValueError):
    sys.exit("no auth file")
entry = data.get("https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828")
if not isinstance(entry, dict) or entry.get("auth_mode") != "oidc" or not entry.get("key"):
    sys.exit("no session")
expires = entry.get("expires_at")
if isinstance(expires, (int, float)) and expires <= time.time():
    sys.exit("expired")
print(entry["key"])
'''

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.grok_home = root / 'grok-home'
        self.grok_home.mkdir()
        self.bridge = root / 'bridge.py'
        self.bridge.write_text(self.BRIDGE_SOURCE)
        self.bridge.chmod(self.bridge.stat().st_mode | stat.S_IEXEC)

    def write_auth(self, **entry_overrides):
        entry = {'key': 'cli-session-token-value', 'auth_mode': 'oidc'}
        entry.update(entry_overrides)
        (self.grok_home / 'auth.json').write_text(json.dumps(
            {'https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828': entry}))

    def call(self):
        with patch.dict(os.environ, {'GROK_HOME': str(self.grok_home), 'GROK_OAUTH_BRIDGE': str(self.bridge)}):
            return proxy.grok_cli_fallback_token()

    def test_real_session_in_a_temp_home_yields_the_token(self):
        self.write_auth()
        token, reason = self.call()
        self.assertEqual(token, 'cli-session-token-value')
        self.assertIsNone(reason)

    def test_missing_auth_file_in_temp_home_is_a_clean_failure(self):
        token, reason = self.call()
        self.assertIsNone(token)
        self.assertTrue(reason)
        self.assertNotIn('Traceback', reason)

    def test_expired_session_in_temp_home_is_not_treated_as_a_token(self):
        self.write_auth(expires_at=time.time() - 3600)
        token, reason = self.call()
        self.assertIsNone(token)

    def test_bridge_script_absent_is_unavailable_not_an_exception(self):
        missing = Path(self.tmp.name) / 'does-not-exist.py'
        with patch.dict(os.environ, {'GROK_HOME': str(self.grok_home), 'GROK_OAUTH_BRIDGE': str(missing)}):
            token, reason = proxy.grok_cli_fallback_token()
        self.assertIsNone(token)
        self.assertTrue(reason)

    DEFAULT_BRIDGE = Path(__file__).resolve().parents[2] / 'bin' / 'grok-oauth-token'

    @unittest.skipUnless(DEFAULT_BRIDGE.exists(),
                         'sibling feat/grok-pi-auth bridge not merged into this branch yet')
    def test_default_bridge_path_resolves_to_the_merged_sibling_script(self):
        with patch.dict(os.environ, {'GROK_OAUTH_BRIDGE': ''}, clear=False):
            self.assertEqual(proxy.grok_cli_bridge_path(), self.DEFAULT_BRIDGE)

    def test_full_adapter_path_through_the_real_bridge_and_temp_home(self):
        self.write_auth(key=GROK_JWT)
        with patch.dict(os.environ, {'GROK_HOME': str(self.grok_home), 'GROK_OAUTH_BRIDGE': str(self.bridge)}), \
                patch.object(proxy, 'get_json', side_effect=[user_payload(), billing_payload()]) as fetch:
            result = proxy.grok_build({})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['credential_source'], 'grok-cli-session')
        self.assertEqual(fetch.call_args_list[0].args[1]['Authorization'], 'Bearer ' + GROK_JWT)


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
