"""bin/pi-claude-sub argument guard: Claude credentials never reach another provider."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'bin/pi-claude-sub'
PLACEHOLDER = 'sk-ant-oat01-' + 'test-placeholder'  # not a credential; split to appease the secret scanner


class AnthropicOnlyGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fake_pi = root / 'pi'
        self.log = root / 'argv'
        self.fake_pi.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {self.log}\n')
        self.fake_pi.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('PI_CLAUDE_SUB_', 'ANTHROPIC_', 'CLAUDE_CODE_'))}
        self.env.update(HOME=str(root), DOTFILES=str(ROOT), PI_CLAUDE_SUB_PI_BIN=str(self.fake_pi),
                        PI_CLAUDE_SUB_PROXY='0', PI_CLAUDE_SUB_TOKEN_REFRESH_BIN='/bin/true',
                        CLAUDE_CODE_OAUTH_TOKEN=PLACEHOLDER)

    def run_sub(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, capture_output=True, text=True, timeout=30)

    def test_rejects_other_providers_and_models(self):
        for args in (['--provider', 'deepseek', '-p', 'hi'], ['--provider=openai-codex', '-p', 'hi'],
                     ['--model', 'deepseek/deepseek-v4-pro', '-p', 'hi'], ['--model=openai-codex/gpt-6-luna', '-p', 'hi']):
            with self.subTest(args=args):
                result = self.run_sub(*args)
                self.assertEqual(result.returncode, 1)
                self.assertIn('Anthropic-only', result.stderr)
                self.assertFalse(self.log.exists(), 'pi must not be launched')

    def test_accepts_anthropic_and_passes_credential(self):
        result = self.run_sub('--model', 'anthropic/claude-haiku-4-5', '-p', 'hi')
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.log.read_text().splitlines()
        self.assertIn(PLACEHOLDER, argv)
        self.assertIn('anthropic/claude-haiku-4-5', argv)

    def test_flags_after_double_dash_are_prompt_text(self):
        result = self.run_sub('-p', '--', '--provider', 'deepseek')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.log.exists())


if __name__ == '__main__':
    unittest.main()
