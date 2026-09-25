"""bin/pi-link-extensions: symlink config/pi/extensions into a temp pi agent dir."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'bin/pi-link-extensions'
ALLOWLIST = ('goal.ts', 'llm-usage.ts', 'llm-failover.ts')


class LinkExtensionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dotfiles = self.root / 'dotfiles'
        self.src = self.dotfiles / 'config/pi/extensions'
        self.src.mkdir(parents=True)
        for name in ALLOWLIST:
            (self.src / name).write_text(f'// {name}\n')
        (self.src / 'experimental.ts').write_text('// not allowlisted\n')
        self.agent = self.root / 'agent'
        self.dst = self.agent / 'extensions'

    def run_script(self, *args, check=True):
        env = dict(os.environ, DOTFILES=str(self.dotfiles), PI_CODING_AGENT_DIR=str(self.agent),
                   HOME=str(self.root / 'home'))
        result = subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_links_allowlist_only_and_is_idempotent(self):
        self.run_script()
        for name in ALLOWLIST:
            link = self.dst / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(os.readlink(link), str(self.src / name))
        self.assertFalse((self.dst / 'experimental.ts').exists())
        second = self.run_script()
        self.assertEqual(second.stdout, '')
        self.assertEqual(self.run_script('--check').stdout.strip().splitlines()[-1], '0 pending changes, 0 conflicts')

    def test_check_reports_pending_without_changing_anything(self):
        result = self.run_script('--check', check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('link: ', result.stdout)
        self.assertFalse(self.dst.exists())

    def test_identical_copy_is_replaced_and_diverged_copy_is_kept(self):
        self.dst.mkdir(parents=True)
        (self.dst / 'goal.ts').write_text('// goal.ts\n')
        (self.dst / 'llm-usage.ts').write_text('// local edits\n')
        result = self.run_script(check=False)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.dst / 'goal.ts').is_symlink())
        self.assertFalse((self.dst / 'llm-usage.ts').is_symlink())
        self.assertEqual((self.dst / 'llm-usage.ts').read_text(), '// local edits\n')
        self.assertIn('conflict', result.stderr)

    def test_never_touches_credentials_or_settings(self):
        self.agent.mkdir()
        for name in ('auth.json', 'settings.json', 'models.json'):
            (self.agent / name).write_text(name)
        self.run_script()
        for name in ('auth.json', 'settings.json', 'models.json'):
            self.assertEqual((self.agent / name).read_text(), name)
            self.assertFalse((self.agent / name).is_symlink())

    def test_remove_unlinks_only_managed_links_and_dangling_are_pruned(self):
        self.dst.mkdir(parents=True)
        foreign = self.dst / 'mine.ts'
        foreign.write_text('// user extension\n')
        stale = self.dst / 'retired.ts'
        stale.symlink_to(self.src / 'retired.ts')  # dangling, points into our tree
        self.run_script()
        self.assertFalse(stale.is_symlink())
        self.assertTrue(foreign.is_file())
        self.run_script('--remove')
        for name in ALLOWLIST:
            self.assertFalse((self.dst / name).exists())
        self.assertEqual(foreign.read_text(), '// user extension\n')


if __name__ == '__main__':
    unittest.main()
