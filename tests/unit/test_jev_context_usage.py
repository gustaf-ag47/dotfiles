"""File scouting shares Jev accounting, not provider quota/routing."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('jev_context_usage', ROOT / 'scripts/llm_usage.py')
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def event(**extra):
    return dict(schema='jev-event.v1', timestamp='2026-10-02T12:00:00Z',
                source='pi', status='ok', model='jev-1.13.0',
                input_tokens=500, output_tokens=50, estimated_cost_usd=0.000021,
                cost_source='published-rate', applied=False, **extra)


class ScoutAccountingTests(unittest.TestCase):
    def test_scout_and_legacy_task_events_share_cost_not_class_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / 'events.jsonl'
            ledger.write_text('\n'.join(json.dumps(e) for e in [
                event(**{'class': 'mechanical'}),
                event(purpose='file-scout', **{'class': None}),
            ]) + '\n')
            report = usage.jev_classifier_activity(ledger_path=ledger)
        total = report['retained_total']
        self.assertEqual(total['by_purpose'], {'task-class': 1, 'file-scout': 1})
        self.assertEqual(total['by_class'], {'mechanical': 1})
        self.assertEqual(total['network_calls'], 2)
        self.assertEqual(total['applied_count'], 0)
        self.assertAlmostEqual(total['estimated_cost_usd'], 0.000042)

    def test_unknown_purpose_and_raw_payload_do_not_leak(self):
        row = event(purpose={'private': 'SOURCE_MUST_NOT_LEAK'},
                    raw_source='SOURCE_MUST_NOT_LEAK', path='/secret/file')
        normalized = usage.jev_validate_event(row)
        self.assertNotIn('SOURCE_MUST_NOT_LEAK', json.dumps(normalized))
        self.assertNotIn('/secret/file', json.dumps(normalized))
        self.assertEqual(usage.jev_aggregate([normalized])['by_purpose'], {'unknown': 1})


if __name__ == '__main__':
    unittest.main()
