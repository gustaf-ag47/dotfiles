"""Regression: a fresh local report must not make old Fable headers fresh."""
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

usage = load('usage_freshness', ROOT / 'scripts/llm_usage.py')
proxy = load('proxy_freshness', ROOT / 'bin/claude-token-proxy')


class FreshnessTests(unittest.TestCase):
    def test_each_header_bucket_has_its_own_persisted_timestamp(self):
        tok = proxy.Tok('fixture-not-a-credential')
        with patch.object(proxy.time, 'time', return_value=1000), patch.object(proxy, 'record_sample'):
            proxy.update_from_headers(tok, {'anthropic-ratelimit-unified-7d_oi-utilization': '0.87'})
        with patch.object(proxy.time, 'time', return_value=2000), patch.object(proxy, 'record_sample'):
            proxy.update_from_headers(tok, {'anthropic-ratelimit-unified-7d-utilization': '0.63'})
        self.assertEqual(tok.header_observed_at, {'u7_oi': 1000, 'u7': 2000})
        restored = proxy.Tok('fixture-not-a-credential')
        proxy.restore_quota(restored, proxy.quota_snapshot(tok), now=2100)
        self.assertEqual(restored.header_observed_at, tok.header_observed_at)
        self.assertEqual(restored.snapshot()['header_observed_at'], tok.header_observed_at)
        # Old persisted data must not acquire a fabricated observation date.
        legacy = proxy.Tok('legacy')
        proxy.restore_quota(legacy, {'u7_oi': .87}, now=2100)
        self.assertEqual(legacy.header_observed_at, {})
        # Restoring old state must not overwrite a newer live reading or age.
        with patch.object(proxy.time, 'time', return_value=3000), patch.object(proxy, 'record_sample'):
            proxy.update_from_headers(restored, {'anthropic-ratelimit-unified-7d_oi-utilization': '1'})
        proxy.restore_quota(restored, proxy.quota_snapshot(tok), now=3100)
        self.assertEqual(restored.u7_oi, 1)
        self.assertEqual(restored.header_observed_at['u7_oi'], 3000)

    def test_scope_denied_headers_are_estimates_not_ready(self):
        token = {'fp': 'a', 'valid': True, 'quota_scope_denied': True,
                 'u7_oi': .87, 'u7_oi_reset': 9000, 'header_observed_at': {'u7_oi': 1000}}
        with patch.object(usage, 'get_json', return_value={'tokens': [token]}):
            raw = usage.anthropic({})
        window = next(w for w in raw['accounts'][0]['windows'] if w['name'] == 'seven_day_overage_included')
        self.assertEqual(window['observed_at'], 1000)
        self.assertNotIn('READY', usage.account_status(raw['accounts'][0], 2000))
        lines, _ = usage.anthropic_lines(raw, 2000)
        text = '\n'.join(lines)
        self.assertIn('user:profile', text)
        self.assertIn('last observed', text)
        self.assertIn('estimate', text)
        normalized = usage.normalize_provider('anthropic', raw, 2000)
        self.assertIsNone(normalized['availability']['provider'])
        self.assertNotEqual(normalized['freshness']['observed_at'], '1970-01-01T00:33:20Z')

    def test_missing_fable_reading_remains_visible_and_explained(self):
        token = {'fp': 'fixture', 'label': 'fixture-account', 'valid': True,
                 'quota_scope_denied': True, 'u5': .3, 'u7': .49,
                 'u7_oi': None, 'u7_oi_reset': None}
        with patch.object(usage, 'get_json', return_value={'tokens': [token]}):
            raw = usage.anthropic({})
        fable = next(w for w in raw['accounts'][0]['windows'] if w['name'] == 'seven_day_overage_included')
        self.assertIsNone(fable['used_percent'])
        self.assertIn('user:profile', fable['unknown_reason'])
        self.assertIn('Fable', fable['unknown_reason'])
        with patch.object(usage, 'use_color', return_value=False):
            line = usage.window_line(fable, 2000)
        self.assertIn('?% left', line)
        self.assertNotIn('100% left', line)
        self.assertIn('user:profile', line)
        normalized = usage.normalize_provider('anthropic', raw, 2000)
        window = next(w for q in normalized['quota']['windows'] for w in q.get('windows', [])
                      if w['name'] == 'seven_day_overage_included')
        self.assertEqual(window['state'], 'unknown')
        self.assertEqual(window['unknown_reason'], fable['unknown_reason'])

    def test_observed_zero_usage_is_not_confused_with_missing_usage(self):
        token = {'fp': 'fixture', 'valid': True, 'u7_oi': 0.0, 'u7_oi_reset': 9999999999}
        with patch.object(usage, 'get_json', return_value={'tokens': [token]}):
            raw = usage.anthropic({})
        normalized = usage.normalize_provider('anthropic', raw, 2000)
        window = next(w for q in normalized['quota']['windows'] for w in q.get('windows', [])
                      if w['name'] == 'seven_day_overage_included')
        self.assertEqual(window['used_percent'], 0)
        self.assertEqual(window['remaining_percent'], 100)
        self.assertIsNone(window['unknown_reason'])
        for provider in ('openai-codex', 'grok-build'):
            with self.subTest(provider=provider):
                normalized = usage.normalize_provider(provider, {'status': 'ok', 'windows': [
                    {'name': 'weekly', 'used_percent': 0}]}, 2000)
                self.assertEqual(normalized['quota']['windows'][0]['remaining_percent'], 100)

    def test_routing_unknown_fable_is_not_an_unexplained_question_mark(self):
        routing = {'buckets': {'oi': {'would_pick': 'fixture', 'ranking': [
            {'fp': 'fixture', 'utilization': None, 'eligible': True, 'pressure': 0.0}]}}}
        with patch.object(usage, 'use_color', return_value=False):
            text = '\n'.join(usage.routing_lines(routing, {'fixture': 'fixture-account'}))
        self.assertIn('no current Fable reading', text)
        self.assertIn('?% left', text)

    def test_warm_report_cache_does_not_hide_new_proxy_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / 'auth.json'
            auth.write_text('{}')
            first = {'status': 'ok', 'accounts': []}
            second = {'status': 'ok', 'accounts': [{'account': 'a', 'model_cooldowns': {'fable': 9000}}]}
            with patch.dict(os.environ, {'XDG_CACHE_HOME': tmp, 'PI_CODING_AGENT_DIR': tmp}), \
                 patch('sys.argv', ['llm-usage', '--json', '--provider', 'anthropic']), \
                 patch.object(usage, 'anthropic', side_effect=[first, second]) as adapter, \
                 patch.dict(usage.ADAPTERS, {'anthropic': lambda auth: usage.anthropic(auth)}), \
                 patch.object(usage, 'jev_classifier_activity', return_value={}), \
                 patch('sys.stdout', new_callable=io.StringIO) as out:
                usage.main()
                out.seek(0)
                out.truncate()
                usage.main()
                report = json.loads(out.getvalue())
            self.assertEqual(adapter.call_count, 2)
            self.assertEqual(report['providers']['anthropic']['accounts'][0]['model_cooldowns'], {'fable': 9000})


if __name__ == '__main__':
    unittest.main()
