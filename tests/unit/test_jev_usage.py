"""Tests for the local-only Jev classifier activity section in llm_usage.py.

Covers: missing/empty/corrupt/truncated ledgers, unknown-cost handling,
UTC day rollover, integration with the provider-report cache refresh, and
that existing providers/schema stay unaffected by this addition.
"""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('llm_usage', Path(__file__).resolve().parents[2] / 'scripts/llm_usage.py')
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def event(**overrides):
    base = {
        'schema': 'jev-event.v1',
        'timestamp': '2026-10-02T12:00:00Z',
        'source': 'delegate',
        'status': 'ok',
        'class': 'routine',
        'confidence': 0.91,
        'model': 'jev-1.13.0',
        'rubric_version': 'r3',
        'latency_ms': 120,
        'input_tokens': 500,
        'output_tokens': 0,
        'estimated_cost_usd': 0.000021,
        'cost_source': 'published-rate',
        'applied': False,
    }
    base.update(overrides)
    return base


def write_ledger(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(line) if isinstance(line, dict) else line for line in lines) + '\n')


class LedgerPathTests(unittest.TestCase):
    def test_ledger_path_follows_xdg_state_home(self):
        with patch.dict(usage.os.environ, {'XDG_STATE_HOME': '/tmp/xdg-state-test'}):
            self.assertEqual(usage.jev_ledger_path(), Path('/tmp/xdg-state-test/jev/events.jsonl'))

    def test_ledger_path_defaults_under_home(self):
        with patch.dict(usage.os.environ, {}, clear=False):
            usage.os.environ.pop('XDG_STATE_HOME', None)
            self.assertEqual(usage.jev_ledger_path(), Path.home() / '.local' / 'state' / 'jev' / 'events.jsonl')


class MissingAndEmptyLedgerTests(unittest.TestCase):
    def test_missing_ledger_is_quiet_and_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            activity = usage.jev_classifier_activity(ledger_path=Path(tmp) / 'nope' / 'events.jsonl')
        self.assertEqual(activity['schema'], 'jev-classifier-activity.v1')
        self.assertEqual(activity['ledger_status'], 'missing')
        self.assertEqual(activity['today']['calls'], 0)
        self.assertEqual(activity['retained_total']['calls'], 0)
        self.assertEqual(activity['malformed_lines_skipped'], 0)
        lines = usage.jev_classifier_lines(activity)
        self.assertIn('  no local activity observed (ledger not found)', lines)

    def test_empty_file_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            path.write_text('')
            activity = usage.jev_classifier_activity(ledger_path=path)
        self.assertEqual(activity['ledger_status'], 'ok')
        self.assertEqual(activity['today']['calls'], 0)

    def test_unreadable_ledger_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [event()])
            os.chmod(path, 0)
            try:
                if os.access(path, os.R_OK):
                    self.skipTest('running as a user that bypasses file permissions (e.g. root)')
                activity = usage.jev_classifier_activity(ledger_path=path)
            finally:
                os.chmod(path, 0o600)
        self.assertEqual(activity['ledger_status'], 'unreadable')
        self.assertEqual(activity['today']['calls'], 0)


class ParsingAndValidationTests(unittest.TestCase):
    def test_corrupt_and_unknown_schema_lines_are_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(),
                '{not valid json',
                json.dumps({'schema': 'some-other-event.v1', 'status': 'ok'}),
                json.dumps(event(status='not-a-real-status')),
                json.dumps(event(timestamp='not-a-timestamp')),
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        self.assertEqual(activity['retained_total']['calls'], 1)
        self.assertEqual(activity['parse_errors'], 1)
        self.assertEqual(activity['schema_errors'], 3)
        self.assertEqual(activity['malformed_lines_skipped'], 4)
        rendered = '\n'.join(usage.jev_classifier_lines(activity))
        self.assertNotIn('not valid json', rendered)
        self.assertNotIn('not-a-real-status', rendered)

    def test_truncated_final_line_is_dropped_quietly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            path.write_text(json.dumps(event()) + '\n' + json.dumps(event())[:20])
            activity = usage.jev_classifier_activity(ledger_path=path)
        self.assertEqual(activity['retained_total']['calls'], 1)
        self.assertEqual(activity['malformed_lines_skipped'], 0)

    def test_unknown_token_and_cost_fields_never_become_silent_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(input_tokens=None, output_tokens=None, estimated_cost_usd=None, cost_source='unknown'),
                event(status='error', input_tokens=None, output_tokens=None, estimated_cost_usd=None, cost_source=None),
                event(estimated_cost_usd=0.00005, cost_source='published-rate', input_tokens=100, output_tokens=0),
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        total = activity['retained_total']
        self.assertEqual(total['calls'], 3)
        self.assertEqual(total['tokens_unknown_calls'], 2)
        self.assertEqual(total['cost_unknown_calls'], 2)
        self.assertEqual(total['input_tokens'], 100)
        self.assertAlmostEqual(total['estimated_cost_usd'], 0.00005)
        self.assertEqual(total['errors'], 1)

    def test_applied_true_is_surfaced_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [event(applied=True)])
            activity = usage.jev_classifier_activity(ledger_path=path)
        self.assertEqual(activity['today']['applied_count'], 1)
        rendered = '\n'.join(usage.jev_classifier_lines(activity))
        self.assertIn('anomaly', rendered)
        self.assertIn('applied=true', rendered)


