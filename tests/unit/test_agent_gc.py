import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("agent_gc", str(ROOT / "bin/agent-gc"))
gc = importlib.util.module_from_spec(importlib.util.spec_from_loader(_loader.name, _loader))
_loader.exec_module(gc)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class PiIdleTest(unittest.TestCase):
    def test_old_quiet_session_is_idle(self):
        with tempfile.NamedTemporaryFile() as f:
            old = time.time() - 3 * 86400
            os.utime(f.name, (old, old))
            self.assertTrue(gc.pi_is_idle(f.name, "> ", time.time(), 86400))

    def test_working_pane_or_recent_session_is_kept(self):
        with tempfile.NamedTemporaryFile() as f:
            old = time.time() - 3 * 86400
            os.utime(f.name, (old, old))
            self.assertFalse(gc.pi_is_idle(f.name, "⠋ Working...", time.time(), 86400))
            os.utime(f.name, None)
            self.assertFalse(gc.pi_is_idle(f.name, "> ", time.time(), 86400))
        self.assertFalse(gc.pi_is_idle(None, "> ", time.time(), 86400))


class WorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo, self.root = base / "repo", base / "scratch"
        self.repo.mkdir()
        self.root.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / "a.txt").write_text("a\n")
        git("add", ".", cwd=self.repo)
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, age_h):
        wt = self.root / name
        git("worktree", "add", "-q", "--detach", str(wt), cwd=self.repo)
        old = time.time() - age_h * 3600
        for p in [wt, *wt.iterdir()]:
            os.utime(p, (old, old), follow_symlinks=False)
        return wt

    def collect(self):
        with mock.patch.object(gc, "live_cwds", return_value=set()), mock.patch.object(gc, "log"):
            return gc.gc_worktrees(False, self.root, 72 * 3600)

    def test_removes_old_clean_worktree_and_parks_head(self):
        wt = self.add("wt-old", 100)
        self.assertEqual(self.collect(), 1)
        self.assertFalse(wt.exists())
        ref = subprocess.run(["git", "rev-parse", "refs/parked/wt-old"], cwd=self.repo, capture_output=True)
        self.assertEqual(ref.returncode, 0)

    def test_keeps_recent_modified_or_untracked(self):
        self.add("wt-recent", 1)
        mod = self.add("wt-mod", 100)
        (mod / "a.txt").write_text("changed\n")
        new = self.add("wt-new", 100)
        (new / "notes.md").write_text("x\n")
        for wt in (mod, new):
            old = time.time() - 100 * 3600
            for p in [wt, *wt.iterdir()]:
                os.utime(p, (old, old), follow_symlinks=False)
        self.assertEqual(self.collect(), 0)

    def test_deleted_tracked_files_only_still_removed(self):
        wt = self.add("wt-aged-out", 100)
        (wt / "a.txt").unlink()
        old = time.time() - 100 * 3600
        os.utime(wt, (old, old))
        self.assertEqual(self.collect(), 1)

    def test_only_deletions(self):
        self.assertTrue(gc.only_deletions(" D a\n D b\n"))
        self.assertTrue(gc.only_deletions(""))
        self.assertFalse(gc.only_deletions(" D a\n M b\n"))
        self.assertFalse(gc.only_deletions("?? c\n"))


if __name__ == "__main__":
    unittest.main()
