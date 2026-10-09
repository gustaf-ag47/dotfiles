"""grok-build adapter tests for scripts/llm_usage.py.

Offline and credential-free: every network call is mocked via `usage.get_json`,
and (for the isolated test classes) the Grok CLI fallback is mocked via the
explicit `usage.grok_cli_fallback_token` seam, so these tests never touch a
real ~/.pi/agent/auth.json, make no live requests, and write no real cache
files. `GrokCliBridgeIntegrationTests` is the deliberate exception: it points
`GROK_OAUTH_BRIDGE` at a throwaway script under a temp directory and sets a
temp `GROK_HOME`, so the real subprocess/stdout/exit-code plumbing in
`grok_cli_fallback_token` is genuinely exercised end to end -- isolation comes
from the temp paths, not from stubbing the functionality away.
"""
import base64
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

SPEC = importlib.util.spec_from_file_location('llm_usage', Path(__file__).resolve().parents[2] / 'scripts/llm_usage.py')
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def fake_jwt(payload, canary='GROKJWTCANARY'):
    segment = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=').decode()  # noqa: E731
    return f"{segment({'alg': 'RS256', 'typ': 'JWT'})}.{segment(payload)}.{canary}"


NOW = time.time()
GROK_JWT = fake_jwt({'email': 'grok@example.test', 'sub': 'user-SECRETSUBJECT'})
GROK_AUTH = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': (NOW + 600) * 1000}}


def billing_payload(**config_overrides):
    config = {'monthlyLimit': 100, 'used': 42, 'creditUsagePercent': 42,
              'currentPeriod': {'type': 'USAGE_PERIOD_TYPE_MONTHLY', 'end': '2099-01-01T00:00:00Z'}}
    config.update(config_overrides)
    return {'config': config}


def user_payload(**overrides):
    data = {'email': 'grok@example.test', 'subscriptionTier': 'SuperGrok'}
    data.update(overrides)
    return data


