"""Tests for the decision-gate activity section added to llm_usage.py.

Mirrors tests/unit/test_jev_usage.py's approach for the parallel Jev section:
missing/corrupt ledger handling, aggregation, and that it's metadata-only.
"""
import datetime
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('llm_usage', Path(__file__).resolve().parents[2] / 'scripts/llm_usage.py')
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)

FROZEN_NOW = datetime.datetime(2026, 10, 7, 18, 0, 0, tzinfo=datetime.timezone.utc).timestamp()


def event(**overrides):
    base = {
        'schema': 'decision-gate-event.v1',
        'timestamp': '2026-10-07T12:00:00Z',
        'kind': 'decide',
        'purpose': 'finance-attachment-kind',
        'sensitivity': 'internal',
        'backend': 'jev',
        'model': 'jev-1.13.0',
        'latency_ms': 210.5,
        'cached': False,
        'abstained': False,
        'input_tokens': 300,
        'output_tokens': 20,
        'estimated_cost_usd': 0.0000126,
        'cost_source': 'published-rate',
        'overridden_for_privacy': False,
    }
    base.update(overrides)
    return base


class DecisionGateActivityTests(unittest.TestCase):
    def test_missing_ledger(self):
        activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=Path('/nonexistent/decision-gate/events.jsonl'))
        self.assertEqual(activity['ledger_status'], 'missing')
        self.assertEqual(activity['today']['decides'], 0)

    def test_aggregates_today_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            lines = [
                json.dumps(event()),
                json.dumps(event(abstained=True, backend='ollama', model='qwen2.5vl:7b', cost_source='cache',
                                  estimated_cost_usd=0.0)),
                json.dumps(event(timestamp='2026-09-01T00:00:00Z')),  # different day, excluded from "today"
            ]
            path.write_text('\n'.join(lines) + '\n')
            activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=path)
            self.assertEqual(activity['today']['decides'], 2)
            self.assertEqual(activity['today']['abstained'], 1)
            self.assertEqual(activity['retained_total']['decides'], 3)
            self.assertIn('finance-attachment-kind', activity['today']['by_purpose'])
            self.assertIn('jev', activity['today']['by_backend'])
            self.assertIn('ollama', activity['today']['by_backend'])

    def test_malformed_lines_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            path.write_text('not json\n' + json.dumps(event()) + '\n' + json.dumps({'schema': 'other.v1'}) + '\n')
            activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=path)
            self.assertEqual(activity['malformed_lines_skipped'], 2)
            self.assertEqual(activity['today']['decides'], 1)

    def test_metadata_only_no_state_or_answers_keys_survive(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            injected = event()
            injected['state'] = 'this must never be read'
            injected['answers'] = {'kind': 'invoice'}
            path.write_text(json.dumps(injected) + '\n')
            activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=path)
            self.assertEqual(activity['today']['decides'], 1)
            # dg_validate_event() only copies a fixed known field set -- state/answers never survive it.
            events, _ = usage.dg_read_ledger(path)
            self.assertNotIn('state', events[0])
            self.assertNotIn('answers', events[0])

    def test_overridden_for_privacy_counted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'events.jsonl'
            path.write_text(json.dumps(event(overridden_for_privacy=True, backend='ollama', sensitivity='private')) + '\n')
            activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=path)
            self.assertEqual(activity['today']['overridden_for_privacy'], 1)

    def test_render_lines_dont_crash_on_empty(self):
        activity = usage.decision_gate_activity(now=FROZEN_NOW, ledger_path=Path('/nonexistent'))
        lines = usage.decision_gate_lines(activity)
        self.assertTrue(any('no local activity observed' in line for line in lines))


if __name__ == '__main__':
    unittest.main()
