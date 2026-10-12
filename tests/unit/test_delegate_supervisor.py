"""Shared scanner must not adopt legacy lanes or mistake a CI watch for completion."""
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config/pi/skills/delegate/scripts/supervise-children.py"


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        loader = importlib.machinery.SourceFileLoader("supervisor", str(PATH))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.mod = importlib.util.module_from_spec(spec)
        loader.exec_module(self.mod)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / "lanes"
        self.registry.mkdir()
        self.mailbox = self.root / "mailbox"
        self.mailbox.mkdir()
        self.sent = []
        self.pane = "1.0%/1.0M\n⠁ Working"
        self.now = 1000

    def lane(self, name, supervisor=True):
        path = self.registry / (name + ".json")
        path.write_text(json.dumps({"run_id": name, "status": "open", "watcher": "supervisor" if supervisor else "legacy",
            "session": "s", "window": name, "window_id": "@42", "parent": "%8", "parent_pane": "%8",
            "created_at": "1970-01-01T00:15:00Z", "cwd": str(self.root), "task": name, "goal": "/goal test"}))
        return path

    def scan(self):
        with patch.object(self.mod, "capture", side_effect=lambda *args: self.pane), \
             patch.object(self.mod, "window_exists", return_value=True), \
             patch.object(self.mod, "send", side_effect=lambda target, message: self.sent.append((target, message))), \
             patch.object(self.mod, "watchdog", return_value=False), \
             patch.object(self.mod, "now", side_effect=lambda: self.now):
            self.mod.scan(self.registry, self.mailbox)

    def test_legacy_not_adopted_and_goal_before_completion(self):
        self.lane("old", False)
        path = self.lane("new")
        self.scan()
        self.assertEqual(len(self.sent), 0)
        self.pane = "1.0%/1.0M\nidle"
        for _ in range(3):
            self.now += 20
            self.scan()
        self.assertEqual(self.sent, [("s:new", "/goal test")])
        self.assertEqual(json.loads(path.read_text())["status"], "open")
        for _ in range(3):
            self.now += 20
            self.scan()
        self.assertEqual(json.loads(path.read_text())["status"], "closed")
        self.assertEqual(len(list(self.mailbox.glob("*.md"))), 1)

    def test_ci_wait_is_not_finished(self):
        path = self.lane("ci")
        self.pane = "1.0%/1.0M\nci_wait registered"
        for _ in range(4):
            self.now += 20
            self.scan()
        self.assertEqual(json.loads(path.read_text())["status"], "open")
        records = list(self.mailbox.glob("*.md"))
        self.assertEqual(len(records), 1)
        self.assertIn("waiting on CI", records[0].read_text())
        self.assertEqual(self.sent, [])

    def test_ci_wait_then_result_closes(self):
        path = self.lane("ci")
        self.pane = "1.0%/1.0M\nci_wait registered"
        for _ in range(3):
            self.now += 20
            self.scan()
        self.assertEqual(json.loads(path.read_text())["status"], "open")
        self.pane = "1.0%/1.0M\nci: DONE abcdef1 - /report ci:123"
        for _ in range(3):
            self.now += 20
            self.scan()
        lane = json.loads(path.read_text())
        self.assertEqual(lane["result_status"], "DONE")
        self.assertEqual(lane["result_sha"], "abcdef1")
        self.assertEqual(lane["result_path"], "/report")
        self.assertEqual(lane["status"], "closed")

    def test_older_children_are_polled_every_minute(self):
        path = self.lane("old-age")
        lane = json.loads(path.read_text())
        lane["created_at"] = "1970-01-01T00:00:00Z"
        path.write_text(json.dumps(lane))
        self.scan()
        state_path = self.mailbox / "supervisor/old-age.json"
        self.assertEqual(json.loads(state_path.read_text())["next_poll"], self.now + 60)

    def test_ack_stops_renudge(self):
        self.lane("done")
        self.pane = "1.0%/1.0M\ndone: PASS none - /report"
        for _ in range(3):
            self.now += 20
            self.scan()
        self.now += 400
        with patch.object(self.mod, "parent_exists", return_value=True):
            self.scan()
        self.assertEqual(len(self.sent), 1)
        record = next(self.mailbox.glob("*.md"))
        (self.mailbox / "ack").mkdir(exist_ok=True)
        record.rename(self.mailbox / "ack" / record.name)
        self.now += 400
        with patch.object(self.mod, "parent_exists", return_value=True):
            self.scan()
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
