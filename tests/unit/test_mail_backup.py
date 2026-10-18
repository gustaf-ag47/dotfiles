"""bin/mail-backup: restic snapshots of the append-only mail archive."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIL_BACKUP = ROOT / 'bin/mail-backup'


@unittest.skipUnless(shutil.which('restic'), 'restic not installed')
class MailBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.dir / 'mail-archive'
        for folder, n in (('icloud/INBOX', 3), ('icloud/Archive/2024', 2), ('thunderbird/kth/INBOX', 1)):
            for sub in ('cur', 'new', 'tmp'):
                (self.src / folder / sub).mkdir(parents=True)
            for i in range(n):
                (self.src / folder / 'cur' / f'{i}.host,U={i}:2,S').write_text(f'mail {folder} {i}')
        self.repo = self.dir / 'repo'
        pw = self.dir / 'pw'
        pw.write_text('test-password\n')
        self.env = {
            'PATH': '/usr/bin:/bin', 'HOME': str(self.dir),
            'XDG_STATE_HOME': str(self.dir / 'state'), 'XDG_CACHE_HOME': str(self.dir / 'cache'),
            'XDG_RUNTIME_DIR': str(self.dir), 'MAIL_BACKUP_SOURCE': str(self.src),
            'MAIL_BACKUP_PASSWORD_FILE': str(pw), 'MAIL_BACKUP_REPOS': f'# comment\n{self.repo}\n',
            'RESTIC_CACHE_DIR': str(self.dir / 'restic-cache'),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_mb(self, *args, **env):
        return subprocess.run([str(MAIL_BACKUP), *args], env={**self.env, **env},
                              capture_output=True, text=True, timeout=120)

    def test_init_backup_verify_roundtrip(self):
        self.assertEqual(self.run_mb('init').returncode, 0)
        result = self.run_mb('backup')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('6 messages', result.stdout)
        manifest = (self.src / '.backup-manifest').read_text().splitlines()
        self.assertIn('total=6', manifest[0])
        self.assertEqual(manifest[1:], ['2 icloud/Archive/2024', '3 icloud/INBOX', '1 thunderbird/kth/INBOX'])
        verify = self.run_mb('verify')
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn('restore OK: 6 messages', verify.stdout)
        self.assertFalse((self.dir / 'cache/mail-backup-verify').exists(), 'scratch restore not cleaned up')

    def test_refuses_when_archive_shrinks(self):
        self.run_mb('init')
        self.assertEqual(self.run_mb('backup').returncode, 0)
        next((self.src / 'icloud/INBOX/cur').iterdir()).unlink()
        result = self.run_mb('backup')
        self.assertEqual(result.returncode, 1)
        self.assertIn('shrank from 6 to 5', result.stderr)
        self.assertEqual(self.run_mb('backup', MAIL_BACKUP_ALLOW_SHRINK='1').returncode, 0)

    def test_unreachable_repo_fails_and_alerts_when_never_succeeded(self):
        result = self.run_mb('backup', MAIL_BACKUP_REPOS=str(self.dir / 'missing-repo'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('ALERT: no successful backup', result.stderr)

    def test_missing_repo_config_is_an_error(self):
        env = dict(self.env)
        del env['MAIL_BACKUP_REPOS']
        env['MAIL_BACKUP_OVERLAY'] = str(self.dir / 'no-overlay')
        result = subprocess.run([str(MAIL_BACKUP), 'backup'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('no repositories', result.stderr)

    def test_usage(self):
        self.assertEqual(self.run_mb('bogus').returncode, 2)


if __name__ == '__main__':
    unittest.main()
