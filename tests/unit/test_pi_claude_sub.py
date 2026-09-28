"""bin/pi-claude-sub is a transparent shim: plain pi does the Anthropic routing now."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'bin/pi-claude-sub'


class ShimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fake_pi = root / 'pi'
        self.log = root / 'argv'
        self.fake_pi.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {self.log}\n')
        self.fake_pi.chmod(0o755)
        self.env = dict(os.environ, PI_CLAUDE_SUB_PI_BIN=str(self.fake_pi))

    def test_passes_arguments_through_unchanged_and_adds_nothing(self):
        args = ['--model', 'openai-codex/gpt-6-luna', '-p', '--', 'hi --api-key not-a-flag']
        result = subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), args)
        self.assertNotIn('--api-key', result.stderr)


if __name__ == '__main__':
    unittest.main()
