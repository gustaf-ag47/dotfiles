#!/usr/bin/env python3
"""Unit tests for scripts/decision_gate/core.py: policy, cache key, scoring, store, report."""
import tempfile
import time
import unittest
from pathlib import Path

from scripts.decision_gate import core


class PolicyTests(unittest.TestCase):
    def test_missing_file_is_defaults(self):
        policy, err = core.load_policy(Path("/nonexistent/decision-gate/policy.json"))
        self.assertIsNone(err)
        self.assertEqual(policy["default"]["backend"], "ollama")

    def test_malformed_json_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "policy.json"
            p.write_text("{not json")
            policy, err = core.load_policy(p)
            self.assertIsNone(policy)
            self.assertEqual(err, "policy_malformed")

    def test_bad_backend_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "policy.json"
            p.write_text('{"default": {"backend": "opus"}}')
            policy, err = core.load_policy(p)
            self.assertIsNone(policy)
            self.assertEqual(err, "policy_invalid")

    def test_purpose_overrides_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "policy.json"
            p.write_text('{"purposes": {"x": {"backend": "jev", "min_p": 0.5}}}')
            policy, err = core.load_policy(p)
            self.assertIsNone(err)
            effective = core.resolve_policy(policy, "x")
            self.assertEqual(effective["backend"], "jev")
            self.assertEqual(effective["min_p"], 0.5)
            self.assertEqual(effective["cache_ttl_s"], core.DEFAULT_CACHE_TTL_S)

    def test_unknown_purpose_falls_back_to_default(self):
        policy, _ = core.load_policy(Path("/nonexistent"))
        effective = core.resolve_policy(policy, "never-configured")
        self.assertEqual(effective["backend"], "ollama")


class PrivacyEnforcementTests(unittest.TestCase):
    def test_private_forced_off_jev_by_default(self):
        effective = {"backend": "jev", "allow_external": False}
        backend, overridden = core.enforce_privacy(effective, "private")
        self.assertEqual(backend, "ollama")
        self.assertTrue(overridden)

    def test_private_allowed_jev_with_explicit_flag(self):
        effective = {"backend": "jev", "allow_external": True}
        backend, overridden = core.enforce_privacy(effective, "private")
        self.assertEqual(backend, "jev")
        self.assertFalse(overridden)

    def test_internal_jev_untouched(self):
        effective = {"backend": "jev", "allow_external": False}
        backend, overridden = core.enforce_privacy(effective, "internal")
        self.assertEqual(backend, "jev")
        self.assertFalse(overridden)

    def test_sensitivity_allowed(self):
        effective = {"allowed_sensitivity": ["internal", "public"]}
        self.assertFalse(core.sensitivity_allowed(effective, "private"))
        self.assertTrue(core.sensitivity_allowed(effective, "internal"))


class CacheKeyTests(unittest.TestCase):
    def test_deterministic(self):
        q = [{"id": "k", "kind": "bool", "prompt": "p"}]
        a = core.cache_key("purpose", "state text", q, "ollama:m1")
        b = core.cache_key("purpose", "state text", q, "ollama:m1")
        self.assertEqual(a, b)

    def test_differs_on_backend_version(self):
        q = [{"id": "k", "kind": "bool", "prompt": "p"}]
        a = core.cache_key("purpose", "state", q, "ollama:m1")
        b = core.cache_key("purpose", "state", q, "ollama:m2")
        self.assertNotEqual(a, b)

    def test_differs_on_state(self):
        q = [{"id": "k", "kind": "bool", "prompt": "p"}]
        a = core.cache_key("purpose", "state 1", q, "v")
        b = core.cache_key("purpose", "state 2", q, "v")
        self.assertNotEqual(a, b)

    def test_json_state_order_independent(self):
        q = [{"id": "k", "kind": "bool", "prompt": "p"}]
        a = core.cache_key("purpose", {"a": 1, "b": 2}, q, "v")
        b = core.cache_key("purpose", {"b": 2, "a": 1}, q, "v")
        self.assertEqual(a, b)


class ScoringTests(unittest.TestCase):
    def test_softmax_sums_to_one(self):
        probs = core.softmax({"a": 2.0, "b": 1.0, "c": 0.1})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)

    def test_softmax_empty(self):
        self.assertEqual(core.softmax({}), {})

    def test_softmax_peak_wins(self):
        probs = core.softmax({"a": 10.0, "b": 0.0})
        self.assertGreater(probs["a"], probs["b"])

    def test_decide_answer_confident(self):
        choice, p, abstained = core.decide_answer({"a": 0.9, "b": 0.1}, min_p=0.8)
        self.assertEqual(choice, "a")
        self.assertEqual(p, 0.9)
        self.assertFalse(abstained)

    def test_decide_answer_below_threshold_abstains(self):
        choice, p, abstained = core.decide_answer({"a": 0.6, "b": 0.4}, min_p=0.8)
        self.assertEqual(choice, "a")
        self.assertTrue(abstained)

    def test_decide_answer_empty_probs_abstains(self):
        choice, p, abstained = core.decide_answer({}, min_p=0.8)
        self.assertIsNone(choice)
        self.assertEqual(p, 0.0)
        self.assertTrue(abstained)


