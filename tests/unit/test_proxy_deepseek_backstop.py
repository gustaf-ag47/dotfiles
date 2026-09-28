"""Focused DeepSeek backstop invariants (kept separate from shared sibling tests)."""

import json
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock
from tests.unit.proxy_fixture import ProxyIsolationMixin


PROXY_PATH = Path(__file__).parents[2] / "bin" / "claude-token-proxy"
proxy = SourceFileLoader("claude_token_proxy_deepseek_tests", str(PROXY_PATH)).load_module()


class DeepseekBackstopTests(ProxyIsolationMixin, unittest.TestCase):
    proxy = proxy
    def test_rewrite_model_changes_only_model(self):
        original = {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "hi"}]}
        rewritten = json.loads(proxy.rewrite_model(json.dumps(original).encode(), "deepseek-v4-pro"))
        self.assertEqual(rewritten["model"], "deepseek-v4-pro")
        self.assertEqual(rewritten["messages"], original["messages"])

    def test_candidate_respects_balance_floor_and_availability(self):
        healthy = {"status": "ok", "available": True,
                   "balances": [{"currency": "USD", "total_balance": "2.00"}]}
        candidate = proxy.deepseek_candidate("deepseek-v4-pro", healthy)
        self.assertTrue(candidate["routable"])
        self.assertEqual(candidate["model"], "deepseek-v4-pro")
        self.assertFalse(proxy.deepseek_candidate("deepseek-flash", {
            **healthy, "available": False
        })["routable"])

    def test_upstream_uses_deepseek_key_and_never_oauth_bearer(self):
        conn = mock.Mock()
        with mock.patch.object(proxy.http.client, "HTTPSConnection", return_value=conn):
            proxy.deepseek_upstream("POST", "/v1/messages", {
                "Authorization": "Bearer OAuthCanary", "x-api-key": "old", "anthropic-version": "2023-06-01"
            }, b"{}", "DeepSeekCanary")
        args, kwargs = conn.request.call_args
        self.assertEqual(args[:2], ("POST", "/anthropic/v1/messages"))
        headers = {k.lower(): v for k, v in kwargs["headers"].items()}
        self.assertEqual(headers["x-api-key"], "DeepSeekCanary")
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

    def test_failover_is_opt_in_by_default(self):
        self.assertEqual(proxy.os.environ.get("CC_PROXY_DEEPSEEK_FALLBACK", "0"), "0")
        service = (Path(__file__).parents[2] / "config/systemd/user/claude-token-proxy.service").read_text()
        self.assertNotIn("CC_PROXY_DEEPSEEK_FALLBACK=1", service)


if __name__ == "__main__":
    unittest.main()
