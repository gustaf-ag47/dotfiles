#!/usr/bin/env python3
"""Regression tests for the dependency-free Claude token proxy."""

import base64
import http.client
import json
import os
import threading
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main, mock


PROXY_PATH = Path(__file__).parents[2] / "bin" / "claude-token-proxy"
proxy = SourceFileLoader("claude_token_proxy", str(PROXY_PATH)).load_module()


class UsagePersistenceTests(TestCase):
    def setUp(self):
        proxy.STATE.clear()
        proxy.PERSISTENCE_ERROR = None
        self.token = proxy.Tok("test-token")
        proxy.STATE.append(self.token)

    def tearDown(self):
        proxy.STATE.clear()
        proxy.PERSISTENCE_ERROR = None

    def test_persistence_failure_does_not_abort_request_accounting(self):
        with mock.patch.object(
            proxy.Path,
            "mkdir",
            side_effect=OSError(30, "Read-only file system"),
        ):
            proxy.record_request(self.token, "claude-opus-test")

        self.assertEqual(self.token.requests, 1)
        self.assertEqual(self.token.by_model["claude-opus-test"]["requests"], 1)
        self.assertIsNotNone(proxy.PERSISTENCE_ERROR)

    def test_persistence_recovers_after_a_failure(self):
        proxy.PERSISTENCE_ERROR = "previous failure"
        with TemporaryDirectory() as directory:
            proxy.CONTROL_DIR = Path(directory)
            proxy.USAGE_STATE_FILE = proxy.CONTROL_DIR / "usage.json"
            self.assertTrue(proxy.save_usage_state())
            self.assertTrue(proxy.USAGE_STATE_FILE.is_file())

        self.assertIsNone(proxy.PERSISTENCE_ERROR)


