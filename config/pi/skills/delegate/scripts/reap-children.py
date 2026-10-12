#!/usr/bin/python3
"""Conservative one-shot cleanup of ACKed delegate.sh children (timer or --dry-run)."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False)


def safe_worktree(lane):
    cwd = lane.get('cwd', '')
    # A caller may have passed --cwd pointing into a worktree without --worktree.
    # Compare Git directories, not the presence of a branch field alone.
    if not lane.get('branch') and cwd and Path(cwd).is_dir():
        gitdir = command('git', '-C', cwd, 'rev-parse', '--absolute-git-dir')
        common = command('git', '-C', cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
        if gitdir.returncode == 0 and common.returncode == 0 and gitdir.stdout.strip() != common.stdout.strip():
            return False  # unknown checkout; cannot establish its upstream safely
    if not lane.get('branch'):
        return True
    if not cwd or not Path(cwd).is_dir():
        return False
    branch = command('git', '-C', cwd, 'branch', '--show-current')
    if branch.returncode or branch.stdout.strip() != lane['branch']:
        return False
    status = command('git', '-C', cwd, 'status', '--porcelain', '--untracked-files=all')
    if status.returncode or status.stdout.strip():
        return False
    upstream = command('git', '-C', cwd, 'rev-parse', '--verify', '@{upstream}')
    if upstream.returncode:
        return False  # no upstream means we cannot prove the branch was pushed
    ahead = command('git', '-C', cwd, 'rev-list', '--count', '@{upstream}..HEAD')
    return ahead.returncode == 0 and ahead.stdout.strip() == '0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    registry = Path(os.environ.get('PI_DELEGATE_REGISTRY', Path.home() / '.pi/agent/delegate-lanes'))
    idle_seconds = int(os.environ.get('PI_DELEGATE_REAP_IDLE_MIN', '30')) * 60
    if idle_seconds < 0:
        parser.error('PI_DELEGATE_REAP_IDLE_MIN must be non-negative')
    now = time.time()
    for entry in registry.glob('*.json'):
        try:
            lane = json.loads(entry.read_text())
            record = Path(lane['mailbox_record'])
            window_id = lane['window_id']
            target = f"{lane['session']}:{lane['window']}"
            if (lane.get('status') != 'closed' or lane.get('reaped_at') or not lane.get('result')
                    or lane.get('result_status') not in ('PASS', 'DONE', 'BLOCKER', 'FAILED')
                    or not record.with_name('ack').joinpath(record.name).exists()
                    or not re.fullmatch(r'@[0-9]+', window_id)):
                continue
            # Exact window identity: names can be reused after a server restart.
            actual = command('tmux', 'display-message', '-p', '-t', target, '#{window_id}')
            owner = command('tmux', 'show-options', '-w', '-v', '-t', window_id, '@pi_delegate_run_id')
            if (actual.returncode or actual.stdout.strip() != window_id
                    or owner.returncode or owner.stdout.strip() != lane['run_id']):
                continue
            pane = command('tmux', 'capture-pane', '-p', '-t', window_id)
            if (pane.returncode or re.search(r'[⠀-⣿] Working|Working\.\.\.|esc to interrupt', pane.stdout)
                    or not safe_worktree(lane)):
                if lane.get('reap_idle_since') and not args.dry_run:
                    lane.pop('reap_idle_since', None)
                    lane.pop('reap_idle_fingerprint', None)
                    Path(entry.resolve()).write_text(json.dumps(lane, indent=2) + '\n')
                continue
            fingerprint = hashlib.sha256(pane.stdout.encode()).hexdigest()
            seen = lane.get('reap_idle_since')
            if not seen or lane.get('reap_idle_fingerprint') != fingerprint:
                seen = now
                if not args.dry_run:
                    lane['reap_idle_since'] = seen
                    lane['reap_idle_fingerprint'] = fingerprint
                    Path(entry.resolve()).write_text(json.dumps(lane, indent=2) + '\n')
            if now - float(seen) < idle_seconds:
                continue
            print(f"{'would reap' if args.dry_run else 'reaping'} {lane['run_id']} {target} ({window_id})")
            if args.dry_run:
                continue
            # Revalidate just before kill: a new turn or dirty work may have started.
            pane = command('tmux', 'capture-pane', '-p', '-t', window_id)
            if (pane.returncode or hashlib.sha256(pane.stdout.encode()).hexdigest() != fingerprint
                    or re.search(r'[⠀-⣿] Working|Working\.\.\.|esc to interrupt', pane.stdout)
                    or not safe_worktree(lane)):
                lane.pop('reap_idle_since', None)
                Path(entry.resolve()).write_text(json.dumps(lane, indent=2) + '\n')
                continue
            if command('tmux', 'kill-window', '-t', window_id).returncode:
                continue
            lane['reaped_at'] = datetime.now(timezone.utc).isoformat()
            Path(entry.resolve()).write_text(json.dumps(lane, indent=2) + '\n')
            log = Path(os.environ.get('PI_DELEGATE_REAP_LOG', Path.home() / '.pi/agent/reap-log.tsv'))
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a') as handle:
                handle.write(f"{lane['reaped_at']}\t{lane['run_id']}\t{target}\t{window_id}\n")
        except (OSError, ValueError, KeyError, TypeError):
            continue  # old/partial manifests are never candidates


if __name__ == '__main__':
    main()
