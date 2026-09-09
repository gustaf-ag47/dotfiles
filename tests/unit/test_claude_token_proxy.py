#!/usr/bin/env python3
"""Regression tests for the dependency-free Claude token proxy."""

from datetime import datetime, timedelta, timezone
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

    def test_exclude_and_cooldown_still_respected(self):
        reset = iso_in(hours=6)
        best = self.make("a", u7=0.1, u7_reset=reset)
        cooling = self.make("b", u7=0.2, u7_reset=reset)
        cooling.cooldown_until = __import__("time").time() + 300
        last = self.make("c", u7=0.9, u7_reset=reset)
        self.assertIs(proxy.pick(exclude={best.fp}, model="claude-opus-5"), last)


if __name__ == "__main__":
    main()
