"""Task-class quota ceilings, class oracle and explicit escalation."""
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.unit.test_claude_token_proxy import OracleFixture, codex_state, deepseek_state
from tests.unit import test_claude_token_proxy as proxy_tests

proxy = proxy_tests.proxy


class TaskClassesTests(OracleFixture):
    def setUp(self):
        super().setUp()
        self.tmp = TemporaryDirectory()
        self.old_classes = (proxy.CLASSES_FILE, proxy.CLASSES_MTIME, proxy.CLASSES, proxy.CLASSES_ERROR)
        proxy.CLASSES_FILE = Path(self.tmp.name) / "classes.json"
        proxy.CLASSES_MTIME = None
        proxy.CLASSES = {}
        proxy.CLASSES_FILE.write_text(json.dumps({
            "interactive": {"routes": [["anthropic", "claude-fable-5"]]},
            "build": {"routes": [["anthropic", "claude-fable-5"]], "ceiling": {"anthropic": {"no_oi": True, "oi_max_used": .7}}},
            "mechanical": {"routes": [["deepseek", "deepseek-flash"], ["anthropic", "claude-haiku-4-5"]], "ceiling": {"anthropic": {"no_oi": True}}},
        }))

    def tearDown(self):
        self.tmp.cleanup()
        proxy.CLASSES_FILE, proxy.CLASSES_MTIME, proxy.CLASSES, proxy.CLASSES_ERROR = self.old_classes
        super().tearDown()

    def test_class_ceiling_excludes_high_oi_pool_but_interactive_is_unchanged(self):
        tok = self.token()
        tok.u7_oi = .8
        tok.u7_oi_reset = proxy.datetime.now(proxy.timezone.utc).isoformat()
        self.assertIs(proxy.pick(model="claude-fable-5", class_name="interactive"), tok)
        self.assertIsNone(proxy.pick(model="claude-fable-5", class_name="build"))
        ranked = proxy.rank_pool("claude-fable-5", class_name="build")
        self.assertEqual(ranked["ranking"][0]["reason"], "class ceiling")

    def test_mechanical_prefers_routable_deepseek_first(self):
        self.token(cooldown=time.time() + 600)
        proxy.PROVIDER_STATE = {"deepseek": deepseek_state(), "openai-codex": codex_state()}
        route = proxy.route_payload("", class_name="mechanical")
        self.assertEqual(route["first_routable"]["provider"], "deepseek")
        self.assertEqual(route["preferred"]["provider"], "deepseek")
        self.assertEqual(route["class"], "mechanical")

    def test_escalation_header_records_event_and_lifts_one_tier(self):
        events = []
        with patch.object(proxy, "append_route", events.append):
            target = proxy.escalated_class("mechanical", "test-session")
        self.assertEqual(target, "research")
        self.assertEqual(events[0]["kind"], "escalate")
        self.assertEqual(events[0]["class"], "mechanical")
        self.assertEqual(events[0]["to"], "research")
        self.assertEqual(events[0]["session"], "test-session")

    def test_class_model_oracle_does_not_change_model_oracle(self):
        self.token(cooldown=time.time() + 600)
        proxy.PROVIDER_STATE = {"deepseek": deepseek_state(), "openai-codex": codex_state()}
        self.assertIsNone(proxy.route_payload("not-a-model"))
        self.assertIsNone(proxy.route_payload("", class_name="unknown"))


if __name__ == "__main__":
    unittest.main()
