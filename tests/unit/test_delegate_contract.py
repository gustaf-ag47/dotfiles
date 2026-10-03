"""Exercise the watcher against a fake tmux; never send keys to a real pane."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WATCHER = ROOT / "config/pi/skills/delegate/scripts/watch-child.sh"


class DelegateContractTest(unittest.TestCase):
    def run_watcher(self, child_line: str, require_join=False) -> tuple[str, str]:
        with tempfile.TemporaryDirectory(prefix="delegate-contract-") as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            (commands / "tmux").write_text(
                "#!/bin/bash\n"
                "case \"$1\" in\n"
                "capture-pane) if [ \"$REQUIRE_JOIN\" = 1 ] && [[ \" $* \" != *\" -J \"* ]]; then printf '2.0%%/1.0M\\nexample: PASS abcdef123 -\\n docs/report.md\\n'; else printf '%s\\n' '2.0%/1.0M' \"$CHILD_LINE\"; fi ;;\n"
                "has-session) exit 0 ;;\n"
                "list-windows) echo child ;;\n"
                "list-panes) exit 0 ;;\n"
                "send-keys) printf '%s\\n' \"$*\" >> \"$KEY_LOG\" ;;\n"
                "esac\n"
            )
            (commands / "sleep").write_text("#!/bin/bash\nexit 0\n")
            for name in ("tmux", "sleep"):
                (commands / name).chmod(0o755)
            env = os.environ | {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "HOME": tmp,
                "CHILD_LINE": child_line,
                "REQUIRE_JOIN": "1" if require_join else "0",
                "KEY_LOG": str(root / "keys"),
                "PI_DELEGATE_MAILBOX": str(root / "mailbox"),
                "PI_DELEGATE_GOAL": "finish the task",
                "PI_DELEGATE_POLL_SECS": "0",
                "PI_DELEGATE_IDLE_STREAK": "1",
                "PI_DELEGATE_MIN_GRACE_SECS": "0",
            }
            run = subprocess.run(
                [str(WATCHER), "demo:child", "unknown", "run-id", tmp, "example"],
                env=env,
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            records = list((root / "mailbox").glob("*.md"))
            self.assertEqual(len(records), 1)
            return records[0].read_text(), (root / "keys").read_text() if (root / "keys").exists() else ""

    def test_result_and_blocker_do_not_resume(self):
        for status in ("PASS", "DONE", "BLOCKER", "FAILED"):
            for sha in ("abcdef123", "none"):
                with self.subTest(status=status, sha=sha):
                    record, keys = self.run_watcher(f"example: {status} {sha} - docs/report.md")
                    self.assertIn("verdict: **idle**", record)
                    self.assertNotIn("/goal", keys)

    def test_wrapped_and_long_completion_records_do_not_resume(self):
        _, keys = self.run_watcher('example: PASS abcdef123 - docs/report.md', require_join=True)
        self.assertNotIn('/goal', keys)
        _, keys = self.run_watcher('example: nested task: PASS abcdef123 - docs/report.md\n' + 'x' * 100000)
        self.assertNotIn('/goal', keys)

    def test_legacy_handshake_does_not_resume(self):
        _, keys = self.run_watcher("PARENT: example accepted")
        self.assertNotIn("/goal", keys)
        _, keys = self.run_watcher("PARENT: example done")
        self.assertNotIn("/goal", keys)

    def test_noise_is_not_completion(self):
        for line in (
            "example: ACK abcdef123 - docs/report.md",
            "example: DONE <sha-or-none> - <report path>",
            "example: DONE abcdef123 - <report path>",
            "example: DONE abc - docs/report.md",
            "example: progress abcdef123 - docs/report.md",
            "example: PASS abcdef123 - docs/report.md still running",
        ):
            with self.subTest(line=line):
                _, keys = self.run_watcher(line)
                self.assertIn("/goal", keys)


if __name__ == "__main__":
    unittest.main()
