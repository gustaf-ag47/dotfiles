"""Jev's delegate hook observes task text but never controls the launch.

All tmux/agent/classifier commands are local stubs. No network, credentials,
real processes/windows, or private state are used.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'config/pi/skills/delegate/scripts/delegate.sh'


class JevDelegateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mock = self.root / 'mock-bin'
        self.mock.mkdir()
        self.script = self.root / 'dotfiles/config/pi/skills/delegate/scripts/delegate.sh'
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        self.helper = self.root / 'dotfiles/bin/jev-classify'
        self.helper.parent.mkdir()
        self.write_exec(self.mock / 'tmux', '''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_ROOT/tmux-calls"
case "$1" in
  capture-pane) printf '1.0%%/256K\\n' ;;
  display-message) printf '%s\\n' '$7' ;;
esac
exit 0
''')
        self.write_exec(self.mock / 'pi', '#!/bin/bash\nexit 0\n')
        self.write_exec(self.mock / 'sleep', '#!/bin/bash\nexit 0\n')
        self.write_exec(self.helper, '''#!/bin/bash
printf '%s\\n' "$*" > "$TEST_ROOT/helper-args"
/bin/cat > "$TEST_ROOT/observed-task"
printf '{"status":"ok","suggestion":"mechanical","confidence":1,"applied":false}\\n'
''')
        self.brief = self.root / 'brief.md'
        self.brief.write_text('PRIVATE_BRIEF_MUST_NOT_BE_SENT')
        self.env = {
            'PATH': f'{self.mock}:/usr/bin:/bin',
            'HOME': str(self.root), 'TEST_ROOT': str(self.root),
            'PI_JEV_MODE': 'observe', 'PI_OFFLINE': '1',
        }

    def write_exec(self, path, content):
        path.write_text(content)
        path.chmod(0o700)

    def run_delegate(self, *extra, task=True):
        args = ['bash', str(self.script), '--session', 'test', '--cwd', str(self.root),
                '--model', 'anthropic/fixed-model', '--class', 'research',
                '--no-probe', '--no-notify', '--brief', str(self.brief)]
        if task:
            args += ['--task', 'Compare public documentation']
        result = subprocess.run(args + list(extra), env=self.env, text=True,
                                capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_launch_unchanged(self):
        calls = (self.root / 'tmux-calls').read_text()
        self.assertIn('PI_LLM_CLASS=research', calls)
        self.assertIn('anthropic/fixed-model', calls)
        self.assertNotIn('PI_LLM_CLASS=mechanical', calls)

    def test_observes_only_task_and_ignores_suggestion(self):
        self.run_delegate()
        self.assertEqual((self.root / 'observed-task').read_text(), 'Compare public documentation')
        self.assertEqual((self.root / 'helper-args').read_text().strip(), '--task-stdin --source delegate')
        self.assert_launch_unchanged()

    def test_failed_classifier_does_not_block_or_leak_error(self):
        self.write_exec(self.helper, '#!/bin/bash\necho PRIVATE_FAILURE >&2\nexit 1\n')
        result = self.run_delegate()
        self.assertNotIn('PRIVATE_FAILURE', result.stdout + result.stderr)
        self.assert_launch_unchanged()

    def test_timeout_does_not_block_launch(self):
        self.write_exec(self.helper, '#!/bin/bash\nexec /bin/sleep 60\n')
        self.run_delegate()
        self.assert_launch_unchanged()

    def test_off_missing_helper_and_brief_only_skip_observation(self):
        self.env['PI_JEV_MODE'] = 'off'
        self.run_delegate()
        self.assertFalse((self.root / 'observed-task').exists())
        self.assertIn('PI_JEV_MODE=off', (self.root / 'tmux-calls').read_text())
        self.env['PI_JEV_MODE'] = 'observe'
        self.run_delegate(task=False)
        self.assertFalse((self.root / 'observed-task').exists())
        self.helper.unlink()
        self.run_delegate()
        self.assert_launch_unchanged()

    def test_numeric_session_is_not_treated_as_window_index(self):
        self.run_delegate('--session', '3')
        self.assertIn('new-window -t 3: ', (self.root / 'tmux-calls').read_text())

    def test_automatic_session_uses_calling_pane_not_focused_client(self):
        self.env.update(TMUX='fixture', TMUX_PANE='%fixture')
        result = subprocess.run(['bash', str(self.script), '--task', 'fixture', '--cwd', str(self.root),
                                 '--model', 'anthropic/fixed-model', '--no-probe', '--dry-run'],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('session : $7', result.stdout)
        self.assertIn('display-message -p -t %fixture #{session_id}', (self.root / 'tmux-calls').read_text())

    def test_dry_run_does_not_classify_or_launch(self):
        self.run_delegate('--dry-run')
        self.assertFalse((self.root / 'observed-task').exists())
        self.assertNotIn('new-window', (self.root / 'tmux-calls').read_text())


if __name__ == '__main__':
    unittest.main()