class HardeningTests(unittest.TestCase):
    """Regression coverage for parent-review findings: unhashable enum fields,
    non-finite/negative numerics, secret-shaped class labels, and cache-hit
    zero-cost accounting.
    """

    def test_unhashable_enum_fields_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(status=['ok']),
                event(source={'bad': 'dict'}),
                event(cost_source=['published-rate']),
            ])
            # Must not raise TypeError (unhashable type) anywhere in the read path.
            activity = usage.jev_classifier_activity(ledger_path=path)
        # status is required/validated first: an unhashable status fails closed (schema error).
        self.assertEqual(activity['schema_errors'], 1)
        # unhashable source/cost_source don't invalidate the whole event; they just come back as None/unknown.
        self.assertEqual(activity['retained_total']['calls'], 2)
        self.assertEqual(activity['retained_total']['cost_unknown_calls'], 1,
                          'only the event with an unhashable cost_source loses its known cost')

    def test_nan_inf_and_negative_numerics_are_rejected_not_poisoning_sums(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                json.dumps(event(latency_ms=float('nan'))),
                json.dumps(event(latency_ms=float('inf'))),
                json.dumps(event(latency_ms=-5)),
                json.dumps(event(estimated_cost_usd=float('nan'), cost_source='published-rate')),
                json.dumps(event(estimated_cost_usd=-0.01, cost_source='published-rate')),
                json.dumps(event(input_tokens=-10)),
                json.dumps(event(output_tokens=-1)),
                json.dumps(event(confidence=float('inf'))),
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        total = activity['retained_total']
        self.assertEqual(total['calls'], 8, 'events are still retained; only the bad field is dropped to None/unknown')
        # 3 of the 8 fixtures corrupt latency_ms itself (nan/inf/-5); the other
        # 5 keep the fixture's valid default latency, so they still summarize.
        self.assertEqual(total['latency_ms_summary']['count'], 5)
        self.assertEqual(total['latency_ms_summary']['avg'], 120.0)
        # 2 of the 8 fixtures corrupt estimated_cost_usd itself (nan/negative);
        # the other 6 keep the fixture's valid default cost and are summed.
        self.assertAlmostEqual(total['estimated_cost_usd'], 6 * 0.000021)
        self.assertEqual(total['cost_unknown_calls'], 2)
        self.assertEqual(total['tokens_unknown_calls'], 2, 'negative token counts are treated as unknown, not as -10/-1')
        # The other 6 fixtures keep the default valid token counts (500 in / 0 out each).
        self.assertEqual(total['input_tokens'], 6 * 500)
        self.assertEqual(total['output_tokens'], 0)

    def test_secretlike_and_control_char_class_is_never_echoed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(**{'class': 'sk-ant-api03-SECRETVALUE\x1b[31mhacked\x07'}),
                event(**{'class': 'has spaces'}),
                event(**{'class': 'routine'}),  # safe token, must still pass through
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        by_class = activity['retained_total']['by_class']
        self.assertEqual(by_class, {'routine': 1})
        rendered = json.dumps(activity) + '\n'.join(usage.jev_classifier_lines(activity))
        self.assertNotIn('SECRET', rendered)
        self.assertNotIn('\x1b', rendered)
        self.assertNotIn('has spaces', rendered)

    def test_cache_hit_zero_cost_is_known_not_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(status='cache_hit', estimated_cost_usd=0, cost_source='cache',
                      input_tokens=0, output_tokens=0),
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        today = activity['today']
        self.assertEqual(today['cost_unknown_calls'], 0, 'a cache hit with a known (zero) cost is not unknown-cost')
        self.assertEqual(today['estimated_cost_usd'], 0.0)

    def test_observation_count_distinct_from_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(status='ok'),
                event(status='error'),
                event(status='abstained'),
                event(status='cache_hit'),
                event(status='skipped'),
            ])
            activity = usage.jev_classifier_activity(ledger_path=path)
        today = activity['today']
        self.assertEqual(today['calls'], 5, 'calls = every retained observation, any status')
        self.assertEqual(today['network_calls'], 3, 'only ok/abstained/error actually reached the classifier')
        rendered = '\n'.join(usage.jev_classifier_lines(activity))
        self.assertIn('observations=5', rendered)
        self.assertIn('network_calls=3', rendered)


