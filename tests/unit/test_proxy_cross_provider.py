"""Cross-provider EDF oracle behavior, isolated from the main proxy suite."""
import time
import unittest

from tests.unit.test_claude_token_proxy import OracleFixture, codex_state, deepseek_state
from tests.unit import test_claude_token_proxy as proxy_tests

proxy = proxy_tests.proxy


class CrossProviderEDFTests(OracleFixture):
    def providers(self, state):
        proxy.PROVIDER_STATE = {"openai-codex": state, "deepseek": deepseek_state()}

    def test_codex_pressure_uses_worst_window_and_seven_day_default(self):
        state = codex_state(used=25)
        state["windows"].append({"name": "secondary", "used_percent": 60})
        self.providers(state)
        candidate = proxy.codex_candidate("gpt-6-luna", state)
        self.assertAlmostEqual(candidate["pressure"], .4 / (7 * 86400))
        self.assertTrue(candidate["routable"])

    def test_preferred_selects_highest_pressure_but_never_deepseek(self):
        self.token(cooldown=time.time() + 600)
        self.providers(codex_state(used=10))
        result = proxy.route_payload("claude-opus-5-5")
        self.assertEqual(result["preferred"]["provider"], "openai-codex")
        self.providers(codex_state(used=100, allowed=False))
        result = proxy.route_payload("claude-opus-5-5")
        self.assertEqual(result["first_routable"]["provider"], "deepseek")
        self.assertIsNone(result["preferred"])

    def test_sticky_band_and_credit_exclusion(self):
        tok = self.token(u7=.2)
        state = codex_state(used=90)
        self.providers(state)
        result = proxy.route_payload("claude-opus-5-5", current="anthropic")
        self.assertEqual(result["preferred"]["provider"], "anthropic")
        state["credits"] = {"has_credits": True, "overage_limit_reached": False}
        state["windows"][0]["used_percent"] = 100
        state["allowed"] = False
        self.providers(state)
        result = proxy.route_payload("claude-opus-5-5")
        self.assertTrue(result["candidates"][1].get("on_credits"))
        self.assertNotEqual(result["preferred"]["provider"], "openai-codex")

    def test_blocked_codex_is_not_preferred(self):
        self.providers(codex_state(models={"gpt-6-luna": {"available": False}}))
        result = proxy.route_payload("claude-opus-5-5")
        self.assertFalse(result["candidates"][1]["routable"])
        self.assertNotEqual((result["preferred"] or {}).get("provider"), "openai-codex")


if __name__ == "__main__":
    unittest.main()
