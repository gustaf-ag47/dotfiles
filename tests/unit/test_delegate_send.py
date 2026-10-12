"""Durable steering preserves literal payloads and never sends keys."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DelegateSendTest(unittest.TestCase):
    def test_literal_file_and_text_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "tmux"
            fake.write_text('#!/bin/bash\n[[ "$1" = list-panes || "$1" = display-message ]] || exit 99\nprintf "%%123\\n"\n')
            fake.chmod(0o755)
            env = os.environ | {"PATH": f"{root}:{os.environ['PATH']}", "PI_DELEGATE_MAILBOX": str(root / "mailbox")}
            text = "don't expand `touch BAD` or $(touch BAD)\nsecond line \"quoted\""
            source = root / "message.txt"
            source.write_text(text)
            for args in [["--file", str(source)], ["--text", text]]:
                result = subprocess.run([str(ROOT / "bin/delegate-send"), "%123", *args],
                                        env=env, capture_output=True, text=True, check=True)
                record = Path(result.stdout.strip())
                self.assertIn(text, record.read_text())
                self.assertIn('- parent: `%123`', record.read_text())
                self.assertIn('"state": "queued"', (record.parent / "state" / (record.name + ".json")).read_text())
                self.assertFalse((root / "BAD").exists())

    def test_ambiguous_window_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "tmux"
            fake.write_text('#!/bin/bash\nprintf "%%123\\n%%124\\n"\n')
            fake.chmod(0o755)
            result = subprocess.run([str(ROOT / "bin/delegate-send"), "Demo:child", "--text", "hi"],
                                    env=os.environ | {"PATH": f"{root}:{os.environ['PATH']}"}, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one pane", result.stderr)


if __name__ == "__main__":
    unittest.main()
