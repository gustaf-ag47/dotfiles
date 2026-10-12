"""Load admission is evaluated before model probing and never sleeps in dry runs."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DELEGATE = ROOT / 'config/pi/skills/delegate/scripts/delegate.sh'


class LoadAdmissionTest(unittest.TestCase):
    def test_overload_dry_run_reports_without_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cpu').write_text('some avg10=50.00 avg60=45.00 avg300=30.00 total=1\n')
            (root / 'load').write_text('64.00 0.00 0.00 1/100 1\n')
            (root / 'mem').write_text('MemAvailable: 5000000 kB\n')
            bindir = root / 'bin'
            bindir.mkdir()
            (bindir / 'tmux').write_text('#!/bin/bash\ncase "$1" in has-session) exit 0;; display-message) echo demo;; esac\n')
            (bindir / 'pi').write_text('#!/bin/bash\nexit 0\n')
            for cmd in ('tmux', 'pi'):
                (bindir / cmd).chmod(0o755)
            env = os.environ | {'PATH': str(bindir) + ':' + os.environ['PATH'], 'TMUX': 'fake',
                                'TMUX_PANE': '%1', 'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'cpu'),
                                'PI_DELEGATE_LOADAVG_FILE': str(root / 'load'),
                                'PI_DELEGATE_MEMINFO_FILE': str(root / 'mem'),
                                'PI_DELEGATE_LOAD_WAIT_MAX': '0', 'DELEGATE_IGNORE_MEM': '1'}
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe']
            dry = subprocess.run(args + ['--dry-run'], env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn('overloaded', dry.stdout)
            refused = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(refused.returncode, 5, refused.stderr)
            forced = subprocess.run(args + ['--force', '--dry-run'], env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertIn('skipped', forced.stdout)

    def _base_env(self, root, bindir):
        return os.environ | {'PATH': str(bindir) + ':' + os.environ['PATH'], 'TMUX': 'fake',
                              'TMUX_PANE': '%1', 'PI_DELEGATE_LOAD_WAIT_MAX': '0',
                              'DELEGATE_IGNORE_MEM': '1'}

    def _make_bindir(self, root):
        bindir = root / 'bin'
        bindir.mkdir()
        (bindir / 'tmux').write_text('#!/bin/bash\ncase "$1" in has-session) exit 0;; display-message) echo demo;; esac\n')
        (bindir / 'pi').write_text('#!/bin/bash\nexit 0\n')
        for cmd in ('tmux', 'pi'):
            (bindir / cmd).chmod(0o755)
        return bindir

    def test_missing_loadavg_file_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cpu').write_text('some avg10=1.00 avg60=1.00 avg300=1.00 total=1\n')
            (root / 'mem').write_text('MemAvailable: 5000000 kB\n')
            bindir = self._make_bindir(root)
            env = self._base_env(root, bindir) | {
                'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'cpu'),
                'PI_DELEGATE_LOADAVG_FILE': str(root / 'no-such-loadavg'),
                'PI_DELEGATE_MEMINFO_FILE': str(root / 'mem'),
            }
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe', '--dry-run']
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('unavailable', result.stdout)
            self.assertNotIn('unbound variable', result.stderr)

    def test_unreadable_loadavg_file_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cpu').write_text('some avg10=1.00 avg60=1.00 avg300=1.00 total=1\n')
            (root / 'mem').write_text('MemAvailable: 5000000 kB\n')
            load = root / 'load'
            load.write_text('1.00 0.00 0.00 1/100 1\n')
            load.chmod(0o000)
            bindir = self._make_bindir(root)
            env = self._base_env(root, bindir) | {
                'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'cpu'),
                'PI_DELEGATE_LOADAVG_FILE': str(load),
                'PI_DELEGATE_MEMINFO_FILE': str(root / 'mem'),
            }
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe', '--dry-run']
            try:
                result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('unavailable', result.stdout)
            finally:
                load.chmod(0o644)

    def test_missing_meminfo_file_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cpu').write_text('some avg10=1.00 avg60=1.00 avg300=1.00 total=1\n')
            (root / 'load').write_text('1.00 0.00 0.00 1/100 1\n')
            bindir = self._make_bindir(root)
            env = self._base_env(root, bindir) | {
                'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'cpu'),
                'PI_DELEGATE_LOADAVG_FILE': str(root / 'load'),
                'PI_DELEGATE_MEMINFO_FILE': str(root / 'no-such-meminfo'),
            }
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe', '--dry-run']
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('unavailable', result.stdout)
            self.assertNotIn('unbound variable', result.stderr)

    def test_missing_cpu_pressure_file_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'load').write_text('1.00 0.00 0.00 1/100 1\n')
            (root / 'mem').write_text('MemAvailable: 5000000 kB\n')
            bindir = self._make_bindir(root)
            env = self._base_env(root, bindir) | {
                'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'no-such-cpu'),
                'PI_DELEGATE_LOADAVG_FILE': str(root / 'load'),
                'PI_DELEGATE_MEMINFO_FILE': str(root / 'mem'),
            }
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe', '--dry-run']
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('unavailable', result.stdout)

    def test_all_sources_readable_still_detects_overload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cpu').write_text('some avg10=50.00 avg60=45.00 avg300=30.00 total=1\n')
            (root / 'load').write_text('64.00 0.00 0.00 1/100 1\n')
            (root / 'mem').write_text('MemAvailable: 5000000 kB\n')
            bindir = self._make_bindir(root)
            env = self._base_env(root, bindir) | {
                'PI_DELEGATE_CPU_PRESSURE_FILE': str(root / 'cpu'),
                'PI_DELEGATE_LOADAVG_FILE': str(root / 'load'),
                'PI_DELEGATE_MEMINFO_FILE': str(root / 'mem'),
            }
            args = [str(DELEGATE), '--task', 'test', '--session', 'demo', '--no-probe', '--dry-run']
            result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('overloaded', result.stdout)
            self.assertNotIn('unavailable', result.stdout)


if __name__ == '__main__':
    unittest.main()
