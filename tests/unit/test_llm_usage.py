import base64
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import time

SPEC = importlib.util.spec_from_file_location('llm_usage', Path(__file__).resolve().parents[2] / 'scripts/llm_usage.py')
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def fake_jwt(payload):
    segment = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=').decode()  # noqa: E731
    return f"{segment({'alg': 'RS256', 'typ': 'JWT'})}.{segment(payload)}.not-a-signature"


JWT = fake_jwt({'https://api.openai.com/profile': {'email': 'a@b', 'name': 'A B'},
                'https://api.openai.com/auth': {'chatgpt_plan_type': 'plus', 'chatgpt_account_id': 'abcdef-1234-5678',
                                                'chatgpt_user_id': 'user-JWTSECRET'}})
NOW = time.time()
CODEX_AUTH = {'openai-codex': {'type': 'oauth', 'access': JWT, 'expires': (NOW + 600) * 1000, 'accountId': 'abcdef-1234-5678'}}


def wham_usage(**overrides):
    """Redacted copy of Appendix A (Pro, 7-day window exhausted, astra blocked)."""
    data = {'user_id': 'user-972WKYSECRET', 'account_id': 'abcdef-1234-5678', 'email': 'gs@example.test', 'plan_type': 'pro',
            'rate_limit': {'allowed': False, 'limit_reached': True,
                           'primary_window': {'used_percent': 100, 'limit_window_seconds': 604800,
                                              'reset_after_seconds': 456647, 'reset_at': NOW + 456647},
                           'secondary_window': None},
            'code_review_rate_limit': None, 'additional_rate_limits': None,
            'model_usage': {'gpt-6-astra': {'available': False, 'available_at': '2026-09-30T14:38:22.363903Z',
                                            'credits_would_enable': True}},
            'credits': {'has_credits': False, 'unlimited': False, 'overage_limit_reached': False, 'balance': '0',
                        'approx_local_messages': [0, 0], 'approx_cloud_messages': [0, 0]},
            'spend_control': {'reached': False, 'individual_limit': None},
            'rate_limit_reached_type': {'type': 'rate_limit_reached', 'details': 'default'},
            'rate_limit_upsell': {'banner_type': 'pro_rate_limit_reached', 'title': "You're out of Codex messages",
                                  'ctas': [{'action': 'add_credits', 'label': 'Add Credits'}], 'reset_at': 1790779102,
                                  'referral': 'REFERRALSECRET', 'request_url': None},
            'promo': None, 'rate_limit_reset_credits': {'available_count': 0, 'applicable_available_count': 0}}
    data.update(overrides)
    return data


DEEPSEEK_BALANCE_NEGATIVE = {'is_available': False, 'balance_infos': [
    {'currency': 'USD', 'total_balance': '-0.12', 'granted_balance': '0.00', 'topped_up_balance': '-0.12'}]}  # Appendix B


def report(provider, info):
    return {'schema': 1, 'providers': {provider: {**info, 'checked_at': int(NOW)}}}


class JwtClaimsTests(unittest.TestCase):
    def test_valid_token_yields_email_and_plan_only(self):
        self.assertEqual(usage.jwt_claims(JWT), {'email': 'a@b', 'name': 'A B', 'plan': 'plus'})
        self.assertNotIn('JWTSECRET', str(usage.jwt_claims(JWT)))

    def test_malformed_tokens_do_not_raise(self):
        for token in ('fake', 'a.b', 'a.b.c.d', 'x.!!!notbase64!!!.y', 'x.' + base64.urlsafe_b64encode(b'[1]').decode() + '.y',
                      'x.' + base64.urlsafe_b64encode(b'\xff\xfe').decode() + '.y', '', None):
            self.assertEqual(usage.jwt_claims(token), {}, token)

    def test_missing_claims_are_absent(self):
        self.assertEqual(usage.jwt_claims(fake_jwt({'sub': 'x'})), {})
        self.assertEqual(usage.jwt_claims(fake_jwt({'https://api.openai.com/profile': 'not-a-dict'})), {})
        self.assertEqual(usage.jwt_claims(fake_jwt({'https://api.openai.com/profile': {'email': 'a@b'}})), {'email': 'a@b'})


