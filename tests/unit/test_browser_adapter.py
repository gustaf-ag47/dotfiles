import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "llm_browser", Path(__file__).resolve().parents[2] / "scripts/llm_browser.py"
)
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


class BrowserAdapterTests(unittest.TestCase):
    def test_rendered_and_network_usage_is_redacted_and_normalized(self):
        result = browser.inspect_snapshot(
            rendered={
                "provider": "anthropic",
                "reset_expiry": "2026-10-01T12:00:00Z",
                "offer": "unused trial",
                "account_id": "acct-secret",
                "cookie": "session-secret",
            },
            network_responses=[
                {"url": "https://claude.ai/api/account", "body": json.dumps({
                    "resetCount": 2, "accountId": "acct-secret",
                    "authorization": "Bearer secret",
                })}
            ],
            source_url="https://claude.ai/settings/usage",
            observed_at=1000,
            now=1100,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "authenticated browser rendered page")
        self.assertEqual(result["values"], {"reset_expiry": "2026-10-01T12:00:00Z", "reset_count": 2,
                                             "offer_present": True})
        self.assertEqual(result["age_seconds"], 100)
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("account_id", json.dumps(result))

    def test_mutating_navigation_is_denied(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.assertRaises(browser.MutationDenied):
                browser.assert_read_only(method, "https://claude.ai/settings/usage")
        for url in ("https://claude.ai/checkout", "https://claude.ai/settings/billing", "https://claude.ai/reset"):
            with self.assertRaises(browser.MutationDenied):
                browser.assert_read_only("GET", url)
        browser.assert_read_only("GET", "https://claude.ai/settings/usage")

    def test_login_expiry_and_changed_page_are_explicit(self):
        expired = browser.inspect_snapshot({"logged_in": False}, [], "https://chatgpt.com/usage", 1000, 1100)
        self.assertEqual(expired["status"], "unavailable")
        self.assertIn("logged out", expired["reason"])
        blocked = browser.inspect_snapshot({}, [{"status": 403, "body": "blocked"}],
                                           "https://chatgpt.com/usage", 1000, 1100)
        self.assertEqual(blocked["status"], "unavailable")
        self.assertNotIn("body", blocked)

    def test_cache_is_redacted_permissioned_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            value = browser.inspect_snapshot({"reset_expiry": "tomorrow"}, [], "https://x/usage", 1000, 1001)
            browser.write_cache(path, value)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(browser.read_cache(path, now=1100, max_age=200)["status"], "ok")
            self.assertIsNone(browser.read_cache(path, now=1301, max_age=200))


if __name__ == "__main__":
    unittest.main()
