import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "config" / "pi" / "skills" / "hermes"
SEND = SKILL_DIR / "scripts" / "hermes-send.sh"

FAKE_TMUX = """#!/usr/bin/env bash
log="$FAKE_TMUX_LOG"
case "$1" in
list-windows) printf '%s\\n' $FAKE_WINDOWS ;;
list-panes) echo x ;;
capture-pane) printf '%b\\n' "$FAKE_PANE" ;;
send-keys) shift; printf '%s\\n' "$*" >> "$log" ;;
esac
"""


class HermesSendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bindir = Path(self.tmp.name) / "bin"
        bindir.mkdir()
        tmux = bindir / "tmux"
        tmux.write_text(FAKE_TMUX)
        tmux.chmod(tmux.stat().st_mode | stat.S_IEXEC)
        sleep = bindir / "sleep"
        sleep.write_text("#!/bin/sh\n")
        sleep.chmod(sleep.stat().st_mode | stat.S_IEXEC)
        self.log = Path(self.tmp.name) / "keys.log"
        self.env = {
            "PATH": f"{bindir}:/usr/bin:/bin",
            "FAKE_TMUX_LOG": str(self.log),
            "FAKE_WINDOWS": "Work:orchestrator Work:hermes Other:zsh",
            "FAKE_PANE": "idle prompt",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_send(self, *args, **env):
        return subprocess.run(
            ["bash", str(SEND), *args],
            env={**self.env, **env},
            capture_output=True,
            text=True,
        )

    def sent(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_finds_the_single_hermes_window_by_name(self):
        result = self.run_send("--where")
        self.assertEqual(result.stdout.strip(), "Work:hermes")

    def test_idle_hermes_gets_the_message_as_typed(self):
        result = self.run_send("hello there")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent(), ["-t Work:hermes -l hello there", "-t Work:hermes Enter"])

    def test_busy_hermes_gets_a_queued_message_so_its_run_is_not_interrupted(self):
        result = self.run_send("status?", FAKE_PANE="working\\n msg=interrupt · /queue · Ctrl+C cancel")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sent()[0], "-t Work:hermes -l /queue status?")
        self.assertIn("queued", result.stdout)

    def test_pane_ids_and_indexes_are_refused_as_targets(self):
        for bad in ("%2025", "Work:3", "Work:hermes.0"):
            result = self.run_send("--target", bad, "hi")
            self.assertEqual(result.returncode, 3, bad)
        self.assertEqual(self.sent(), [])

    def test_multiline_message_is_refused_because_newline_submits_early(self):
        result = self.run_send("line one\nline two")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.sent(), [])

    def test_two_hermes_windows_require_an_explicit_target(self):
        result = self.run_send("hi", FAKE_WINDOWS="A:hermes B:hermes")
        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.sent(), [])

    def test_env_target_wins_over_discovery(self):
        result = self.run_send("--where", HERMES_TMUX_TARGET="Other:zsh")
        self.assertEqual(result.stdout.strip(), "Other:zsh")


class HermesSkillDocTest(unittest.TestCase):
    def test_skill_frontmatter_names_the_skill(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\nname: hermes\ndescription: "))

    def test_send_script_is_executable(self):
        self.assertTrue(os.access(SEND, os.X_OK))


if __name__ == "__main__":
    unittest.main()