class GrokBuildAdapterTests(unittest.TestCase):
    def fetch(self, user, billing):
        with patch.object(usage, 'get_json', side_effect=[user, billing]) as fetch:
            result = usage.grok_build(GROK_AUTH)
        return result, fetch

    def test_no_credential_falls_back_to_cli_seam_and_reports_its_reason(self):
        # No Pi credential: grok_build must consult the explicit CLI fallback
        # seam (mocked here for isolation -- see GrokCliFallbackTests and
        # GrokCliBridgeIntegrationTests for the fallback's own behavior) and
        # never performs a quota request when that seam has no token either.
        with patch.object(usage, 'get_json') as fetch, \
                patch.object(usage, 'grok_cli_fallback_token', return_value=(None, 'no cli session')) as cli:
            result = usage.grok_build({})
        fetch.assert_not_called()
        cli.assert_called_once_with()
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'no cli session'})

    def test_non_oauth_credential_is_unavailable(self):
        with patch.object(usage, 'get_json') as fetch, \
                patch.object(usage, 'grok_cli_fallback_token', return_value=(None, 'no cli session')):
            result = usage.grok_build({'grok-build': {'type': 'api_key', 'key': 'x'}})
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'unavailable')

    def test_expired_pi_oauth_does_not_refresh_request_or_fall_back_to_cli(self):
        # A present-but-expired Pi credential is a deliberate Pi-side login,
        # not an absence of one: it must not silently swap to the CLI session.
        auth = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': 1}}
        with patch.object(usage, 'get_json') as fetch, patch.object(usage, 'grok_cli_fallback_token') as cli:
            result = usage.grok_build(auth)
        fetch.assert_not_called()
        cli.assert_not_called()
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('grok@example.test', result['reason'])
        self.assertIn('never refreshes', result['reason'])

    def test_monthly_window_and_headers_are_well_formed(self):
        result, fetch = self.fetch(user_payload(), billing_payload())
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['account'], {'email': 'grok@example.test', 'plan': 'SuperGrok'})
        self.assertEqual(result['windows'][0]['name'], 'monthly')
        self.assertEqual(result['windows'][0]['used_percent'], 42)
        self.assertEqual(result['windows'][0]['resets_at'], '2099-01-01T00:00:00Z')
        first_call_headers = fetch.call_args_list[0].args[1]
        self.assertEqual(first_call_headers['X-XAI-Token-Auth'], 'xai-grok-cli')
        self.assertEqual(first_call_headers['Authorization'], 'Bearer ' + GROK_JWT)
        self.assertIn(fetch.call_args_list[0].args[0], usage.GROK_BASE_URL + '/user?include=subscription')
        self.assertIn('/billing?format=credits', fetch.call_args_list[1].args[0])
        self.assertNotIn('SECRETSUBJECT', json.dumps(result))
        self.assertNotIn('GROKJWTCANARY', json.dumps(result))

    def test_weekly_period_is_labeled_weekly(self):
        result, _ = self.fetch(user_payload(), billing_payload(
            currentPeriod={'type': 'USAGE_PERIOD_TYPE_WEEKLY', 'end': '2099-02-01T00:00:00Z'}))
        self.assertEqual(result['windows'][0]['name'], 'weekly')

    def test_missing_used_percent_falls_back_to_ratio(self):
        result, _ = self.fetch(user_payload(), billing_payload(creditUsagePercent=None, used=25, monthlyLimit=50))
        self.assertEqual(result['windows'][0]['used_percent'], 50)

    def test_on_demand_cap_adds_a_second_window_only_when_positive(self):
        result, _ = self.fetch(user_payload(), billing_payload(onDemandCap=10))
        self.assertEqual(len(result['windows']), 2)
        self.assertEqual(result['windows'][1]['name'], 'on_demand_cap')
        result_zero, _ = self.fetch(user_payload(), billing_payload(onDemandCap=0))
        self.assertEqual(len(result_zero['windows']), 1)

    def test_unrecognized_schema_still_reports_a_monthly_window_with_unknown_percent(self):
        result, _ = self.fetch({'unexpected': 'shape'}, {'config': {}})
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['windows'][0]['used_percent'])
        self.assertIsNone(result['account']['plan'])

    def test_live_observed_billing_schema_without_monthly_fields_is_unknown_not_zero(self):
        """Redacted/sanitized shape of a real GET /v1/user and /v1/billing response
        (2026-10-02, operator notes: grok-usage-implementation.md): this account's
        billing config has no monthlyLimit/used/creditUsagePercent at all -- only
        currentPeriod, onDemandCap/onDemandUsed/prepaidBalance (each 0). The demi
        community adapter's fields were not present; the adapter must not invent
        a used_percent when the live schema simply omits it.
        """
        live_user = {'userId': 'id', 'email': 'grok@example.test', 'firstName': 'X', 'lastName': None,
                     'principalType': 'User', 'principalId': 'id', 'teamId': None, 'organizationId': None,
                     'codingDataRetentionOptOut': True, 'hasGrokCodeAccess': True, 'subscriptionTier': None}
        live_billing = {'config': {'currentPeriod': {'type': 'USAGE_PERIOD_TYPE_WEEKLY',
                                                      'start': '2026-10-01T00:00:00+00:00',
                                                      'end': '2026-10-08T00:00:00+00:00'},
                                   'onDemandCap': {'val': 0}, 'onDemandUsed': {'val': 0},
                                   'isUnifiedBillingUser': True, 'prepaidBalance': {'val': 0},
                                   'topUpMethod': 'card', 'billingPeriodStart': '2026-10-01T00:00:00+00:00',
                                   'billingPeriodEnd': '2026-10-08T00:00:00+00:00'}}
        result, _ = self.fetch(live_user, live_billing)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['account'], {'email': 'grok@example.test', 'plan': None})
        self.assertEqual(result['windows'], [{'name': 'weekly', 'used_percent': None, 'used': None,
                                              'limit': None, 'unit': 'credits',
                                              'resets_at': '2026-10-08T00:00:00+00:00'}])
        normalized = usage.normalize_provider('grok-build', result, NOW)
        self.assertEqual(normalized['quota']['windows'][0]['state'], 'unknown')
        self.assertIsNone(normalized['quota']['windows'][0]['remaining_percent'])

    def test_http_error_names_account_and_never_leaks_body(self):
        with patch.object(usage, 'get_json', side_effect=urllib.error.HTTPError('u', 401, 'bad body SECRET', {}, None)):
            result = usage.grok_build(GROK_AUTH)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('grok@example.test', result['reason'])
        self.assertIn('HTTP 401', result['reason'])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_money_dict_shape_is_unwrapped(self):
        result, _ = self.fetch(user_payload(), billing_payload(monthlyLimit={'val': 80, 'currencyCode': 'USD'},
                                                                used={'val': 16}, creditUsagePercent=None))
        self.assertEqual(result['windows'][0]['used_percent'], 20)

    def test_client_identifier_defaults_to_pi_and_is_overridable(self):
        with patch.dict(usage.os.environ, {'GROK_CLIENT_NAME': ''}, clear=False):
            _, fetch = self.fetch(user_payload(), billing_payload())
        self.assertEqual(fetch.call_args_list[0].args[1]['x-grok-client-identifier'], 'pi')
        with patch.dict(usage.os.environ, {'GROK_CLIENT_NAME': 'custom-client'}):
            _, fetch = self.fetch(user_payload(), billing_payload())
        self.assertEqual(fetch.call_args_list[0].args[1]['x-grok-client-identifier'], 'custom-client')