class DayRolloverTests(unittest.TestCase):
    def test_only_today_utc_events_count_toward_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [
                event(timestamp='2026-10-01T23:59:59Z'),
                event(timestamp='2026-10-02T00:00:01Z'),
                event(timestamp='2026-10-02T23:59:59+00:00'),
            ])
            now = datetime.datetime(2026, 10, 2, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
            activity = usage.jev_classifier_activity(now=now, ledger_path=path)
        self.assertEqual(activity['today_utc'], '2026-10-02')
        self.assertEqual(activity['today']['calls'], 2)
        self.assertEqual(activity['retained_total']['calls'], 3)

    def test_local_offset_timestamp_normalizes_to_utc_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            # 23:30 at UTC-5 is 04:30 the next UTC day.
            write_ledger(path, [event(timestamp='2026-10-01T23:30:00-05:00')])
            now = datetime.datetime(2026, 10, 2, 6, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
            activity = usage.jev_classifier_activity(now=now, ledger_path=path)
        self.assertEqual(activity['today']['calls'], 1)


class CacheIntegrationTests(unittest.TestCase):
    def test_providers_report_unaffected_cache_refresh_still_rereads_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            cache_home = Path(tmp) / 'cache'
            state_home = Path(tmp) / 'state'
            agent_dir = Path(tmp) / 'agent'
            home.mkdir(); cache_home.mkdir(); state_home.mkdir(); agent_dir.mkdir()
            ledger = state_home / 'jev' / 'events.jsonl'
            env = {'HOME': str(home), 'XDG_CACHE_HOME': str(cache_home), 'XDG_STATE_HOME': str(state_home),
                   'PI_CODING_AGENT_DIR': str(agent_dir)}
            with patch.dict(usage.os.environ, env, clear=False):
                with patch.object(usage, 'collect', return_value={}):
                    import io
                    import contextlib

                    def run(args):
                        out = io.StringIO()
                        with patch('sys.argv', ['llm_usage.py'] + args), contextlib.redirect_stdout(out):
                            usage.main()
                        return json.loads(out.getvalue())

                    first = run(['--json'])
                    self.assertIn('classifier_activity', first)
                    self.assertEqual(first['classifier_activity']['retained_total']['calls'], 0)
                    self.assertEqual(first['providers'], {})

                    write_ledger(ledger, [event()])
                    second = run(['--json'])  # same identity => provider report served from the 60s cache
                    self.assertEqual(second['providers'], {})
                    self.assertEqual(second['classifier_activity']['retained_total']['calls'], 1,
                                      'ledger must be read fresh even when the provider report cache is reused')

    def test_ledger_file_and_dir_permissions_not_widened(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jevdir' / 'events.jsonl'
            write_ledger(path, [event()])
            os.chmod(path, 0o600)
            os.chmod(path.parent, 0o700)
            usage.jev_classifier_activity(ledger_path=path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)


class RenderAndSchemaTests(unittest.TestCase):
    def test_text_render_includes_jev_section_without_breaking_provider_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            write_ledger(path, [event(), event(status='abstained', class_=None, applied=False)])
            activity = usage.jev_classifier_activity(ledger_path=path)
        report = {'schema': usage.REPORT_SCHEMA, 'generated_at': int(time.time()),
                  'providers': {'deepseek': {'status': 'ok', 'checked_at': int(time.time()),
                                              'normalized': {'freshness': {'state': 'fresh'}, 'confidence': 'high'}}},
                  'classifier_activity': activity}
        with patch.object(usage, 'use_color', return_value=False):
            with patch.object(usage, 'RENDERERS', {'deepseek': lambda info, now: (['  ok'], False)}):
                rendered = usage.render(report)
        self.assertIn('Jev classifier activity (observation only)', rendered)
        self.assertIn('deepseek', rendered)

    def test_waybar_payload_ignores_classifier_activity(self):
        report = {'providers': {}, 'classifier_activity': {'today': {'calls': 5}}}
        payload = usage.waybar_payload(report)
        self.assertNotIn('jev', json.dumps(payload).lower())

    def test_jev_not_listed_as_a_routable_provider(self):
        self.assertNotIn('jev', usage.ADAPTERS)
        self.assertNotIn('jev', usage.REPORT_SOURCES)


if __name__ == '__main__':
    unittest.main()
