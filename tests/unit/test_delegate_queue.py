"""Dependency queue fixtures never launch real services or agents."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "bin/delegate-queue"
loader = importlib.machinery.SourceFileLoader("delegate_queue", str(QUEUE))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, source in {
            "systemd-run": 'printf "%s\\n" "$*" >> "$FIXTURE/timers"',
            "systemctl": 'exit 0',
            "gh": 'cat "$FIXTURE/pr-state"',
            "launch": 'printf "%s\\n" "$*" >> "$FIXTURE/launched"',
        }.items():
            path = self.root / name
            path.write_text('#!/bin/bash\n' + source + '\n')
            path.chmod(0o755)
        self.env = os.environ | {"PATH": f"{self.root}:{os.environ['PATH']}", "FIXTURE": str(self.root)}
        (self.root / "pr-state").write_text("OPEN")
        self.directory = self.root / "lanes"

    def run_queue(self, *args):
        return subprocess.run([str(QUEUE), *args, "--directory", str(self.directory)],
                              env=self.env, capture_output=True, text=True, check=True)

    def enqueue(self, *conditions):
        args = []
        for condition in conditions:
            args += ["--after", condition]
        subprocess.run([str(QUEUE), "_enqueue", "--directory", str(self.directory), *args,
                        "--", str(self.root / "launch"), "literal `quote`"], env=self.env, check=True, capture_output=True)
        return next((self.directory / "queued").glob("*.json"))

    def test_all_dependencies_then_launch_once(self):
        path = self.enqueue("pr:owner/repo#12:merged", "lane:dependency:done")
        self.assertIn("queued", self.run_queue("list").stdout)
        self.run_queue("_tick", str(path))
        self.assertFalse((self.root / "launched").exists())
        (self.root / "pr-state").write_text("MERGED")
        self.run_queue("_tick", str(path))
        self.assertFalse((self.root / "launched").exists())
        dependency = self.directory / "dependency.json"
        dependency.write_text(json.dumps({"status": "closed", "result_status": "BLOCKER"}))
        self.run_queue("_tick", str(path))
        self.assertFalse((self.root / "launched").exists())
        dependency.write_text(json.dumps({"status": "closed", "result_status": "DONE"}))
        self.run_queue("_tick", str(path))
        self.run_queue("_tick", str(path))
        self.assertEqual((self.root / "launched").read_text().splitlines(), ["literal `quote`"])
        self.assertEqual(json.loads(path.read_text())["status"], "launched")

    def test_cancel_never_launches(self):
        path = self.enqueue("pr:owner/repo#12:merged")
        self.run_queue("cancel", path.stem)
        (self.root / "pr-state").write_text("MERGED")
        self.run_queue("_tick", str(path))
        self.assertFalse((self.root / "launched").exists())
        self.assertEqual(json.loads(path.read_text())["status"], "cancelled")

    def test_api_failure_is_not_satisfied(self):
        path = self.enqueue("pr:owner/repo#12:merged")
        (self.root / "pr-state").unlink()
        self.run_queue("_tick", str(path))
        lane = json.loads(path.read_text())
        self.assertEqual(lane["status"], "queued")
        self.assertIn("last_error", lane)

    def test_invalid_dependencies_rejected(self):
        for condition in ["pr:owner/repo#0:merged", "lane:../escape:done", "branch:-main:merged", "unknown"]:
            with self.subTest(condition=condition):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    module.validate(condition)

    def test_branch_ancestor(self):
        repo = self.root / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.DEVNULL).strip()
        git("init", "-b", "main")
        git("-c", "user.name=Fixture", "-c", "user.email=f@example.test", "commit", "--allow-empty", "-m", "base")
        git("branch", "dependency")
        git("remote", "add", "origin", str(repo))
        git("fetch", "origin")
        git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assertTrue(module.satisfied("branch:dependency:merged", {"launch_cwd": str(repo)}, self.directory))
        git("checkout", "dependency")
        git("-c", "user.name=Fixture", "-c", "user.email=f@example.test", "commit", "--allow-empty", "-m", "unmerged")
        self.assertFalse(module.satisfied("branch:dependency:merged", {"launch_cwd": str(repo)}, self.directory))


if __name__ == "__main__":
    unittest.main()
