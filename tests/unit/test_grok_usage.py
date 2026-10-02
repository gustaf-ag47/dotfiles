"""grok-build adapter tests for scripts/llm_usage.py.

Offline and credential-free: every network call is mocked via `usage.get_json`,
and the Grok OAuth credential always comes from an in-memory `auth` dict rather
than any real file, so these tests never touch a real ~/.grok/auth.json or
~/.pi/agent/auth.json, make no live requests, and write no real cache files.
"""
import base64
import importlib.util
import json
from pathlib import Path
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

    def test_no_credential_is_unavailable_without_any_request(self):
        with patch.object(usage, 'get_json') as fetch:
            result = usage.grok_build({})
        fetch.assert_not_called()
        self.assertEqual(result, {'status': 'unavailable', 'reason': 'Log in to grok-build in Pi.'})

    def test_non_oauth_credential_is_unavailable(self):
        with patch.object(usage, 'get_json') as fetch:
            result = usage.grok_build({'grok-build': {'type': 'api_key', 'key': 'x'}})
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'unavailable')

    def test_expired_oauth_does_not_refresh_or_request(self):
        auth = {'grok-build': {'type': 'oauth', 'access': GROK_JWT, 'expires': 1}}
        with patch.object(usage, 'get_json') as fetch:
            result = usage.grok_build(auth)
        fetch.assert_not_called()
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
        (2026-10-02, docs/research/grok-usage-implementation.md): this account's
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
