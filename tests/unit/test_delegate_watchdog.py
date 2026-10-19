"""Stall watchdog decisions use fake panes, GitHub answers, and a fake clock."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader("delegate_watchdog", str(ROOT / "bin/delegate-watchdog"))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "lane.json"
        self.manifest.write_text(json.dumps({"cwd": str(self.root)}))
        self.pr = dict(number=12, url="https://github.com/owner/repo/pull/12", state="OPEN", isDraft=False, mergeStateStatus="DIRTY", headRefOid="a" * 40)
        self.child = "idle"
        self.parent = "idle"
        self.sent = []
        self.clock = 1000
        self.checks = []
        self.start(patch.dict(os.environ, {"PI_DELEGATE_MAILBOX": str(self.root / "mailbox"), "PI_DELEGATE_STALL_POLL_SECS": "0"}))
        self.start(patch.object(module, "command", side_effect=self.command))
        self.start(patch.object(module, "notify", side_effect=lambda target, message: self.sent.append((target, message))))
        self.start(patch.object(module.time, "time", side_effect=lambda: self.clock))
        self.start(patch.object(module.subprocess, "run", side_effect=lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(self.checks), "")))

    def start(self, mock):
        mock.start()
        self.addCleanup(mock.stop)

    def command(self, args, cwd=None):
        if args[0] == "git":
            return ".git"
        if args[0] == "gh":
            self.assertIn("isDraft", args[-1].split(","))
            return json.dumps(self.pr)
        return self.child if args[-1] == "child" else self.parent

    def tick(self):
        return module.tick(self.manifest, "child", "parent")

    def test_child_parked_on_blocker_is_never_told_to_rebase(self):
        self.child = "x\n $ delegate-send %16 --text 'docs-purge-4593: BLOCKER none - ~/runs/lane-report.md'\n"
        self.assertEqual(self.tick(), 10)
        self.assertEqual([target for target, _ in self.sent], ["parent"])
        self.assertIn("parked on BLOCKER", self.sent[0][1])
        self.pr["mergeStateStatus"] = "CLEAN"
        self.checks = [dict(name="hub verdict", bucket="fail")]
        self.tick()
        self.assertEqual([target for target, _ in self.sent], ["parent", "parent"])

    def test_dirty_and_behind_notify_both_panes_once(self):
        self.assertEqual(self.tick(), 10)
        self.assertEqual([target for target, _ in self.sent], ["parent", "child"])
        self.assertIn("DIRTY", self.sent[0][1])
        self.assertEqual(self.tick(), 10)
        self.assertEqual(len(self.sent), 2)
        self.pr["mergeStateStatus"] = "BEHIND"
        self.tick()
        self.assertEqual(len(self.sent), 4)

    def test_red_checks_and_ci_wait_trigger_even_while_busy(self):
        self.child = "⠁ Working\nci_wait registered"
        self.pr["mergeStateStatus"] = "CLEAN"
        self.checks = [{"name": "unit", "bucket": "fail"}]
        self.assertEqual(self.tick(), 10)
        self.assertIn("red: unit", self.sent[0][1])

    def test_draft_red_verdicts_do_not_alert_or_escalate(self):
        self.pr.update(isDraft=True, mergeStateStatus="CLEAN")
        self.child = "⠁ Working\nci_wait registered"
        self.checks = [{"name": "CI/global/org/hub/Rust verdict", "bucket": "fail"}]
        self.assertEqual(self.tick(), 0)
        self.clock += 601
        self.assertEqual(self.tick(), 0)
        self.assertEqual(self.sent, [])
        module.subprocess.run.assert_not_called()

    def test_converting_red_pr_to_draft_clears_stall_and_ready_resumes_detection(self):
        self.pr["mergeStateStatus"] = "CLEAN"
        self.checks = [{"name": "draft verdict", "bucket": "fail"}]
        self.assertEqual(self.tick(), 10)
        self.assertEqual(len(self.sent), 2)
        self.pr["isDraft"] = True
        self.clock += 601
        self.assertEqual(self.tick(), 0)
        self.assertEqual(len(self.sent), 2, "draft must not escalate existing idle state")
        state = json.loads((self.root / "mailbox/watchdog/lane.json").read_text())
        self.assertFalse(state["stalled"])
        self.assertNotIn("parent_idle_since", state)
        self.assertNotIn("signature", state)
        self.pr["isDraft"] = False
        self.assertEqual(self.tick(), 10)
        self.assertEqual(len(self.sent), 4, "ready PR must alert afresh")

    def test_draft_conflicts_still_alert(self):
        self.pr["isDraft"] = True
        self.assertEqual(self.tick(), 10)
        self.assertIn("DIRTY", self.sent[0][1])

    def test_busy_nonwaiting_child_not_stalled(self):
        self.child = "⠁ Working"
        self.assertEqual(self.tick(), 0)
        self.assertEqual(self.sent, [])

    def test_parent_idle_alert_after_ten_minutes_and_recovery(self):
        self.tick()
        self.clock += 599
        self.tick()
        self.assertEqual(len(self.sent), 2)
        self.clock += 1
        self.tick()
        self.assertEqual(len(self.sent), 3)
        self.assertIn("Orchestrator idle", self.sent[-1][1])
        self.tick()
        self.assertEqual(len(self.sent), 3)
        self.pr["mergeStateStatus"] = "CLEAN"
        self.assertEqual(self.tick(), 0)

    def test_parent_activity_resets_idle_clock(self):
        self.tick()
        self.clock += 599
        self.parent = "⠁ Working"
        self.tick()
        self.clock += 600
        self.parent = "idle"
        self.tick()
        self.assertEqual(len(self.sent), 2)


if __name__ == "__main__":
    unittest.main()
