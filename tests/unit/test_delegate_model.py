"""Launch verification uses fake panes only; no live agents or quota."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "config/pi/skills/delegate/scripts"


class ModelVerificationTest(unittest.TestCase):
    def verify(self, pane, model="anthropic/claude-sonnet-5", minimum="1000000"):
        return subprocess.run(["python3", str(SCRIPTS / "verify-model.py"), model, minimum],
                              input=pane, capture_output=True, text=True, check=False)

    def test_footer_and_context(self):
        for gauge, capacity in [("1.0M", 1000000), ("1.1M", 1100000)]:
            result = self.verify(f"↑20k 2.0%/{gauge} (auto)    (anthropic) claude-sonnet-5 • high")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"anthropic/claude-sonnet-5 {capacity}")

    def test_wrong_model_small_context_and_missing_footer_fail_closed(self):
        for pane in [
            "requested anthropic/claude-sonnet-5\n0.0%/1.1M (openai-codex) gpt-6-astra • high",
            "0.0%/272k (anthropic) claude-sonnet-5 • high",
            "anthropic/claude-sonnet-5 has 1000000 tokens",
            "",
        ]:
            with self.subTest(pane=pane):
                self.assertEqual(self.verify(pane).returncode, 4)

    def launch(self, repaired):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            scripts = {
                "tmux": '''#!/bin/bash
case "$1" in
 display-message) echo Demo ;;
 capture-pane)
   if [ -f "$HOME/repaired" ] && [ "$REPAIRED" = 1 ]; then
     echo '1.0%/1.0M (anthropic) claude-sonnet-5 • high'
   else
     echo '0.0%/272k (openai-codex) gpt-6-sol • high'
   fi ;;
 send-keys)
   printf '%s\\n' "$*" >> "$HOME/keys"
   [[ "$*" != *'/model '* ]] || touch "$HOME/repaired" ;;
 *) exit 0 ;;
esac
''',
                "pi": "#!/bin/bash\nexit 0\n",
                "sleep": "#!/bin/bash\nexit 0\n",
                "ws": "#!/bin/bash\nexit 1\n",
                "llm-usage": "#!/bin/bash\nexit 1\n",
            }
            for name, source in scripts.items():
                (commands / name).write_text(source)
                (commands / name).chmod(0o755)
            env = os.environ | {"HOME": tmp, "NOTES": tmp, "PATH": f"{commands}:{os.environ['PATH']}",
                                "REPAIRED": str(int(repaired)), "PI_JEV_MODE": "off",
                                "DELEGATE_IGNORE_MEM": "1", "TMUX": "", "TMUX_PANE": ""}
            result = subprocess.run([str(SCRIPTS / "delegate.sh"), "--task", "fixture task", "--session", "Demo",
                                     "--model", "anthropic/claude-sonnet-5", "--min-context", "1000000",
                                     "--no-probe", "--no-notify"], env=env, text=True, capture_output=True, timeout=20)
            return result, (root / "keys").read_text()

    def test_pin_retry_succeeds_before_handover(self):
        result, keys = self.launch(True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified; 1000000 tokens", result.stdout)
        self.assertLess(keys.index("/model anthropic/claude-sonnet-5"), keys.index("You are a delegated"))
        self.assertEqual(keys.count("/failover off"), 1)
        self.assertIn("operator-notes path in the brief", keys)
        self.assertIn("ci:<successful-run-id>", keys)
        self.assertNotIn("record findings in-repo", keys)

    def test_pin_retry_failure_never_sends_task(self):
        result, keys = self.launch(False)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("You are a delegated", keys)
        self.assertEqual(keys.count("/model anthropic/claude-sonnet-5"), 1)
        self.assertIn("child has NO task", result.stderr)


if __name__ == "__main__":
    unittest.main()
