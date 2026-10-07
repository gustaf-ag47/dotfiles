"""Exercise delegate.sh's WORKTREES guard and name-based parent resolution.

Dry runs only; this never boots a real tmux window or pi process.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DELEGATE = ROOT / "config/pi/skills/delegate/scripts/delegate.sh"


def write_fake_pi(commands_dir):
    (commands_dir / "pi").write_text("#!/bin/bash\nexit 0\n")
    (commands_dir / "pi").chmod(0o755)


def write_fake_git(commands_dir, repo_root):
    # Only the subset delegate.sh's --worktree path calls in dry run: resolve
    # the repo root and a base ref. Real git's behavior here (shallow clone,
    # detached HEAD, safe.directory) is CI-runner-specific and not what this
    # test is about; stub it out so the guard test is deterministic everywhere.
    (commands_dir / "git").write_text(
        "#!/bin/bash\n"
        "case \" $* \" in\n"
        "*' --show-toplevel '*) printf '%s\\n' " + repr(str(repo_root)) + " ;;\n"
        "*' --abbrev-ref '*) printf 'main\\n' ;;\n"
        "*' symbolic-ref '*) exit 1 ;;\n"
        "*' show-ref '*) exit 1 ;;\n"
        "*) exit 0 ;;\n"
        "esac\n"
    )
    (commands_dir / "git").chmod(0o755)


def write_fake_tmux(commands_dir, session_window):
    (commands_dir / "tmux").write_text(
        "#!/bin/bash\n"
        "case \"$1\" in\n"
        f"display-message) printf '%s' '{session_window}' ;;\n"
        "has-session) exit 0 ;;\n"
        "list-windows) echo demo ;;\n"
        "list-panes) exit 0 ;;\n"
        "new-window) exit 0 ;;\n"
        "send-keys) exit 0 ;;\n"
        "*) exit 0 ;;\n"
        "esac\n"
    )
    (commands_dir / "tmux").chmod(0o755)


class WorktreeGuardTest(unittest.TestCase):
    def run_delegate(self, args, env_extra=None):
        with tempfile.TemporaryDirectory(prefix="delegate-guard-") as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            fake_repo = root / "fake-repo"
            fake_repo.mkdir()
            write_fake_tmux(commands, "demo:caller-window")
            write_fake_pi(commands)
            write_fake_git(commands, fake_repo)
            env = os.environ | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "HOME": tmp,
                "TMUX": "fake-server",
                "TMUX_PANE": "%1",
            }
            env.pop("WORKTREES", None)
            if env_extra:
                env.update(env_extra)
            return subprocess.run(
                [str(DELEGATE), "--task", "guard-test", "--session", "Demo",
                 "--model", "fixture/model", "--dry-run", *args],
                env=env, text=True, capture_output=True, timeout=20,
            )

    def test_missing_worktrees_fails_closed(self):
        run = self.run_delegate(["--worktree", "some-branch"])
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("WORKTREES is not set", run.stderr)

    def test_tmp_worktrees_refused(self):
        run = self.run_delegate(["--worktree", "some-branch"], {"WORKTREES": "/tmp"})
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("must not be under /tmp", run.stderr)

    def test_tmp_subdir_worktrees_refused(self):
        run = self.run_delegate(["--worktree", "some-branch"], {"WORKTREES": "/tmp/scratch"})
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("must not be under /tmp", run.stderr)

    def test_persistent_worktrees_passes_guard(self):
        # dir=str(ROOT): the guard rejects /tmp, and on a CI runner without a
        # TMPDIR override tempfile.TemporaryDirectory() defaults INTO /tmp.
        with tempfile.TemporaryDirectory(prefix="delegate-guard-wt-", dir=str(ROOT)) as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            fake_repo = root / "fake-repo"
            fake_repo.mkdir()
            persistent = root / "worktrees"
            persistent.mkdir()
            write_fake_tmux(commands, "demo:caller-window")
            write_fake_pi(commands)
            write_fake_git(commands, fake_repo)
            env = os.environ | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "HOME": tmp,
                "TMUX": "fake-server",
                "TMUX_PANE": "%1",
                "WORKTREES": str(persistent),
            }
            run = subprocess.run(
                [str(DELEGATE), "--task", "guard-test", "--session", "Demo",
                 "--model", "fixture/model", "--dry-run",
                 "--worktree", "some-branch", "--cwd", str(fake_repo)],
                env=env, text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn(f"{persistent}/wt-some-branch", run.stdout)
            self.assertNotIn("WORKTREES", run.stderr)

    def test_parent_resolves_to_session_window_not_pane_id(self):
        run = self.run_delegate([])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("parent  : demo:caller-window", run.stdout)
        self.assertNotIn("parent  : %1", run.stdout)


def write_fake_tmux_full(commands_dir, session_name_reply, parent_reply, window_names_reply="caller-window"):
    # display-message is called with two different formats here: a bare
    # '#{session_name}' to normalize --session, and '#{session_name}:#{window_name}'
    # to resolve the parent pane. Switch on the trailing format argument so one
    # fake binary can answer both without the test caring about call order.
    (commands_dir / "tmux").write_text(
        "#!/bin/bash\n"
        "args=(\"$@\")\n"
        "last=\"${args[${#args[@]}-1]}\"\n"
        "case \"$1\" in\n"
        "display-message)\n"
        "  case \"$last\" in\n"
        f"  '#{{session_name}}') printf '%s' {session_name_reply!r} ;;\n"
        f"  '#{{session_name}}:#{{window_name}}') printf '%s' {parent_reply!r} ;;\n"
        "  esac ;;\n"
        "has-session) exit 0 ;;\n"
        "list-windows)\n"
        "  case \"$*\" in\n"
        "  *\"#{window_name}\"*) cat <<'WINDOW_NAMES_EOF'\n"
        + window_names_reply + "\n"
        "WINDOW_NAMES_EOF\n"
        "  ;;\n"
        "  *) echo demo ;;\n"
        "  esac ;;\n"
        "list-panes) exit 0 ;;\n"
        "new-window) exit 0 ;;\n"
        "send-keys) exit 0 ;;\n"
        "*) exit 0 ;;\n"
        "esac\n"
    )
    (commands_dir / "tmux").chmod(0o755)


class SessionNormalizationTest(unittest.TestCase):
    def run_delegate(self, session_arg, session_name_reply, parent_reply="Demo:caller", window_names_reply="caller"):
        with tempfile.TemporaryDirectory(prefix="delegate-session-norm-") as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            fake_repo = root / "fake-repo"
            fake_repo.mkdir()
            write_fake_tmux_full(commands, session_name_reply, parent_reply, window_names_reply)
            write_fake_pi(commands)
            write_fake_git(commands, fake_repo)
            env = os.environ | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "HOME": tmp,
                "TMUX": "fake-server",
                "TMUX_PANE": "%1",
            }
            env.pop("WORKTREES", None)
            return subprocess.run(
                [str(DELEGATE), "--task", "norm-test", "--session", session_arg,
                 "--model", "fixture/model", "--dry-run"],
                env=env, text=True, capture_output=True, timeout=20,
            )

    def test_raw_tmux_session_id_is_normalized_to_a_name(self):
        # tmux's own session-id syntax ($0, $1, ...) is a "valid" --session
        # value per has-session, but storing it verbatim in a lane manifest
        # left it unresolvable later (ws route only knows names).
        run = self.run_delegate("$1", "Example-Driver")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("session : Example-Driver", run.stdout)
        self.assertNotIn("session : $1", run.stdout)

    def test_a_name_passed_in_is_left_as_is(self):
        run = self.run_delegate("Demo", "Demo")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("session : Demo", run.stdout)


class ParentWindowUniquenessTest(unittest.TestCase):
    def run_delegate(self, parent_reply, window_names_reply):
        with tempfile.TemporaryDirectory(prefix="delegate-parent-uniq-") as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            fake_repo = root / "fake-repo"
            fake_repo.mkdir()
            write_fake_tmux_full(commands, "Demo", parent_reply, window_names_reply)
            write_fake_pi(commands)
            write_fake_git(commands, fake_repo)
            env = os.environ | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "HOME": tmp,
                "TMUX": "fake-server",
                "TMUX_PANE": "%1",
            }
            env.pop("WORKTREES", None)
            return subprocess.run(
                [str(DELEGATE), "--task", "uniq-test", "--session", "Demo",
                 "--model", "fixture/model", "--dry-run"],
                env=env, text=True, capture_output=True, timeout=20,
            )

    def test_generic_window_name_warns_and_records_fallback_pane(self):
        run = self.run_delegate("Demo:zsh", "zsh")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("generic name", run.stderr)
        self.assertIn("parent_pane=%1", run.stderr)
        self.assertIn("parent_pane %1", run.stdout)

    def test_duplicate_window_name_in_session_warns(self):
        run = self.run_delegate("Demo:shared", "shared\nshared")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("not unique", run.stderr)
        self.assertIn("parent_pane=%1", run.stderr)

    def test_unique_specific_window_name_is_silent(self):
        run = self.run_delegate("Demo:caller-window", "caller-window")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("generic name", run.stderr)
        self.assertNotIn("not unique", run.stderr)


if __name__ == "__main__":
    unittest.main()