class GrokCliFallbackTests(unittest.TestCase):
    """Isolated tests for the explicit, mockable `grok_build_token` seam
    decision logic. The CLI fallback itself (`grok_cli_fallback_token`'s real
    subprocess/file behavior) is covered separately in
    `GrokCliBridgeIntegrationTests`.
    """

    def test_present_valid_pi_credential_skips_the_cli_fallback_entirely(self):
        with patch.object(usage, 'grok_cli_fallback_token') as cli:
            access, email, source, error = usage.grok_build_token(GROK_AUTH)
        cli.assert_not_called()
        self.assertEqual((access, email, source, error), (GROK_JWT, 'grok@example.test', 'pi-auth.json', None))

    def test_absent_pi_credential_uses_the_cli_fallback_token(self):
        cli_jwt = fake_jwt({'email': 'cli-session@example.test'}, canary='CLICANARY')
        with patch.object(usage, 'grok_cli_fallback_token', return_value=(cli_jwt, None)) as cli:
            access, email, source, error = usage.grok_build_token({})
        cli.assert_called_once_with()
        self.assertEqual((access, email, source, error), (cli_jwt, 'cli-session@example.test', 'grok-cli-session', None))

    def test_cli_fallback_failure_is_reported_without_a_quota_request(self):
        with patch.object(usage, 'get_json') as fetch, \
                patch.object(usage, 'grok_cli_fallback_token', return_value=(None, 'No Grok CLI session found.')):
            result = usage.grok_build({'grok-build': {'type': 'api_key', 'key': 'irrelevant'}})
        fetch.assert_not_called()
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'No Grok CLI session found.'})

    def test_cli_fallback_token_feeds_the_real_quota_request(self):
        cli_jwt = fake_jwt({'email': 'cli-session@example.test'}, canary='CLICANARY2')
        with patch.object(usage, 'grok_cli_fallback_token', return_value=(cli_jwt, None)), \
                patch.object(usage, 'get_json', side_effect=[user_payload(email='cli-session@example.test'),
                                                             billing_payload()]) as fetch:
            result = usage.grok_build({})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['credential_source'], 'grok-cli-session')
        self.assertEqual(fetch.call_args_list[0].args[1]['Authorization'], 'Bearer ' + cli_jwt)
        self.assertNotIn('CLICANARY2', json.dumps(result))