class CodexTests(unittest.TestCase):
    def fetch(self, data):
        with patch.object(usage, 'get_json', return_value=data) as fetch:
            result = usage.codex(CODEX_AUTH)
        return result, fetch

    def test_pro_exhausted_fixture(self):
        result, fetch = self.fetch(wham_usage())
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1]['ChatGPT-Account-Id'], 'abcdef-1234-5678')
        self.assertEqual(result['account'], {'email': 'gs@example.test', 'name': 'A B', 'plan': 'pro', 'account_id': 'abcdef'})
        self.assertEqual(result['windows'], [{'name': 'primary_window', 'used_percent': 100, 'window_seconds': 604800,
                                             'reset_at': NOW + 456647}])
        self.assertEqual(result['models'], {'gpt-6-astra': {'available': False, 'available_at': '2026-09-30T14:38:22.363903Z',
                                                            'credits_would_enable': True}})
        self.assertEqual(result['credits'], {'balance': '0', 'has_credits': False, 'unlimited': False, 'overage_limit_reached': False})
        self.assertEqual(result['reached_type'], 'rate_limit_reached')
        self.assertEqual(result['reset_credits'], 0)
        self.assertEqual(result['topup_url'], 'https://chatgpt.com/codex/settings/usage')
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', result))
        self.assertIn('gs@example.test (pro)  LIMIT REACHED', out)
        self.assertRegex(out, r'7d\s+░{20}\s+0% left\s+resets in 5d')
        self.assertIn('gpt-6-astra unavailable until', out)
        self.assertIn('credits would unlock it (balance 0)', out)
        self.assertIn('top up: https://chatgpt.com/codex/settings/usage   reset credits: 0', out)

    def test_plus_5h_and_7d_windows_ready(self):
        data = wham_usage(plan_type='plus', model_usage={}, rate_limit={
            'allowed': True, 'limit_reached': False,
            'primary_window': {'used_percent': 12, 'limit_window_seconds': 18000, 'reset_at': NOW + 3600},
            'secondary_window': {'used_percent': 40, 'limit_window_seconds': 604800, 'reset_at': NOW + 86400 * 3}})
        result, _ = self.fetch(data)
        self.assertEqual([w['name'] for w in result['windows']], ['primary_window', 'secondary_window'])
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', result))
        self.assertIn('gs@example.test (plus)  READY', out)
        self.assertRegex(out, r'\n    5h\s+\S+\s+88% left')
        self.assertRegex(out, r'\n    7d\s+\S+\s+60% left')
        self.assertNotIn('top up', out)
        self.assertNotIn('unavailable', out)

    def test_additional_rate_limits_become_named_windows(self):
        data = wham_usage(additional_rate_limits=[{'limit_name': 'codex-spark', 'metered_feature': 'spark', 'rate_limit': {
            'primary_window': {'used_percent': 40, 'limit_window_seconds': 18000, 'reset_at': NOW + 600}}}, 'junk', {}])
        result, _ = self.fetch(data)
        self.assertEqual(result['windows'][1], {'name': 'codex-spark', 'used_percent': 40, 'window_seconds': 18000,
                                                'reset_at': NOW + 600})
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', result))
        self.assertRegex(out, r'codex-spark 5h\s+\S+\s+60% left')

    def test_credits_fund_overage_variant(self):
        data = wham_usage(credits={'has_credits': True, 'unlimited': False, 'overage_limit_reached': False, 'balance': '12.50'})
        result, _ = self.fetch(data)
        self.assertTrue(usage.codex_on_credits(result))
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', result))
        self.assertIn('LIMIT REACHED · running on credits', out)
        self.assertIn('(balance 12.50)', out)

    def test_credits_and_model_usage_absent_are_not_zero(self):
        data = wham_usage()
        for key in ('model_usage', 'credits', 'rate_limit_reached_type', 'rate_limit_upsell', 'rate_limit_reset_credits',
                    'email', 'plan_type'):
            del data[key]
        result, _ = self.fetch(data)
        self.assertEqual(result['models'], {})
        self.assertEqual(result['credits'], {'balance': None, 'has_credits': None, 'unlimited': None, 'overage_limit_reached': None})
        self.assertIsNone(result['reset_credits'])
        self.assertIsNone(result['reached_type'])
        self.assertEqual((result['account']['email'], result['account']['plan']), ('a@b', 'plus'))  # JWT fallback
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', result))
        self.assertIn('a@b (plus)  LIMIT REACHED', out)
        self.assertNotIn('reset credits', out)
        self.assertNotIn('balance', out)

    def test_result_never_carries_ids_or_referral(self):
        result, _ = self.fetch(wham_usage())
        blob = json.dumps(result)
        for secret in ('user-972WKYSECRET', 'abcdef-1234-5678', 'REFERRALSECRET', 'JWTSECRET', 'approx_local_messages',
                       JWT.split('.')[1]):
            self.assertNotIn(secret, blob)
        self.assertIn('"account_id": "abcdef"', blob)

    def test_http_error_still_names_account_and_never_refreshes(self):
        error = urllib.error.HTTPError('https://chatgpt.com/backend-api/wham/usage', 401, 'Unauthorized', {}, None)
        self.addCleanup(error.close)
        with patch.object(usage, 'get_json', side_effect=error) as fetch:
            result = usage.codex(CODEX_AUTH)
        fetch.assert_called_once()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['account']['email'], 'a@b')
        self.assertIn('HTTP 401', result['reason'])
        self.assertIn('a@b', result['reason'])
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('openai-codex', {**result}))
        self.assertIn('openai-codex  a@b (plus)  Usage endpoint HTTP 401', out)

    def test_expired_token_names_account_without_network(self):
        with patch.object(usage, 'get_json') as fetch:
            result = usage.codex({'openai-codex': {'type': 'oauth', 'access': JWT, 'expires': 1}})
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('OAuth for a@b expired', result['reason'])

    def test_malformed_jwt_keeps_adapter_working(self):
        auth = {'openai-codex': {'type': 'oauth', 'access': 'not.a-jwt', 'expires': (NOW + 600) * 1000}}
        with patch.object(usage, 'get_json', return_value=wham_usage(email=None, plan_type=None)):
            result = usage.codex(auth)
        self.assertEqual(result['status'], 'ok')
        self.assertIsNone(result['account']['email'])
        self.assertIsNone(result['account']['account_id'])
        with patch.object(usage, 'use_color', return_value=False):
            self.assertIn('  ?  LIMIT REACHED', usage.render(report('openai-codex', result)))


