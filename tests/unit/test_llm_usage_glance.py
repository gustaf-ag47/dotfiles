"""Glance is a presentation-only view; diagnostics and JSON remain available."""
import unittest
from unittest.mock import patch
from tests.unit.test_llm_usage import usage


class GlanceTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(usage.time, 'time', return_value=1000)
        self.color = patch.object(usage, 'use_color', return_value=False)
        self.clock.start()
        self.color.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.color.stop)

    def report(self):
        return {'providers': {'anthropic': {
            'status': 'ok', 'checked_at': 1000,
            'accounts': [
                {'account': 'a', 'label': 'active@test', 'valid': True,
                 'windows': [{'name': 'seven_day', 'used_percent': 36,
                              'reset_at': 2000, 'source': 'header observation',
                              'observed_at': 880}]},
                {'account': 'b', 'label': 'parked@test', 'valid': False, 'windows': []},
                {'account': 'c', 'label': 'cool@test', 'valid': True,
                 'cooldown_until': 1500, 'windows': []}],
            'routing': {'buckets': {'base': {'would_pick': 'a'}, 'oi': {'would_pick': None}}}}},
            'classifier_activity': {'irrelevant': True}, 'decision_gate_activity': {'irrelevant': True}}

    def test_glance_keeps_failures_and_model_specific_routes(self):
        out = usage.render_glance(self.report())
        self.assertIn('Claude  ROUTABLE', out)
        self.assertIn('opus/sonnet (7d) → active@test', out)
        self.assertIn('fable (7d fable) → none routable', out)
        self.assertIn('parked@test: AUTH · needs sign-in', out)
        self.assertIn('1 account(s) cooling', out)
        self.assertIn('~64% left', out)
        self.assertIn('observed 2m ago', out)
        for noise in ('freshness=', 'confidence=', 'classifier', 'decision-gate', 'burn', 'forecast'):
            self.assertNotIn(noise, out)

    def test_accounts_expands_cooling_account(self):
        self.assertIn('cool@test  COOLDOWN', usage.render_glance(self.report(), accounts=True))
        self.assertNotIn('cool@test', usage.render_glance(self.report()))

    def test_expired_and_missing_quota_stay_unknown(self):
        for w in ({'name': 'seven_day', 'used_percent': 36, 'reset_at': 900},
                  {'name': 'five_hour', 'used_percent': None}):
            self.assertIn('? left', usage.glance_window(w, 1000))
            self.assertNotIn('64%', usage.glance_window(w, 1000))

    def test_only_missing_configuration_hidden(self):
        report = {'providers': {
            'deepseek': {'status': 'unavailable', 'reason': 'No supported DeepSeek API key configured.'},
            'openai-codex': {'status': 'unavailable', 'reason': 'HTTP 401: expired'},
            'google-antigravity': {'status': 'unavailable', 'reason': 'proxy not running'}}}
        out = usage.render_glance(report)
        self.assertNotIn('No supported', out)
        self.assertIn('HTTP 401', out)
        self.assertIn('proxy not running', out)
        self.assertIn('No supported', usage.render_glance(report, show_all=True))

    def test_no_routing_evidence_does_not_claim_ready(self):
        report = self.report()
        report['providers']['anthropic'].pop('routing')
        self.assertIn('ROUTING UNKNOWN', usage.render_glance(report))

    def test_distinct_route_accounts_have_labeled_quota(self):
        report = self.report()
        report['providers']['anthropic']['routing']['buckets']['oi']['would_pick'] = 'c'
        out = usage.render_glance(report)
        self.assertIn('\n  active@test\n', out)
        self.assertIn('\n  cool@test\n', out)

    def test_codex_credit_and_model_actions_remain_visible(self):
        report = {'providers': {'openai-codex': {'status': 'ok', 'allowed': False,
                  'limit_reached': True, 'reset_credits': 1, 'windows': [],
                  'models': {'example-model': {'available': False}}}}}
        out = usage.render_glance(report)
        self.assertIn('LIMIT REACHED', out)
        self.assertIn('1 reset credit', out)
        self.assertIn('example-model: unavailable', out)
        self.assertIn('Top up:', out)

    def test_empty_report(self):
        self.assertIn('No configured providers', usage.render_glance({'providers': {}}))


if __name__ == '__main__':
    unittest.main()