class GrokCliBridgeIntegrationTests(unittest.TestCase):
    """Exercises the real `grok_cli_fallback_token` subprocess/file-reading
    path against a temp `GROK_HOME`, with `GROK_OAUTH_BRIDGE` pointed at a
    throwaway bridge script under a temp directory. Nothing here is mocked:
    this is the "temp GROK_HOME/HOME" isolation the integration gap asked
    for, proving the seam's actual plumbing (argv, env passthrough, stdout
    capture, non-zero exit handling, timeout) rather than just its call
    signature.

    The throwaway script re-implements the sibling's documented, narrow
    contract (scripts/grok_oauth.py / operator notes: grok-pi-auth-implementation.md
    in the feat/grok-pi-auth worktree: fixed entry key, auth_mode == "oidc",
    expires_at skew, print bare token or exit non-zero) because that real
    script is owned by a sibling change not yet merged into this branch; it
    is a test double for *this test file's own* subprocess-integration
    assertions, not a copy shipped in the adapter.
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
            return usage.grok_cli_fallback_token()

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
        self.assertTrue(reason)

    def test_wrong_auth_mode_in_temp_home_is_rejected(self):
        self.write_auth(auth_mode='legacy')
        token, reason = self.call()
        self.assertIsNone(token)

    def test_bridge_script_absent_is_unavailable_not_an_exception(self):
        missing = Path(self.tmp.name) / 'does-not-exist.py'
        with patch.dict(os.environ, {'GROK_HOME': str(self.grok_home), 'GROK_OAUTH_BRIDGE': str(missing)}):
            token, reason = usage.grok_cli_fallback_token()
        self.assertIsNone(token)
        self.assertTrue(reason)

    DEFAULT_BRIDGE = Path(__file__).resolve().parents[2] / 'bin' / 'grok-oauth-token'

    @unittest.skipUnless(DEFAULT_BRIDGE.exists(),
                         'sibling feat/grok-pi-auth bridge not merged into this branch yet')
    def test_default_bridge_path_resolves_to_the_merged_sibling_script(self):
        """Once bin/grok-oauth-token (feat/grok-pi-auth) lands on this branch,
        the default (no GROK_OAUTH_BRIDGE override) path must find it -- the
        real coordination point between the two changes, not just the override
        env var used everywhere else in this file for isolation.
        """
        with patch.dict(os.environ, {'GROK_OAUTH_BRIDGE': ''}, clear=False):
            self.assertEqual(usage.grok_cli_bridge_path(), self.DEFAULT_BRIDGE)

    def test_full_adapter_path_through_the_real_bridge_and_temp_home(self):
        """End-to-end: no Pi credential, real subprocess reads a real (temp)
        GROK_HOME/auth.json, and the resulting token drives a (mocked) quota
        request -- the only remaining mock is the network call itself.
        """
        self.write_auth(key=GROK_JWT)
        with patch.dict(os.environ, {'GROK_HOME': str(self.grok_home), 'GROK_OAUTH_BRIDGE': str(self.bridge)}), \
                patch.object(usage, 'get_json', side_effect=[user_payload(), billing_payload()]) as fetch:
            result = usage.grok_build({})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['credential_source'], 'grok-cli-session')
        self.assertEqual(fetch.call_args_list[0].args[1]['Authorization'], 'Bearer ' + GROK_JWT)


class GrokBuildNormalizeAndRenderTests(unittest.TestCase):
    def test_normalized_projection_reports_known_window_and_remaining_percent(self):
        raw = {'status': 'ok', 'account': {'email': 'a@b', 'plan': 'SuperGrok'},
               'windows': [{'name': 'monthly', 'used_percent': 30, 'resets_at': '2099-01-01T00:00:00Z'}]}
        result = usage.normalize_provider('grok-build', raw, NOW)
        self.assertEqual(result['quota']['windows'][0]['used_percent'], 30)
        self.assertEqual(result['quota']['windows'][0]['remaining_percent'], 70)
        self.assertEqual(result['confidence'], 'low')
        self.assertNotIn('quota', result['unknowns'])

    def test_unknown_used_percent_is_explicitly_unknown_not_zero(self):
        raw = {'status': 'ok', 'account': {'email': 'a@b'},
               'windows': [{'name': 'monthly', 'used_percent': None, 'resets_at': None}]}
        result = usage.normalize_provider('grok-build', raw, NOW)
        self.assertEqual(result['quota']['windows'][0]['state'], 'unknown')
        self.assertIsNone(result['quota']['windows'][0]['remaining_percent'])

    def test_failed_observation_is_redacted_and_explicit(self):
        result = usage.normalize_provider('grok-build',
            {'status': 'unavailable', 'reason': 'Log in to grok-build in Pi.'}, NOW)
        self.assertEqual(result['confidence'], 'none')
        self.assertIn('quota', result['unknowns'])
        self.assertNotIn('access', json.dumps(result))

    def test_malformed_windows_payload_stays_unknown_not_zero(self):
        result = usage.normalize_provider('grok-build', {'status': 'ok', 'windows': None}, NOW)
        self.assertEqual(result['status'], 'ok')
        self.assertIn('quota', result['unknowns'])

    def test_adapter_is_registered_with_a_distinct_source_label(self):
        self.assertIn('grok-build', usage.ADAPTERS)
        self.assertIs(usage.ADAPTERS['grok-build'], usage.grok_build)
        self.assertIn('cli-chat-proxy.grok.com', usage.REPORT_SOURCES['grok-build'])

    def test_render_shows_identity_verdict_and_window_without_raising(self):
        info = {'status': 'ok', 'account': {'email': 'grok@example.test', 'plan': 'SuperGrok'},
                'windows': [{'name': 'monthly', 'used_percent': 10, 'resets_at': NOW + 3600}],
                'checked_at': int(NOW), 'normalized': usage.normalize_provider('grok-build', {
                    'status': 'ok', 'windows': [{'name': 'monthly', 'used_percent': 10, 'resets_at': NOW + 3600}]}, NOW)}
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render({'schema': 1, 'providers': {'grok-build': info}})
        self.assertIn('grok@example.test (SuperGrok)', out)
        self.assertIn('READY', out)
        self.assertIn('unofficial endpoint', out)

    def test_render_shows_unknown_verdict_when_every_window_is_unknown(self):
        info = {'status': 'ok', 'account': {'email': 'grok@example.test'},
                'windows': [{'name': 'monthly', 'used_percent': None, 'resets_at': None}],
                'checked_at': int(NOW), 'normalized': usage.normalize_provider('grok-build',
                    {'status': 'ok', 'windows': [{'name': 'monthly', 'used_percent': None}]}, NOW)}
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render({'schema': 1, 'providers': {'grok-build': info}})
        self.assertIn('UNKNOWN', out)

    def test_render_shows_failure_reason_without_raising(self):
        info = {'status': 'unavailable', 'reason': 'Log in to grok-build in Pi.', 'checked_at': int(NOW)}
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render({'schema': 1, 'providers': {'grok-build': info}})
        self.assertIn('Log in to grok-build in Pi.', out)

    def test_one_provider_failure_does_not_break_grok_or_leak(self):
        def broken(_):
            raise ValueError('secret-grok-value')
        with patch.dict(usage.ADAPTERS, {'grok-build': broken, 'deepseek': lambda _: {'status': 'ok'}}):
            result = usage.collect({}, ['grok-build', 'deepseek'])
        self.assertEqual(result['grok-build']['status'], 'unavailable')
        self.assertEqual(result['deepseek']['status'], 'ok')
        self.assertNotIn('secret-grok-value', str(result))


if __name__ == '__main__':
    unittest.main()
