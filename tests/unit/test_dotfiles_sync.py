"""bin/dotfiles-sync: problems are reported to the desktop once, not on every timer run."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "dotfiles-sync"

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


class SyncFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.env = os.environ.copy()
        self.env.update(GIT_ENV)
        self.origin = self.tmp / "origin.git"
        self.work = self.tmp / "work"
        self.other = self.tmp / "other"
        self.log = self.tmp / "notify.log"
        fake = self.tmp / "fakebin"
        fake.mkdir()
        # notify-send records its message; hyprctl/tmux must never touch the real session.
        (fake / "notify-send").write_text(f'#!/bin/bash\nprintf "%s|%s\\n" "$4" "${{@: -1}}" >> "{self.log}"\n')
        for name in ("hyprctl", "tmux"):
            (fake / name).write_text("#!/bin/bash\nexit 0\n")
        for f in fake.iterdir():
            f.chmod(0o755)
        self.env.update({
            "PATH": f"{fake}:{self.env['PATH']}",
            "DOTFILES": str(self.work),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "HOME": str(self.tmp),
            "HYPRLAND_INSTANCE_SIGNATURE": "test",
        })
        self.git("init", "-q", "--bare", "-b", "master", str(self.origin), cwd=self.tmp)
        self.git("clone", "-q", str(self.origin), str(self.work), cwd=self.tmp)
        (self.work / "a.txt").write_text("one\n")
        (self.work / "scripts").mkdir()
        (self.work / "scripts" / "install.sh").write_text("exit 0\n")
        self.git("add", ".")
        self.git("commit", "-qm", "init")
        self.git("push", "-q", "origin", "master")
        self.git("clone", "-q", str(self.origin), str(self.other), cwd=self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.work, env=self.env, check=True,
                       capture_output=True, text=True)

    def upstream_commit(self, name="a.txt", text="two\n"):
        (self.other / name).write_text(text)
        self.git("add", name, cwd=self.other)
        self.git("commit", "-qm", f"upstream {text.strip()}", cwd=self.other)
        self.git("push", "-q", "origin", "master", cwd=self.other)

    def sync(self):
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True,
                              text=True, timeout=30)

    def notes(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


class BlockedByLocalChanges(SyncFixture):
    def setUp(self):
        super().setUp()
        self.upstream_commit()
        (self.work / "a.txt").write_text("local edit\n")

    def test_names_the_dirty_file_instead_of_claiming_divergence(self):
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.notes()), 1)
        self.assertIn("uncommitted changes in: a.txt", self.notes()[0])
        self.assertNotIn("diverged", self.notes()[0])

    def test_repeated_runs_notify_once_but_log_every_time(self):
        runs = [self.sync() for _ in range(3)]
        self.assertEqual([r.returncode for r in runs], [1, 1, 1])
        self.assertEqual(len(self.notes()), 1)
        for r in runs:
            self.assertIn("uncommitted changes in: a.txt", r.stdout)

    def test_new_upstream_commit_while_blocked_notifies_again(self):
        self.sync()
        self.upstream_commit("b.txt", "new\n")
        self.sync()
        self.assertEqual(len(self.notes()), 2)

    def test_recovery_is_announced_and_clears_the_alert(self):
        self.sync()
        self.git("stash", "-q")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sync working again", "\n".join(self.notes()))
        self.assertFalse((self.tmp / "state" / "dotfiles-sync" / "last-alert").exists())
        self.assertEqual((self.work / "a.txt").read_text(), "two\n")


class RealDivergence(SyncFixture):
    def test_local_commits_are_reported_as_divergence(self):
        self.upstream_commit()
        (self.work / "c.txt").write_text("local\n")
        self.git("add", "c.txt")
        self.git("commit", "-qm", "local")
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.notes()), 1)
        self.assertIn("diverged from origin (1 local commit(s)", self.notes()[0])


class Offline(SyncFixture):
    def test_fetch_failure_notifies_once(self):
        self.origin.rename(self.tmp / "gone.git")
        runs = [self.sync() for _ in range(3)]
        self.assertEqual([r.returncode for r in runs], [0, 0, 0])
        self.assertEqual(self.notes(), ["low|fetch failed (offline?)"])


class UpToDate(SyncFixture):
    def test_quiet_when_nothing_changed(self):
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("up to date", r.stdout)
        self.assertEqual(self.notes(), [])


if __name__ == "__main__":
    unittest.main()
