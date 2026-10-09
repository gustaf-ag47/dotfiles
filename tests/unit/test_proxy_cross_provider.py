"""Cross-provider EDF oracle behavior, isolated from the main proxy suite."""
import time
import unittest

from tests.unit.test_claude_token_proxy import OracleFixture, codex_state, deepseek_state
from tests.unit import test_claude_token_proxy as proxy_tests

proxy = proxy_tests.proxy


class SweepTests(OracleFixture):
    def test_sweep_boosts_pick_and_preview_without_5h_stall(self):
        now = time.time()
        a = self.token(u7=.60)
        b = self.token(name="other-token", u7=.20)
        a.u7_reset = b.u7_reset = proxy.datetime.fromtimestamp(now + 3600, proxy.timezone.utc).isoformat()
        a.u5 = b.u5 = .1
        a.u5_reset = b.u5_reset = proxy.datetime.fromtimestamp(now + 3600, proxy.timezone.utc).isoformat()
        proxy.SAMPLES[a.fp] = {"7d": [[now - 3600, .58], [now, .60]]}
        proxy.SWEEP_BOOST = 4
        self.addCleanup(setattr, proxy, "SWEEP_BOOST", 2.0)
        self.assertEqual(proxy.sweep_factor(a, "base", now), 4)
        self.assertEqual(proxy.sweep_factor(b, "base", now), 1)
        preview = proxy.rank_pool("claude-opus-5", now)
        self.assertTrue(next(r for r in preview["ranking"] if r["fp"] == a.fp)["sweep"])
        self.assertEqual(preview["would_pick"], proxy.pick(model="claude-opus-5").fp)
        a.u5 = .99
        self.assertEqual(proxy.sweep_factor(a, "base", now), 1)

    def test_codex_short_window_limits_weekly_sweep(self):
        now = time.time()
        state = codex_state(used=40)
        state["windows"][0].update(reset_at=now + 3600, window_seconds=604800)
        state["windows"].append({"name": "secondary_window", "used_percent": 95,
                                 "reset_at": now + 1800, "window_seconds": 18000})
        state["forecast"] = {"primary_window": {"forecast": "waste"}}
        candidate = proxy.codex_candidate("gpt-6-luna", state)
        self.assertAlmostEqual(candidate["pressure"], min(.6 / 3600 * 2, .05 / 1800))
        state["windows"][1]["used_percent"] = 99
        candidate = proxy.codex_candidate("gpt-6-luna", state)
        self.assertAlmostEqual(candidate["pressure"], min(.6 / 3600, .01 / 1800))


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

    def test_route_candidates_expose_safe_observation_freshness(self):
        self.token(cooldown=time.time() + 600)
        state = codex_state(used=10)
        state["source"] = "ChatGPT Codex wham/usage (private endpoint)"
        state["checked_at"] = int(time.time()) - 7
        self.providers(state)
        result = proxy.route_payload("claude-opus-5-5")
        self.assertEqual(result["candidates"][0]["source"], "local Anthropic proxy observation")
        self.assertEqual(result["candidates"][1]["source"], state["source"])
        self.assertGreaterEqual(result["candidates"][1]["age_seconds"], 7)
        self.assertEqual(result["candidates"][0]["reason"], "cooldown")
        self.assertEqual(result["candidates"][1]["reason"], None)

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
        self.token(u7=.2)
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
        self.token(cooldown=time.time() + 600)
        self.providers(codex_state(models={"gpt-6-luna": {"available": False}}))
        result = proxy.route_payload("claude-opus-5-5")
        self.assertFalse(result["candidates"][1]["routable"])
        self.assertNotEqual((result["preferred"] or {}).get("provider"), "openai-codex")

    def test_credits_routable_codex_is_still_excluded_from_preferred(self):
        self.token(cooldown=time.time() + 600)
        state = codex_state(used=100, allowed=False)
        state["credits"] = {"has_credits": True, "unlimited": False, "overage_limit_reached": False}
        self.providers(state)
        result = proxy.route_payload("claude-opus-5-5")
        self.assertTrue(result["candidates"][1]["routable"])
        self.assertTrue(result["candidates"][1]["on_credits"])
        self.assertNotEqual((result["preferred"] or {}).get("provider"), "openai-codex")

    def test_fable_codex_quality_gate_allows_astra_not_sol(self):
        self.token(cooldown=time.time() + 600)
        state = codex_state(used=10)
        routes = {"claude-fable-5-1": [["openai-codex", "gpt-6-astra"],
                  ["openai-codex", "gpt-6-sol"], ["deepseek", "deepseek-v4-pro"]]}
        proxy.ROUTES_FILE.write_text(__import__("json").dumps(routes))
        proxy.ROUTES, proxy.ROUTES_MTIME = {}, None
        proxy.load_routes()
        self.providers(state)
        result = proxy.route_payload("claude-fable-5-1")
        self.assertEqual(result["preferred"]["model"], "gpt-6-astra")
        self.assertEqual(result["first_routable"]["model"], "gpt-6-astra")
        state["models"] = {"gpt-6-astra": {"available": False}}
        self.providers(state)
        result = proxy.route_payload("claude-fable-5-1")
        self.assertEqual(result["first_routable"]["model"], "gpt-6-sol")
        self.assertNotEqual((result["preferred"] or {}).get("model"), "gpt-6-sol")


if __name__ == "__main__":
    unittest.main()