class DeepseekTests(unittest.TestCase):
    KEY = 'sk-PREFIXSECRET-wxyz'

    def test_label_precedence_env_then_auth_then_key_suffix(self):
        stored = {'deepseek': {'type': 'api_key', 'key': self.KEY, 'label': 'stored@example.test'}}
        with patch.dict(usage.os.environ, {'DEEPSEEK_ACCOUNT_LABEL': 'env@example.test'}):
            self.assertEqual(usage.deepseek_label(stored, self.KEY), ('env@example.test', 'env'))
        with patch.dict(usage.os.environ, {'DEEPSEEK_ACCOUNT_LABEL': ''}):
            self.assertEqual(usage.deepseek_label(stored, self.KEY), ('stored@example.test', 'auth.json'))
            self.assertEqual(usage.deepseek_label({'deepseek': {'type': 'api_key', 'key': self.KEY}}, self.KEY), ('key …wxyz', 'key'))
            self.assertEqual(usage.deepseek_label({}, self.KEY), ('key …wxyz', 'key'))

    def test_negative_balance_renders_unavailable_and_topup(self):
        auth = {'deepseek': {'type': 'api_key', 'key': self.KEY}}
        with patch.dict(usage.os.environ, {'DEEPSEEK_ACCOUNT_LABEL': ''}), \
                patch.object(usage, 'get_json', return_value=DEEPSEEK_BALANCE_NEGATIVE) as fetch:
            result = usage.deepseek(auth)
        self.assertEqual(fetch.call_args.args[0], 'https://api.deepseek.com/user/balance')
        self.assertEqual(result['label'], 'key …wxyz')
        self.assertIs(result['available'], False)
        self.assertEqual(result['topup_url'], 'https://platform.deepseek.com/top_up')
        self.assertNotIn('PREFIXSECRET', json.dumps(result))
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('deepseek', result))
        self.assertIn('key …wxyz  EXHAUSTED', out)
        self.assertIn('balance -0.12 USD   UNAVAILABLE   (granted 0.00 · topped-up -0.12)', out)
        self.assertIn('top up: https://platform.deepseek.com/top_up', out)
        self.assertIn('set DEEPSEEK_ACCOUNT_LABEL', out)
        self.assertNotIn('PREFIXSECRET', out)

    def test_positive_balance_renders_ready_without_hints(self):
        auth = {'deepseek': {'type': 'api_key', 'key': self.KEY, 'label': 'gs@example.test'}}
        data = {'is_available': True, 'balance_infos': [{'currency': 'USD', 'total_balance': '4.20', 'granted_balance': '0.00',
                                                         'topped_up_balance': '4.20'}]}
        with patch.dict(usage.os.environ, {'DEEPSEEK_ACCOUNT_LABEL': ''}), patch.object(usage, 'get_json', return_value=data):
            result = usage.deepseek(auth)
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('deepseek', result))
        self.assertIn('gs@example.test  READY', out)
        self.assertIn('balance 4.20 USD', out)
        self.assertNotIn('UNAVAILABLE', out)
        self.assertNotIn('top up', out)
        self.assertNotIn('DEEPSEEK_ACCOUNT_LABEL', out)

    def test_zero_balance_is_exhausted_even_when_flag_says_available(self):
        data = {'is_available': True, 'balance_infos': [{'currency': 'USD', 'total_balance': '0.00'}]}
        with patch.dict(usage.os.environ, {'DEEPSEEK_ACCOUNT_LABEL': 'me'}), patch.object(usage, 'get_json', return_value=data):
            result = usage.deepseek({'deepseek': {'type': 'api_key', 'key': self.KEY}})
        with patch.object(usage, 'use_color', return_value=False):
            out = usage.render(report('deepseek', result))
        self.assertIn('me  EXHAUSTED', out)
        self.assertIn('top up:', out)


