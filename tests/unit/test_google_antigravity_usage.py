"""Offline tests for the google-antigravity adapter in scripts/llm_usage.py."""
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import llm_usage  # noqa: E402


class GoogleAntigravityUsageTest(unittest.TestCase):
    def setUp(self):
        self.real = llm_usage.get_json
        self.addCleanup(setattr, llm_usage, "get_json", self.real)

    def test_groups_buckets_and_normalizes(self):
        llm_usage.get_json = lambda url, headers=None: {"models": {
            "gemini-3.8-flash-tiered": {"remaining_fraction": 0.9, "reset_time": "2026-10-10T18:00:00Z"},
            "gemini-3.1-pro-low": {"remaining_fraction": 0.8, "reset_time": "2026-10-10T18:00:00Z"},
            "claude-sonnet-4-6": {"remaining_fraction": 1, "reset_time": "2026-10-10T19:00:00Z"},
            "broken": {"remaining_fraction": None}}}
        raw = llm_usage.google_antigravity({})
        self.assertEqual(raw["status"], "ok")
        windows = {w["name"]: w for w in raw["windows"]}
        self.assertAlmostEqual(windows["gemini_weekly"]["used_percent"], 20.0)
        self.assertEqual(windows["third_party_weekly"]["used_percent"], 0.0)
        normalized = llm_usage.normalize_provider("google-antigravity", raw, 0)
        self.assertEqual(normalized["confidence"], "low")
        self.assertEqual(len(normalized["quota"]["windows"]), 2)

    def test_proxy_down_is_unavailable_not_zero(self):
        def down(url, headers=None):
            raise urllib.error.URLError("refused")
        llm_usage.get_json = down
        raw = llm_usage.google_antigravity({})
        self.assertEqual(raw["status"], "unavailable")
        self.assertIn("google-code-assist-proxy", raw["reason"])


if __name__ == "__main__":
    unittest.main()