def iso_in(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


class PickPolicyTests(TestCase):
    """Selection policy: pressure (EDF-with-headroom), model-aware buckets."""

    def setUp(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        self._mode = proxy.PICK_MODE
        self._dir = TemporaryDirectory()
        # Point the control dir away from the real cache so a leftover
        # force_cooldown file cannot leak into tests.
        self._control = proxy.CONTROL_DIR
        proxy.CONTROL_DIR = Path(self._dir.name)

    def tearDown(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        proxy.PICK_MODE = self._mode
        proxy.CONTROL_DIR = self._control
        self._dir.cleanup()

    def make(self, name, u7=None, u7_reset=None, u7_oi=None, u7_oi_reset=None, u5=None):
        tok = proxy.Tok(name)
        tok.u7, tok.u7_reset = u7, u7_reset
        tok.u7_oi, tok.u7_oi_reset = u7_oi, u7_oi_reset
        tok.u5 = u5
        proxy.STATE.append(tok)
        return tok

    def test_fable_ranks_on_oi_bucket_and_other_models_on_base(self):
        reset = iso_in(days=3)
        exhausted_base = self.make("a", u7=1.0, u7_reset=reset, u7_oi=0.01, u7_oi_reset=reset)
        fresh_base = self.make("b", u7=0.5, u7_reset=reset, u7_oi=0.9, u7_oi_reset=reset)
        self.assertIs(proxy.pick(model="claude-fable-5"), exhausted_base)
        self.assertIs(proxy.pick(model="claude-opus-5"), fresh_base)

    def test_threshold_filters_on_the_governing_bucket(self):
        reset = iso_in(days=3)
        oi_spent = self.make("a", u7=0.1, u7_reset=reset, u7_oi=0.99, u7_oi_reset=reset)
        oi_free = self.make("b", u7=0.9, u7_reset=reset, u7_oi=0.5, u7_oi_reset=reset)
        self.assertIs(proxy.pick(model="claude-fable-5"), oi_free)
        self.assertIs(proxy.pick(model="claude-sonnet-5"), oi_spent)

    def test_equal_headroom_prefers_the_soonest_reset(self):
        soon = self.make("a", u7=0.5, u7_reset=iso_in(hours=6))
        late = self.make("b", u7=0.5, u7_reset=iso_in(days=6))
        self.assertIs(proxy.pick(model="claude-opus-5"), soon)
        self.assertIsNotNone(late)

    def test_pressure_beats_naive_edf_when_soon_token_is_drained(self):
        # 3% headroom expiring in 5d loses to 80% headroom expiring in 6d:
        # raw EDF would pick the drained one, pressure does not.
        drained_soon = self.make("a", u7=0.97, u7_reset=iso_in(days=5))
        full_late = self.make("b", u7=0.2, u7_reset=iso_in(days=6))
        self.assertIsNotNone(drained_soon)
        self.assertIs(proxy.pick(model="claude-opus-5"), full_late)

    def test_sticky_keeps_previous_token_within_tolerance(self):
        reset = iso_in(days=3)
        slightly_better = self.make("a", u7=0.5, u7_reset=reset)
        previous = self.make("b", u7=0.6, u7_reset=reset)
        proxy.LAST_PICK["base"] = previous.fp
        # 0.5/0.4 = 1.25x gap < 1.5 tolerance -> stay for the prompt cache.
        self.assertIs(proxy.pick(model="claude-opus-5"), previous)
        self.assertIsNotNone(slightly_better)

    def test_sticky_yields_when_gap_exceeds_tolerance(self):
        reset = iso_in(days=3)
        much_better = self.make("a", u7=0.1, u7_reset=reset)
        previous = self.make("b", u7=0.9, u7_reset=reset)
        proxy.LAST_PICK["base"] = previous.fp
        self.assertIs(proxy.pick(model="claude-opus-5"), much_better)

    def test_legacy_headroom_mode_is_bucket_blind(self):
        proxy.PICK_MODE = "headroom"
        lowest_u7 = self.make("a", u7=0.2, u7_reset=iso_in(days=6))
        pressure_choice = self.make("b", u7=0.3, u7_reset=iso_in(hours=6))
        self.assertIs(proxy.pick(model="claude-fable-5"), lowest_u7)
        self.assertIsNotNone(pressure_choice)

    def test_unknown_oi_bucket_counts_as_full_headroom(self):
        never_seen = self.make("a")  # no headers observed yet
        known = self.make("b", u7_oi=0.5, u7_oi_reset=iso_in(days=6))
        self.assertIsNotNone(known)
        self.assertIs(proxy.pick(model="claude-fable-5"), never_seen)

    def test_all_cooling_returns_none_until_earliest_cooldown_expires(self):
        first = self.make("gs", u7=0.64)
        first.cooldown_until = 1060
        exhausted = self.make("exhausted", u7=1.0)
        exhausted.cooldown_until = 2000
        for mode in ("pressure", "headroom"):
            with self.subTest(mode=mode), mock.patch.object(proxy, "PICK_MODE", mode):
                with mock.patch.object(proxy.time, "time", return_value=1000):
                    self.assertIsNone(proxy.pick(model="claude-opus-5"))
                with mock.patch.object(proxy.time, "time", return_value=1060):
                    self.assertIs(proxy.pick(model="claude-opus-5"), first)

    def test_excluded_available_token_does_not_fall_back_to_cooling_token(self):
        available = self.make("available", u7=0.64)
        cooling = self.make("cooling", u7=1.0)
        cooling.cooldown_until = 2000
        with mock.patch.object(proxy.time, "time", return_value=1000):
            self.assertIsNone(proxy.pick(exclude={available.fp}))

    def test_over_threshold_without_cooldown_remains_pickable(self):
        # Header observations may be stale; the threshold remains a preference,
        # unlike an explicit upstream cooldown.
        token = self.make("near-limit", u7=0.99)
        self.assertIs(proxy.pick(model="claude-opus-5"), token)

    def test_opaque_429_does_not_fail_over_to_cooling_accounts(self):
        import io
        from email.message import Message

        available = self.make("gs", u7=0.64)
        cooling = self.make("exhausted", u7=1.0)
        cooling.cooldown_until = 2000
        body = b'{"model":"claude-opus-5"}'
        handler = object.__new__(proxy.Handler)
        handler.command = "POST"
        handler.path = "/v1/messages"
        handler.headers = Message()
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler._send_api_error = mock.Mock()
        handler._stream = mock.Mock()
        response = mock.Mock(status=429, headers=Message())
        connection = mock.Mock()
        with mock.patch.object(proxy.time, "time", return_value=1000), \
                mock.patch.object(proxy, "save_usage_state"), \
                mock.patch.object(proxy, "upstream", return_value=(connection, response)) as upstream:
            handler._proxy()

        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(upstream.call_args.args[4], available.token)
        self.assertEqual(available.cooldown_until, 1060)
        self.assertEqual(cooling.cooldown_until, 2000)
        connection.close.assert_called_once()
        handler._stream.assert_not_called()
        self.assertEqual(handler._send_api_error.call_args.args[0], 503)
        self.assertIn("cooldown until", handler._send_api_error.call_args.args[1])

    def test_fable_quota_429_does_not_block_opus_or_get_cleared_by_opus(self):
        import io
        from email.message import Message

        token = self.make("gs", u7=0.64)
        headers = Message()
        headers["Retry-After"] = "600"
        headers["anthropic-ratelimit-unified-status"] = "rejected"
        headers["anthropic-ratelimit-unified-representative-claim"] = "seven_day_overage_included"
        headers["anthropic-ratelimit-unified-7d_oi-utilization"] = "1.0"
        responses = [mock.Mock(status=429, headers=headers),
                     mock.Mock(status=200, headers=Message())]
        connection = mock.Mock()
        with mock.patch.object(proxy.time, "time", return_value=1000), \
                mock.patch.object(proxy, "save_usage_state"), \
                mock.patch.object(proxy, "upstream", side_effect=[(connection, r) for r in responses]) as upstream:
            for model in ("claude-fable-5", "claude-opus-5"):
                body = ('{"model":"' + model + '"}').encode()
                handler = object.__new__(proxy.Handler)
                handler.command = "POST"
                handler.path = "/v1/messages"
                handler.headers = Message()
                handler.headers["Content-Length"] = str(len(body))
                handler.rfile = io.BytesIO(body)
                handler._send_api_error = mock.Mock()
                handler._stream = mock.Mock()
                handler._proxy()
                if model == "claude-fable-5":
                    self.assertIsNone(proxy.pick(model=model))
                    self.assertIs(proxy.pick(model="claude-opus-5"), token)
                else:
                    handler._stream.assert_called_once()
                    handler._send_api_error.assert_not_called()
            self.assertEqual(upstream.call_count, 2)
            self.assertIsNone(proxy.pick(model="claude-fable-5"))
            self.assertIs(proxy.pick(model="claude-opus-5"), token)
        with mock.patch.object(proxy.time, "time", return_value=1600):
            self.assertIs(proxy.pick(model="claude-fable-5"), token)

    def test_exclude_and_cooldown_still_respected(self):
        reset = iso_in(hours=6)
        best = self.make("a", u7=0.1, u7_reset=reset)
        cooling = self.make("b", u7=0.2, u7_reset=reset)
        cooling.cooldown_until = __import__("time").time() + 300
        last = self.make("c", u7=0.9, u7_reset=reset)
        self.assertIs(proxy.pick(exclude={best.fp}, model="claude-opus-5"), last)


class CooldownScopeTests(TestCase):
    def test_explicit_model_claims_are_scoped(self):
        for claim, scope in (("seven_day_overage_included", "fable"),
                             ("five_hour_overage_included", "fable"),
                             ("seven_day_opus", "opus"),
                             ("seven_day_sonnet", "sonnet")):
            with self.subTest(claim=claim):
                self.assertEqual(proxy.quota_cooldown_scope({
                    "anthropic-ratelimit-unified-status": "rejected",
                    "anthropic-ratelimit-unified-representative-claim": claim,
                }), scope)

    def test_shared_unknown_and_burst_limits_remain_account_wide(self):
        for headers in ({}, {"retry-after": "60"}, {
            "anthropic-ratelimit-unified-status": "rejected",
            "anthropic-ratelimit-unified-representative-claim": "seven_day",
            "anthropic-ratelimit-unified-7d_oi-utilization": "1.0",
        }, {
            "anthropic-ratelimit-unified-status": "allowed",
            "anthropic-ratelimit-unified-representative-claim": "seven_day_overage_included",
            "anthropic-ratelimit-unified-7d_oi-utilization": "0.5",
        }):
            with self.subTest(headers=headers):
                self.assertIsNone(proxy.quota_cooldown_scope(headers))

    def test_per_bucket_rejection_without_representative_claim(self):
        self.assertEqual(proxy.quota_cooldown_scope({
            "Anthropic-RateLimit-Unified-7d_oi-Status": "Rejected",
        }), "fable")
        self.assertIsNone(proxy.quota_cooldown_scope({
            "anthropic-ratelimit-unified-7d_oi-status": "rejected",
            "anthropic-ratelimit-unified-7d-status": "rejected",
        }))

    def test_applying_cooldown_never_shortens_existing_deadline(self):
        token = proxy.Tok("synthetic")
        token.cooldown_until = 2000
        with mock.patch.object(proxy.time, "time", return_value=1000):
            proxy.apply_cooldown(token, {"retry-after": "1"})
        self.assertEqual(token.cooldown_until, 2000)

    def test_snapshot_exposes_only_active_model_cooldowns(self):
        token = proxy.Tok("synthetic")
        token.model_cooldowns = {"fable": 2000, "opus": 900}
        with mock.patch.object(proxy.time, "time", return_value=1000), \
                mock.patch.object(proxy, "forced_cooldown_fps", return_value=set()):
            snapshot = token.snapshot()
        self.assertEqual(set(snapshot["model_cooldowns"]), {"fable"})
        self.assertEqual(snapshot["cooldown_remaining"], 0)


class Burst429Tests(TestCase):
    """A spent bucket must rotate; a per-minute burst must just wait."""

    def test_account_level_rejected_is_quota(self):
        self.assertEqual(
            proxy.classify_429({"anthropic-ratelimit-unified-status": "rejected"}),
            "quota",
        )

    def test_per_bucket_rejected_is_quota(self):
        for header in ("anthropic-ratelimit-unified-7d-status",
                       "anthropic-ratelimit-unified-7d_oi-status",
                       "anthropic-ratelimit-unified-overage-status"):
            with self.subTest(header=header):
                self.assertEqual(proxy.classify_429({header: "rejected"}), "quota")

    def test_representative_claim_at_full_utilization_is_quota(self):
        headers = {
            "anthropic-ratelimit-unified-representative-claim": "seven_day_overage_included",
            "anthropic-ratelimit-unified-7d_oi-utilization": "1.0",
        }
        self.assertEqual(proxy.classify_429(headers), "quota")

    def test_allowed_status_is_burst(self):
        headers = {
            "anthropic-ratelimit-unified-status": "allowed_warning",
            "anthropic-ratelimit-unified-representative-claim": "seven_day",
            "anthropic-ratelimit-unified-7d-utilization": "0.42",
        }
        self.assertEqual(proxy.classify_429(headers), "burst")

    def test_absent_ratelimit_headers_are_burst(self):
        self.assertEqual(proxy.classify_429({}), "burst")
        self.assertEqual(proxy.classify_429({"retry-after": "5"}), "burst")

    def test_header_case_does_not_matter(self):
        self.assertEqual(
            proxy.classify_429({"Anthropic-RateLimit-Unified-Status": "Rejected"}),
            "quota",
        )

    def test_burst_within_cap_is_paced(self):
        self.assertEqual(proxy.burst_pause_seconds({"retry-after": "7"}, cap=15), 7.0)

    def test_burst_over_cap_is_not_paced(self):
        self.assertIsNone(proxy.burst_pause_seconds({"retry-after": "60"}, cap=15))

    def test_quota_429_is_never_paced(self):
        headers = {"retry-after": "5", "anthropic-ratelimit-unified-status": "rejected"}
        self.assertIsNone(proxy.burst_pause_seconds(headers, cap=15))

    def test_missing_retry_after_is_not_paced(self):
        self.assertIsNone(proxy.burst_pause_seconds({}, cap=15))

    def test_zero_cap_disables_pacing(self):
        self.assertIsNone(proxy.burst_pause_seconds({"retry-after": "1"}, cap=0))

    def test_cap_defaults_to_the_env_knob(self):
        with mock.patch.object(proxy, "BURST_WAIT_MAX", 3):
            self.assertEqual(proxy.burst_pause_seconds({"retry-after": "2"}), 2.0)
            self.assertIsNone(proxy.burst_pause_seconds({"retry-after": "9"}))

    def test_http_message_headers_are_accepted(self):
        from email.message import Message

        message = Message()
        message["Retry-After"] = "4"
        message["anthropic-ratelimit-unified-status"] = "allowed"
        self.assertEqual(proxy.classify_429(message), "burst")
        self.assertEqual(proxy.burst_pause_seconds(message, cap=15), 4.0)


ROUTES = {
    "claude-fable-5-1": [["openai-codex", "gpt-6-astra"], ["deepseek", "deepseek-v4-pro"]],
    "claude-opus-5-5": [["openai-codex", "gpt-6-luna"], ["deepseek", "deepseek-v4-pro"]],
    "claude-sonnet-5": [["openai-codex", "gpt-6-sol"], ["deepseek", "deepseek-flash"]],
}
ANTHROPIC_CANARY = "sk-ant-oat01-CANARYANTHROPICTOKENVALUE"
CODEX_CANARY = "CANARYCODEXACCESSTOKENVALUE"
DEEPSEEK_CANARY = "sk-CANARYDEEPSEEKKEYVALUE"


def fake_jwt(payload: dict, canary: str = CODEX_CANARY) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.{canary}"


def fake_auth(expires_ms=None) -> dict:
    token = fake_jwt({"https://api.openai.com/profile": {"email": "a@b"},
                      "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}})
    return {"openai-codex": {"type": "oauth", "access": token, "refresh": "CANARYREFRESH",
                             "expires": expires_ms if expires_ms is not None else (time.time() + 3600) * 1000,
                             "accountId": "acct-1"},
            "deepseek": {"type": "api_key", "key": DEEPSEEK_CANARY}}


def codex_state(used=30, allowed=True, models=None):
    return {"status": "ok", "kind": "subscription quota", "account": {"email": "a@b", "plan": "plus"},
            "windows": [{"name": "primary_window", "used_percent": used, "window_seconds": 604800,
                         "reset_at": int(time.time()) + 86400}],
            "allowed": allowed, "limit_reached": not allowed, "models": models or {}, "checked_at": 1}


def deepseek_state(balance="5.00", available=True):
    return {"status": "ok", "kind": "prepaid balance", "label": "key \u2026VALU", "available": available,
            "balances": [{"currency": "USD", "total_balance": balance, "granted_balance": "0.00",
                          "topped_up_balance": balance}], "checked_at": 1}


class OracleFixture(TestCase):
    """Isolated pool, routes file and provider cache for the oracle tests."""

    def setUp(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        self._dir = TemporaryDirectory()
        self._saved = {name: getattr(proxy, name) for name in
                       ("CONTROL_DIR", "ROUTES_FILE", "ROUTES", "ROUTES_MTIME", "ROUTES_ERROR", "PROVIDER_STATE")}
        proxy.CONTROL_DIR = Path(self._dir.name)
        proxy.ROUTES_FILE = Path(self._dir.name) / "routes.json"
        proxy.ROUTES_FILE.write_text(json.dumps(ROUTES))
        proxy.ROUTES, proxy.ROUTES_MTIME, proxy.ROUTES_ERROR = {}, None, None
        proxy.PROVIDER_STATE = {"openai-codex": {"status": "unavailable", "reason": "not polled yet"},
                                "deepseek": {"status": "unavailable", "reason": "not polled yet"}}

    def tearDown(self):
        proxy.STATE.clear()
        proxy.LAST_PICK.clear()
        for name, value in self._saved.items():
            setattr(proxy, name, value)
        self._dir.cleanup()

    def token(self, name=ANTHROPIC_CANARY, u7=0.4, cooldown=0.0):
        tok = proxy.Tok(name)
        tok.u7, tok.u7_reset = u7, iso_in(days=2)
        tok.cooldown_until = cooldown
        proxy.STATE.append(tok)
        return tok


class RoutesTableTests(OracleFixture):
    def test_loads_and_matches_by_prefix(self):
        self.assertEqual(proxy.route_key("claude-opus-5-5-20260901"), "claude-opus-5-5")
        self.assertEqual(proxy.route_key("claude-opus-5-5"), "claude-opus-5-5")
        self.assertEqual(proxy.route_key("claude-fable-5"), "claude-fable-5-1")  # nearest fable row
        self.assertEqual(proxy.route_key("Claude-Sonnet-5"), "claude-sonnet-5")
        self.assertIsNone(proxy.route_key("gpt-6-luna"))
        self.assertIsNone(proxy.route_key(""))
        self.assertEqual(proxy.ROUTES["claude-opus-5-5"][0], ["openai-codex", "gpt-6-luna"])

    def test_reloads_on_mtime_change_and_keeps_last_good_table(self):
        proxy.load_routes()
        self.assertIn("claude-opus-5-5", proxy.ROUTES)
        proxy.ROUTES_FILE.write_text(json.dumps({"claude-haiku-4-5": [["deepseek", "deepseek-flash"]]}))
        os.utime(proxy.ROUTES_FILE, (time.time() + 5, time.time() + 5))
        self.assertEqual(sorted(proxy.load_routes()), ["claude-haiku-4-5"])
        proxy.ROUTES_FILE.write_text("{not json")
        os.utime(proxy.ROUTES_FILE, (time.time() + 10, time.time() + 10))
        self.assertEqual(sorted(proxy.load_routes()), ["claude-haiku-4-5"])
        self.assertIsNotNone(proxy.ROUTES_ERROR)

    def test_unknown_model_yields_no_payload(self):
        self.assertIsNone(proxy.route_payload("gpt-6-luna"))


class RouteRankingTests(OracleFixture):
    def providers(self, codex, deepseek):
        proxy.PROVIDER_STATE = {"openai-codex": codex, "deepseek": deepseek}

    def test_all_routable_prefers_anthropic_then_table_order(self):
        tok = self.token()
        self.providers(codex_state(), deepseek_state())
        out = proxy.route_payload("claude-opus-5-5-20260901")
        self.assertEqual([c["provider"] for c in out["candidates"]], ["anthropic", "openai-codex", "deepseek"])
        self.assertEqual([c["model"] for c in out["candidates"]],
                         ["claude-opus-5-5-20260901", "gpt-6-luna", "deepseek-v4-pro"])
        self.assertTrue(all(c["routable"] for c in out["candidates"]))
        self.assertEqual(out["first_routable"]["provider"], "anthropic")
        self.assertEqual(out["first_routable"]["account"], tok.fp)
        self.assertEqual(out["first_routable"]["quota_left_percent"], 60.0)
        self.assertEqual(out["candidates"][1]["quota_left_percent"], 70.0)
        self.assertEqual(out["candidates"][2]["balance"], 5.0)
        self.assertEqual(proxy.LAST_PICK, {})  # pure: the sticky pick was not touched

    def test_anthropic_cooling_falls_to_codex(self):
        self.token(cooldown=time.time() + 600)
        self.providers(codex_state(), deepseek_state())
        out = proxy.route_payload("claude-opus-5-5")
        anthropic = out["candidates"][0]
        self.assertFalse(anthropic["routable"])
        self.assertEqual(anthropic["reason"], "cooldown")
        self.assertIsNotNone(anthropic["reset_at"])
        self.assertEqual(out["first_routable"]["provider"], "openai-codex")

    def test_codex_exhausted_falls_to_deepseek(self):
        self.token(cooldown=time.time() + 600)
        self.providers(codex_state(used=100, allowed=False), deepseek_state())
        out = proxy.route_payload("claude-sonnet-5")
        codex = out["candidates"][1]
        self.assertEqual((codex["routable"], codex["reason"], codex["quota_left_percent"]), (False, "exhausted", 0.0))
        self.assertEqual(out["first_routable"]["provider"], "deepseek")
        self.assertEqual(out["first_routable"]["model"], "deepseek-flash")

    def test_codex_credits_keep_it_routable_after_window_spent(self):
        """Bought credits serve past the weekly window; a blocked model still is not."""
        self.token(cooldown=time.time() + 600)
        state = codex_state(used=100, allowed=False,
                            models={"gpt-6-astra": {"available": False, "credits_would_enable": False}})
        state["credits"] = {"balance": "12.50", "has_credits": True, "unlimited": False, "overage_limit_reached": False}
        self.providers(state, deepseek_state())
        opus = proxy.route_payload("claude-opus-5-5")
        self.assertEqual((opus["candidates"][1]["routable"], opus["candidates"][1].get("on_credits")), (True, True))
        self.assertEqual(opus["first_routable"]["provider"], "openai-codex")
        fable = proxy.route_payload("claude-fable-5-1")["candidates"][1]
        self.assertEqual((fable["routable"], fable["reason"]), (False, "exhausted"))
        state["credits"]["overage_limit_reached"] = True
        self.providers(state, deepseek_state())
        self.assertFalse(proxy.route_payload("claude-opus-5-5")["candidates"][1]["routable"])

    def test_codex_model_block_is_per_model(self):
        self.providers(codex_state(models={"gpt-6-astra": {"available": False, "available_at": "2026-09-30T14:38:22Z",
                                                            "credits_would_enable": True}}), deepseek_state())
        fable = proxy.route_payload("claude-fable-5-1")["candidates"][1]
        self.assertEqual((fable["routable"], fable["reason"], fable["reset_at"]),
                         (False, "model unavailable", "2026-09-30T14:38:22Z"))
        self.assertTrue(proxy.route_payload("claude-opus-5-5")["candidates"][1]["routable"])

    def test_deepseek_below_floor_leaves_nothing_routable(self):
        self.token(u7=0.99)  # over threshold -> exhausted
        self.providers(codex_state(used=100), deepseek_state(balance="0.50"))
        out = proxy.route_payload("claude-opus-5-5")
        self.assertIsNone(out["first_routable"])
        self.assertEqual([c["reason"] for c in out["candidates"]], ["exhausted", "exhausted", "balance below floor"])
        self.providers(codex_state(used=100), deepseek_state(balance="-0.12", available=False))
        self.assertEqual(proxy.route_payload("claude-opus-5-5")["candidates"][2]["reason"], "unavailable")

    def test_empty_pool_and_unpolled_providers_are_explicit(self):
        out = proxy.route_payload("claude-opus-5-5")
        self.assertEqual([c["reason"] for c in out["candidates"]], ["no token", "unknown", "unknown"])
        self.assertIsNone(out["first_routable"])


class ProviderAdapterTests(OracleFixture):
    def test_failing_upstream_degrades_to_unavailable_without_leaking(self):
        with mock.patch.object(proxy, "read_auth", return_value=fake_auth()), \
                mock.patch.object(proxy, "get_json", side_effect=urllib.error.HTTPError(
                    "u", 401, f"bad {CODEX_CANARY}", {}, None)):
            proxy.refresh_providers()
        for name in ("openai-codex", "deepseek"):
            self.assertEqual(proxy.PROVIDER_STATE[name]["status"], "unavailable")
            self.assertIn("HTTP 401", proxy.PROVIDER_STATE[name]["reason"])
            self.assertIsInstance(proxy.PROVIDER_STATE[name]["checked_at"], int)
        with mock.patch.object(proxy, "read_auth", return_value=fake_auth()), \
                mock.patch.object(proxy, "get_json", side_effect=OSError(CODEX_CANARY)):
            proxy.refresh_providers()
        blob = json.dumps(proxy.PROVIDER_STATE)
        self.assertIn("OSError", blob)
        for canary in (CODEX_CANARY, DEEPSEEK_CANARY, "CANARYREFRESH"):
            self.assertNotIn(canary, blob)

    def test_codex_parses_wham_usage_and_jwt_claims(self):
        payload = {"email": "live@b", "plan_type": "pro",
                   "rate_limit": {"allowed": False, "limit_reached": True,
                                  "primary_window": {"used_percent": 100, "limit_window_seconds": 604800, "reset_at": 1790779102},
                                  "secondary_window": None},
                   "model_usage": {"gpt-6-astra": {"available": False, "available_at": "x", "credits_would_enable": True}},
                   "credits": {"balance": "0", "has_credits": False, "unlimited": False, "overage_limit_reached": False},
                   "rate_limit_reached_type": {"type": "rate_limit_reached"}, "user_id": "user-SECRETUSERID"}
        with mock.patch.object(proxy, "get_json", return_value=payload) as get:
            out = proxy.codex(fake_auth())
        self.assertEqual(out["account"], {"email": "live@b", "name": None, "plan": "pro", "account_id": "acct-1"})
        self.assertEqual((out["reset_credits"], out["topup_url"]), (None, proxy.CODEX_TOPUP_URL))
        self.assertEqual(out["windows"][0]["used_percent"], 100)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["models"]["gpt-6-astra"]["credits_would_enable"], True)
        self.assertNotIn("SECRETUSERID", json.dumps(out))
        self.assertEqual(get.call_args.args[1]["ChatGPT-Account-Id"], "acct-1")
        self.assertEqual(proxy.jwt_claims("not-a-jwt"), {"email": None, "plan": None})

    def test_codex_expired_names_account_without_calling_upstream(self):
        with mock.patch.object(proxy, "get_json") as get:
            out = proxy.codex(fake_auth(expires_ms=1))
        get.assert_not_called()
        self.assertEqual(out["status"], "unavailable")
        self.assertIn("a@b", out["reason"])
        self.assertNotIn(CODEX_CANARY, json.dumps(out))

    def test_codex_unknown_shape_is_unavailable_not_zero(self):
        with mock.patch.object(proxy, "get_json", return_value={"rate_limit": {"allowed": True}}):
            out = proxy.codex(fake_auth())
        self.assertEqual(out["status"], "unavailable")
        self.assertFalse(proxy.codex_candidate("gpt-6-luna", out)["routable"])

    def test_deepseek_label_order_and_no_key_command_execution(self):
        auth = fake_auth()
        with mock.patch.dict(os.environ, {"DEEPSEEK_ACCOUNT_LABEL": ""}, clear=False):
            os.environ.pop("DEEPSEEK_ACCOUNT_LABEL", None)
            self.assertEqual(proxy.deepseek_label(auth, DEEPSEEK_CANARY), "key \u2026ALUE")
            auth["deepseek"]["label"] = "me@x"
            self.assertEqual(proxy.deepseek_label(auth, DEEPSEEK_CANARY), "me@x")
            os.environ["DEEPSEEK_ACCOUNT_LABEL"] = "env@x"
            self.assertEqual(proxy.deepseek_label(auth, DEEPSEEK_CANARY), "env@x")
        self.assertIsNone(proxy.deepseek_key({"deepseek": {"type": "api_key", "key": "!secret-tool lookup"}}))
        with mock.patch.object(proxy, "get_json", return_value={"is_available": False, "balance_infos": [
                {"currency": "USD", "total_balance": "-0.12", "granted_balance": "0.00", "topped_up_balance": "-0.12"}]}):
            out = proxy.deepseek(auth)
        self.assertEqual((out["status"], out["available"], out["balances"][0]["total_balance"]), ("ok", False, "-0.12"))
        self.assertNotIn(DEEPSEEK_CANARY[:8], json.dumps(out))


class OracleHttpTests(OracleFixture):
    """Drive the real handler: /_usage and /_route bodies must never carry a credential."""

    def setUp(self):
        super().setUp()
        self.token()
        proxy.PROVIDER_STATE = {"openai-codex": codex_state(), "deepseek": deepseek_state()}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def get(self, path, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, body

    def assert_no_secrets(self, body):
        for canary in (ANTHROPIC_CANARY, CODEX_CANARY, DEEPSEEK_CANARY, "CANARYREFRESH"):
            self.assertNotIn(canary, body)
        self.assertNotIn("sk-ant-oat", body)

    def test_usage_has_providers_block_and_keeps_schema_1_keys(self):
        status, body = self.get("/_usage")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["schema"], 2)
        self.assertIn("tokens", data)
        self.assertIn("routing", data)
        self.assertEqual(sorted(data["providers"]), ["anthropic", "deepseek", "openai-codex"])
        self.assertEqual(data["providers"]["anthropic"]["tokens"], data["tokens"])
        self.assertEqual(data["providers"]["openai-codex"]["status"], "ok")
        self.assert_no_secrets(body)

    def test_route_endpoint(self):
        status, body = self.get("/_route?model=claude-opus-5-5-20260901")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["first_routable"]["provider"], "anthropic")
        self.assertEqual(len(data["candidates"]), 3)
        self.assert_no_secrets(body)

    def test_route_unknown_model_is_404_json(self):
        status, body = self.get("/_route?model=gpt-6-luna")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "unknown model")
        self.assertEqual(self.get("/_route")[0], 404)

    def test_control_endpoints_are_never_forwarded_upstream(self):
        with mock.patch.object(proxy, "upstream", side_effect=AssertionError("must not reach upstream")):
            self.assertEqual(self.get("/_route?model=claude-opus-5-5", method="POST")[0], 405)
            self.assertEqual(self.get("/_usage", method="POST")[0], 405)


class FakeUpstreamResponse:
    """Just enough of http.client.HTTPResponse for Handler._stream()."""

    def __init__(self, status=200, body=b"", content_type="application/json"):
        self.status = status
        self._body = body
        self._headers = [("content-type", content_type), ("x-ds-trace-id", "trace")]
        self.headers = dict(self._headers)

    def getheader(self, name, default=None):
        return dict(self._headers).get(name.lower(), default)

    def getheaders(self):
        return list(self._headers)

    def read(self, n=-1):
        out, self._body = (self._body, b"") if n < 0 else (self._body[:n], self._body[n:])
        return out


class FakeHTTPSConnection:
    """Records the one request DeepSeek would receive; `responses` is a shared queue."""
    calls: list = []
    responses: list = []

    def __init__(self, host, timeout=None):
        self.host = host

    def request(self, method, path, body=None, headers=None):
        FakeHTTPSConnection.calls.append({"host": self.host, "method": method, "path": path,
                                          "body": body, "headers": dict(headers or {})})

    def getresponse(self):
        return FakeHTTPSConnection.responses.pop(0)

    def close(self):
        pass


class DeepseekPassthroughTests(OracleFixture):
    """Opt-in DeepSeek fallback for the real Claude Code CLI (decision 4)."""

    OAUTH_HEADERS = {"content-type": "application/json", "Authorization": f"Bearer {ANTHROPIC_CANARY}",
                     "anthropic-beta": proxy.OAUTH_BETA, "anthropic-version": "2023-06-01",
                     "x-app": "cli", "anthropic-dangerous-direct-browser-access": "true"}

    def setUp(self):
        super().setUp()
        self._fallback = dict(proxy.FALLBACK)
        proxy.FALLBACK.update(active=False, since=None, model=None, claude_model=None,
                              episode_requests=0, requests=0, by_model={})
        proxy.USAGE_STATE_FILE = proxy.CONTROL_DIR / "usage.json"
        proxy.PROVIDER_STATE = {"openai-codex": codex_state(), "deepseek": deepseek_state()}
        FakeHTTPSConnection.calls, FakeHTTPSConnection.responses = [], []
        self.patches = [mock.patch.object(proxy, "DEEPSEEK_FALLBACK", True),
                        mock.patch.object(proxy, "read_auth", return_value=fake_auth()),
                        mock.patch.object(proxy.http.client, "HTTPSConnection", FakeHTTPSConnection),
                        mock.patch.object(proxy, "upstream", side_effect=AssertionError("anthropic must not be called"))]
        self.anthropic = self.patches[-1].start()
        for patch in self.patches[:-1]:
            patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for patch in self.patches:
            patch.stop()
        proxy.FALLBACK.clear()
        proxy.FALLBACK.update(self._fallback)
        super().tearDown()

    def exhausted_token(self):
        return self.token(cooldown=time.time() + 600)

    def post(self, model="claude-opus-5-5-20260901", stream=False, extra_headers=None):
        body = json.dumps({"model": model, "max_tokens": 5, "stream": stream,
                           "messages": [{"role": "user", "content": "hi"}]}).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        conn.request("POST", "/v1/messages?beta=true", body=body,
                     headers={**self.OAUTH_HEADERS, **(extra_headers or {})})
        resp = conn.getresponse()
        out = resp.status, resp.read().decode()
        conn.close()
        return out

    def usage(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        conn.request("GET", "/_usage")
        data = json.loads(conn.getresponse().read())
        conn.close()
        return data

    def test_feature_off_keeps_the_unavailable_message(self):
        self.exhausted_token()
        with mock.patch.object(proxy, "DEEPSEEK_FALLBACK", False):
            status, body = self.post()
            usage = self.usage()
        self.assertEqual(status, 503)
        self.assertIn("no OAuth account can serve", json.loads(body)["error"]["message"])
        self.assertEqual(FakeHTTPSConnection.calls, [])
        self.assertIsNone(usage["routing"]["fallback"])
        self.assertFalse(usage["routing"]["deepseek_fallback"]["enabled"])

    def test_client_opt_out_header_keeps_the_unavailable_message(self):
        """pi's llm-failover extension switches natively; a silent DeepSeek answer
        labelled as Claude would defeat its notify-only contract (decision 3)."""
        self.exhausted_token()
        with mock.patch.object(proxy, "log") as log:
            status, body = self.post(extra_headers={proxy.FALLBACK_OPT_OUT_HEADER: "none"})
        self.assertEqual(status, 503)
        self.assertIn("no OAuth account can serve", json.loads(body)["error"]["message"])
        self.assertEqual(FakeHTTPSConnection.calls, [])
        self.assertIsNone(self.usage()["routing"]["fallback"])
        self.assertIn("client opted out", " ".join(str(c.args[0]) for c in log.call_args_list))

    def test_pool_exhausted_forwards_to_deepseek_with_its_own_key(self):
        self.exhausted_token()
        FakeHTTPSConnection.responses.append(FakeUpstreamResponse(
            200, b'{"type":"message","model":"deepseek-v4-pro","usage":{"input_tokens":7,"output_tokens":3}}'))
        with mock.patch.object(proxy, "log") as log:
            status, body = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["model"], "deepseek-v4-pro")
        self.anthropic.assert_not_called()
        [call] = FakeHTTPSConnection.calls
        self.assertEqual((call["host"], call["method"], call["path"]),
                         ("api.deepseek.com", "POST", "/anthropic/v1/messages?beta=true"))
        headers = {k.lower(): v for k, v in call["headers"].items()}
        self.assertEqual(headers["x-api-key"], DEEPSEEK_CANARY)
        self.assertNotIn("authorization", headers)
        self.assertEqual(headers["host"], "api.deepseek.com")
        sent = json.loads(call["body"])
        self.assertEqual(sent["model"], "deepseek-v4-pro")
        self.assertEqual(sent["messages"], [{"role": "user", "content": "hi"}])
        wire = json.dumps({**call, "body": call["body"].decode()})
        self.assertNotIn(ANTHROPIC_CANARY, wire)
        self.assertNotIn("sk-ant-oat", wire)
        self.assertIn("-> deepseek deepseek-v4-pro (fallback: anthropic pool exhausted)",
                      " ".join(str(c.args[0]) for c in log.call_args_list))
        usage = self.usage()
        fallback = usage["routing"]["fallback"]
        self.assertEqual((fallback["provider"], fallback["model"], fallback["requests"]),
                         ("deepseek", "deepseek-v4-pro", 1))
        self.assertIsNotNone(fallback["since"])
        by_model = usage["routing"]["deepseek_fallback"]["by_model"]["claude-opus-5-5-20260901"]
        self.assertEqual((by_model["requests"], by_model["input_tokens"], by_model["output_tokens"]), (1, 7, 3))
        self.assertEqual(usage["providers"]["anthropic"]["tokens"][0]["counters"]["requests"], 0)
        persisted = json.loads(proxy.USAGE_STATE_FILE.read_text())[proxy.FALLBACK_STATE_KEY]
        self.assertEqual(persisted["by_model"]["claude-opus-5-5-20260901"]["requests"], 1)
        self.assertNotIn(DEEPSEEK_CANARY, json.dumps(usage))

    def test_streaming_response_is_relayed_and_counted(self):
        self.exhausted_token()
        sse = (b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":4}}}\n\n'
               b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":9}}\n\n')
        FakeHTTPSConnection.responses.append(FakeUpstreamResponse(200, sse, "text/event-stream"))
        status, body = self.post(stream=True)
        self.assertEqual(status, 200)
        self.assertEqual(body.encode(), sse)
        bucket = proxy.FALLBACK["by_model"]["claude-opus-5-5-20260901"]
        self.assertEqual((bucket["input_tokens"], bucket["output_tokens"]), (4, 9))

    def test_balance_below_floor_or_unavailable_keeps_unavailable_message(self):
        self.exhausted_token()
        for state in (deepseek_state(balance="0.50"), deepseek_state(balance="-0.12", available=False),
                      {"status": "unavailable", "reason": "not polled yet"}):
            with self.subTest(state=state):
                proxy.PROVIDER_STATE["deepseek"] = state
                status, body = self.post()
                self.assertEqual(status, 503)
                self.assertIn("no OAuth account can serve", body)
        self.assertEqual(FakeHTTPSConnection.calls, [])
        self.assertIsNone(self.usage()["routing"]["fallback"])

    def test_model_without_deepseek_route_is_not_forwarded(self):
        self.exhausted_token()
        proxy.ROUTES_FILE.write_text(json.dumps({"claude-opus-5-5": [["openai-codex", "gpt-6-luna"]]}))
        os.utime(proxy.ROUTES_FILE, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.post()[0], 503)
        self.assertEqual(self.post(model="gpt-6-luna")[0], 503)
        self.assertEqual(FakeHTTPSConnection.calls, [])

    def test_healthy_pool_never_fires(self):
        self.token()
        self.anthropic.side_effect = None
        self.anthropic.return_value = (mock.Mock(), FakeUpstreamResponse(200, b'{"type":"message"}'))
        self.assertEqual(self.post()[0], 200)
        self.assertEqual(self.anthropic.call_count, 1)
        self.assertEqual(self.anthropic.call_args.args[4], ANTHROPIC_CANARY)
        self.assertEqual(FakeHTTPSConnection.calls, [])
        self.assertIsNone(self.usage()["routing"]["fallback"])

    def test_deepseek_402_is_returned_as_is_without_anthropic_retry(self):
        self.exhausted_token()
        error = b'{"error":{"message":"Insufficient Balance","type":"unknown_error"}}'
        FakeHTTPSConnection.responses.append(FakeUpstreamResponse(402, error))
        status, body = self.post()
        self.assertEqual((status, body.encode()), (402, error))
        self.anthropic.assert_not_called()
        self.assertEqual(len(FakeHTTPSConnection.calls), 1)

    def test_episode_clears_when_a_token_is_pickable_again(self):
        tok = self.exhausted_token()
        FakeHTTPSConnection.responses.append(FakeUpstreamResponse(200, b'{"type":"message"}'))
        self.assertEqual(self.post()[0], 200)
        self.assertIsNotNone(self.usage()["routing"]["fallback"])
        tok.cooldown_until = 0.0
        usage = self.usage()
        self.assertIsNone(usage["routing"]["fallback"])
        self.assertFalse(proxy.FALLBACK["active"])
        self.assertEqual(usage["routing"]["deepseek_fallback"]["requests_total"], 1)  # ledger survives

    def test_counters_survive_restart(self):
        proxy.FALLBACK["requests"] = 3
        proxy.FALLBACK["by_model"] = {"claude-sonnet-5": {"requests": 3, "input_tokens": 1, "output_tokens": 2,
                                                          "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
        self.assertTrue(proxy.save_usage_state())
        proxy.FALLBACK.update(requests=0, by_model={})
        proxy.restore_usage_state()
        self.assertEqual(proxy.FALLBACK["requests"], 3)
        self.assertEqual(proxy.FALLBACK["by_model"]["claude-sonnet-5"]["output_tokens"], 2)


if __name__ == "__main__":
    main()
