"""bin/mail-pass and bin/mail-sync: credential lookup and single-instance sync."""
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIL_PASS = ROOT / 'bin/mail-pass'
MAIL_SYNC = ROOT / 'bin/mail-sync'
MAIL_OPEN = ROOT / 'bin/mail-open'


def write_exe(path, body):
    path.write_text('#!/bin/bash\n' + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class MailPassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.secrets = self.dir / 'secrets'
        self.secrets.mkdir()
        self.bin = self.dir / 'bin'
        self.bin.mkdir()
        # No real `pass` on PATH unless a test writes one.
        self.env = {'PATH': f'{self.bin}:/usr/bin:/bin', 'MAIL_PASS_DIR': str(self.secrets),
                    'HOME': str(self.dir)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_pass(self, *args):
        return subprocess.run([str(MAIL_PASS), *args], env=self.env,
                              capture_output=True, text=True)

    def test_reads_first_line_of_overlay_file(self):
        (self.secrets / 'icloud').write_text('abcd-efgh-ijkl-mnop\nignored\n')
        result = self.run_pass('icloud')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'abcd-efgh-ijkl-mnop\n')

    def test_falls_back_to_pass_store(self):
        write_exe(self.bin / 'pass', 'echo "from-pass-$2"; echo second\n')
        result = self.run_pass('icloud')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'from-pass-email/icloud\n')

    def test_missing_account_fails_without_output(self):
        result = self.run_pass('nope')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn("no password for 'nope'", result.stderr)

    def test_rejects_path_traversal(self):
        for bad in ('', '../x', '.hidden', 'a/b'):
            self.assertEqual(self.run_pass(bad).returncode, 2, bad)


class MailSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.bin = self.dir / 'bin'
        self.bin.mkdir()
        self.log = self.dir / 'calls'
        write_exe(self.bin / 'mbsync',
                  'if [[ $1 == -l ]]; then printf "INBOX\\nSent Messages\\n"; exit; fi\n'
                  f'echo "mbsync $*" >> {self.log}\n')
        write_exe(self.bin / 'notmuch', f'echo "notmuch $*" >> {self.log}\n')
        self.env = {'PATH': f'{self.bin}:/usr/bin:/bin', 'HOME': str(self.dir),
                    'XDG_DATA_HOME': str(self.dir / 'data'),
                    'XDG_RUNTIME_DIR': str(self.dir)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_syncs_all_then_indexes(self):
        subprocess.run([str(MAIL_SYNC)], env=self.env, check=True)
        self.assertEqual(self.log.read_text().splitlines(),
                         ['mbsync -a', 'notmuch new --quiet'])
        self.assertTrue((self.dir / 'data/mail/icloud').is_dir())

    def test_passes_channel_arguments_through(self):
        subprocess.run([str(MAIL_SYNC), 'icloud:INBOX'], env=self.env, check=True)
        self.assertEqual(self.log.read_text().splitlines()[0], 'mbsync icloud:INBOX')

    def test_parallel_mode_syncs_each_box_once(self):
        subprocess.run([str(MAIL_SYNC), '-j', '2'], env=self.env, check=True)
        calls = self.log.read_text().splitlines()
        self.assertCountEqual(calls[:2], ['mbsync icloud:INBOX', 'mbsync icloud:Sent Messages'])
        self.assertEqual(calls[2:], ['notmuch new --quiet'])

    def test_rejects_bad_job_count(self):
        result = subprocess.run([str(MAIL_SYNC), '-j', '0'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_second_instance_exits_while_lock_held(self):
        lock = self.dir / 'mail-sync.lock'
        holder = subprocess.Popen(['flock', str(lock), 'sleep', '5'])
        try:
            for _ in range(50):
                if lock.exists():
                    break
                subprocess.run(['sleep', '0.05'])
            result = subprocess.run([str(MAIL_SYNC)], env=self.env,
                                    capture_output=True, text=True)
        finally:
            holder.kill()
            holder.wait()
        self.assertEqual(result.returncode, 0)
        self.assertIn('already running', result.stderr)
        self.assertFalse(self.log.exists())


class MailOpenTests(unittest.TestCase):
    def test_copy_outlives_neomutt_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / 'att.html'
            src.write_text('<p>hi</p>')
            opener = tmp / 'opener'
            record = tmp / 'opened'
            write_exe(opener, f'echo "$1" > {record}\n')
            env = {'PATH': '/usr/bin:/bin', 'XDG_RUNTIME_DIR': str(tmp),
                   'MAIL_OPEN_CMD': str(opener)}
            subprocess.run([str(MAIL_OPEN), str(src)], env=env, check=True)
            src.unlink()  # what neomutt does when the mailcap command returns
            for _ in range(50):
                if record.exists() and record.read_text().strip():
                    break
                subprocess.run(['sleep', '0.05'])
            opened = Path(record.read_text().strip())
            self.assertEqual(opened.parent, tmp / 'mail-open')
            self.assertTrue(opened.name.endswith('-att.html'))
            self.assertEqual(opened.read_text(), '<p>hi</p>')


if __name__ == '__main__':
    unittest.main()
