"""The reaper never closes an unacked, busy, or unpushed child."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAPER = ROOT / 'config/pi/skills/delegate/scripts/reap-children.py'


class ReapTest(unittest.TestCase):
    def test_ack_result_idle_and_no_worktree_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / 'registry'
            registry.mkdir()
            mailbox = root / 'mailbox'
            (mailbox / 'ack').mkdir(parents=True)
            record = mailbox / 'run.md'
            record.write_text('delivered')
            manifest = root / 'lane.json'
            manifest.write_text(json.dumps({'run_id': 'run', 'window_id': '@25', 'session': 'demo',
                'window': 'child', 'status': 'closed', 'result_status': 'DONE',
                'result': 'task: DONE none - /notes/report.md',
                'mailbox_record': str(record), 'branch': '', 'cwd': tmp}))
            (registry / 'run.json').symlink_to(manifest)
            bindir = root / 'bin'
            bindir.mkdir()
            (bindir / 'tmux').write_text('#!/bin/bash\n'
                'echo "$*" >> "$TMUX_LOG"\n'
                'case "$1" in display-message) echo @25;; show-options) echo "${OWNER:-run}";; capture-pane) echo "${PANE:-2.0%/1M}";; esac\n')
            (bindir / 'tmux').chmod(0o755)
            env = os.environ | {'PATH': str(bindir) + ':' + os.environ['PATH'],
                 'PI_DELEGATE_REGISTRY': str(registry), 'PI_DELEGATE_REAP_IDLE_MIN': '0',
                 'TMUX_LOG': str(root / 'tmux.log'), 'PI_DELEGATE_REAP_LOG': str(root / 'reap-log.tsv')}
            cmd = ['python3', str(REAPER)]
            subprocess.run(cmd + ['--dry-run'], env=env, check=True, capture_output=True)
            self.assertFalse((root / 'tmux.log').exists())
            subprocess.run(cmd, env=env, check=True, capture_output=True)
            self.assertFalse((root / 'tmux.log').exists())
            record.rename(mailbox / 'ack' / record.name)
            subprocess.run(cmd, env=env | {'OWNER': 'other'}, check=True, capture_output=True)
            subprocess.run(cmd, env=env | {'PANE': '⠴ Working'}, check=True, capture_output=True)
            self.assertNotIn('kill-window', (root / 'tmux.log').read_text())
            subprocess.run(cmd, env=env, check=True, capture_output=True)
            self.assertIn('kill-window -t @25', (root / 'tmux.log').read_text())
            self.assertIn('run', (root / 'reap-log.tsv').read_text())


if __name__ == '__main__':
    unittest.main()