class LedgerEventTests(unittest.TestCase):
    def test_build_event_rejects_bad_kind(self):
        with self.assertRaises(ValueError):
            core.build_ledger_event(kind="nope", purpose="p")

    def test_build_event_strips_unsafe_purpose(self):
        event = core.build_ledger_event(kind="decide", purpose="not safe; text\nhere")
        self.assertIsNone(event["purpose"])

    def test_build_event_keeps_safe_purpose(self):
        event = core.build_ledger_event(kind="decide", purpose="finance-attachment-kind")
        self.assertEqual(event["purpose"], "finance-attachment-kind")

    def test_append_and_read_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            state_dir = Path(d) / "state"
            event = core.build_ledger_event(kind="decide", purpose="p", backend="ollama", latency_ms=12.3,
                                              cached=False, abstained=False)
            core.append_ledger(state_dir, event)
            path = core.ledger_path(state_dir)
            self.assertTrue(path.exists())
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            lines = path.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = core.Store(Path(self.tmp.name) / "state")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_cache_round_trip(self):
        self.store.cache_put("key1", {"q": {"probs": {"a": 0.9}}}, "ollama", "m1", ttl_s=60)
        got = self.store.cache_get("key1")
        self.assertEqual(got["answers"]["q"]["probs"]["a"], 0.9)

    def test_cache_expires(self):
        now = time.time()
        self.store.cache_put("key1", {"q": {}}, "ollama", "m1", ttl_s=1, now=now)
        self.assertIsNone(self.store.cache_get("key1", now=now + 2))

    def test_budget_increments(self):
        self.assertEqual(self.store.budget_count("p", "2026-01-01"), 0)
        self.store.budget_increment("p", "2026-01-01")
        self.store.budget_increment("p", "2026-01-01")
        self.assertEqual(self.store.budget_count("p", "2026-01-01"), 2)

    def test_decision_and_outcome_round_trip(self):
        answers = {"kind": {"choice": "invoice", "p": 0.9, "probs": {"invoice": 0.9}, "abstained": False}}
        self.store.record_decision("dg_1", "p", "internal", "jev", answers)
        got = self.store.get_decision("dg_1")
        self.assertEqual(got["answers"]["kind"]["choice"], "invoice")
        self.store.record_outcome("dg_1", {"kind": "invoice"}, "opus")
        rows = self.store.report_rows("p")
        self.assertEqual(len(rows), 1)

    def test_report_rows_filters_by_purpose(self):
        self.store.record_decision("dg_1", "p1", "internal", "jev", {})
        self.store.record_decision("dg_2", "p2", "internal", "jev", {})
        self.store.record_outcome("dg_1", {"a": 1}, "opus")
        self.store.record_outcome("dg_2", {"a": 1}, "opus")
        self.assertEqual(len(self.store.report_rows("p1")), 1)
        self.assertEqual(len(self.store.report_rows(None)), 2)


class ReportTests(unittest.TestCase):
    def test_compute_report_agreement_and_thresholds(self):
        import json as _json
        rows = [
            ("p", _json.dumps({"kind": {"choice": "invoice", "p": 0.96, "abstained": False}}), _json.dumps({"kind": "invoice"})),
            ("p", _json.dumps({"kind": {"choice": "invoice", "p": 0.82, "abstained": False}}), _json.dumps({"kind": "receipt"})),
            ("p", _json.dumps({"kind": {"choice": None, "p": 0.0, "abstained": True}}), _json.dumps({"kind": "receipt"})),
        ]
        report = core.compute_report(rows)
        self.assertEqual(report["p"]["n"], 3)
        self.assertAlmostEqual(report["p"]["abstain_rate"], 1 / 3, places=4)
        # 2 answered, 1 correct -> agreement 0.5
        self.assertAlmostEqual(report["p"]["agreement"], 0.5, places=4)
        # threshold 0.95: only the first row qualifies (p=0.96), and it's correct
        self.assertEqual(report["p"]["thresholds"]["0.95"]["coverage"], round(1 / 3, 4))
        self.assertEqual(report["p"]["thresholds"]["0.95"]["precision"], 1.0)
        # threshold 0.8: both answered rows qualify, 1/2 correct
        self.assertEqual(report["p"]["thresholds"]["0.8"]["precision"], 0.5)

    def test_compute_report_empty(self):
        self.assertEqual(core.compute_report([]), {})

    def test_compute_report_bool_truth(self):
        import json as _json
        rows = [("p", _json.dumps({"financial": {"choice": True, "p": 0.99, "abstained": False}}),
                  _json.dumps({"financial": True}))]
        report = core.compute_report(rows)
        self.assertEqual(report["p"]["agreement"], 1.0)


if __name__ == "__main__":
    unittest.main()