class UsageTests(unittest.TestCase):
    def test_codex_is_subscription_only_and_whitelists_response(self):
        auth = {'openai-codex': {'type': 'oauth', 'access': 'fake-test', 'expires': (time.time() + 600) * 1000}}
        data = {'private': 'sensitive', 'rate_limit': {'primary_window': {'used_percent': 0, 'reset_at': 100, 'private': 'sensitive'}}}
        with patch.object(usage, 'get_json', return_value=data) as fetch:
            result = usage.codex(auth)
        self.assertEqual(result['windows'][0]['used_percent'], 0)
        self.assertNotIn('sensitive', str(result))
        self.assertEqual(fetch.call_args.args[0], 'https://chatgpt.com/backend-api/wham/usage')

    def test_expired_oauth_does_not_refresh_or_request(self):
        with patch.object(usage, 'get_json') as fetch:
            result = usage.codex({'openai-codex': {'type': 'oauth', 'access': 'fake', 'expires': 1}})
        self.assertEqual(result['status'], 'unavailable')
        fetch.assert_not_called()

    def test_deepseek_stored_key_precedence_and_commands_not_executed(self):
        with patch.dict(usage.os.environ, {'DEEPSEEK_API_KEY': 'env-value'}):
            self.assertEqual(usage.deepseek_key({'deepseek': {'type': 'api_key', 'key': 'stored-value'}}), 'stored-value')
            self.assertIsNone(usage.deepseek_key({'deepseek': {'type': 'api_key', 'key': '!dangerous-command'}}))
            self.assertEqual(usage.deepseek_key({}), 'env-value')

    def test_missing_quota_is_unknown_not_zero(self):
        with patch.object(usage, 'get_json', return_value={'tokens': [{'fp': 'test', 'quota_scope_denied': True}]}):
            result = usage.anthropic({})
        self.assertIsNone(result['accounts'][0]['windows'][0]['used_percent'])
        self.assertTrue(result['accounts'][0]['quota_scope_denied'])

    def test_one_provider_failure_does_not_break_others_or_leak_error(self):
        def broken(_):
            raise ValueError('secret-value')
        with patch.dict(usage.ADAPTERS, {'anthropic': broken, 'deepseek': lambda _: {'status': 'ok'}}):
            result = usage.collect({}, ['anthropic', 'deepseek'])
        self.assertEqual(result['anthropic']['status'], 'unavailable')
        self.assertEqual(result['deepseek']['status'], 'ok')
        self.assertNotIn('secret-value', str(result))

    def test_remote_proxy_is_rejected(self):
        with patch.dict(usage.os.environ, {'PI_ANTHROPIC_PROXY_URL': 'http://example.com'}):
            with self.assertRaises(ValueError):
                usage.local_url()


if __name__ == '__main__':
    unittest.main()
