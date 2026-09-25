#!/usr/bin/env python3
"""Install individual Pi resources, preserving live state and reversible backups."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', 'node_modules', '__pycache__'}


def source_files(root):
    if not root.exists():
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(files):
            if not name.endswith(('.pyc', '.bak')):
                yield Path(base) / name


def pi_ai_path(binary):
    executable = Path(shutil.which(binary) or binary).resolve()
    for parent in executable.parents:
        candidate = parent / 'node_modules/@earendil-works/pi-ai'
        if (candidate / 'package.json').is_file():
            return candidate
    raise ValueError('Pi dependency not found. Install @earendil-works/pi-coding-agent or pass --pi-bin.')


def plan(agent, private, binary):
    dependency = pi_ai_path(binary)
    operations = [('link', dependency, ROOT / 'config/pi/node_modules/@earendil-works/pi-ai'),
                  ('link', dependency, agent / 'node_modules/@earendil-works/pi-ai')]
    for source, target in [(ROOT / 'config/pi/extensions', agent / 'extensions'),
                           (ROOT / 'config/pi/lib', agent / 'lib'),
                           (ROOT / 'config/pi/skills', agent / 'skills'),
                           (private / 'skills', agent / 'skills')]:
        for file in source_files(source):
            operations.append(('link', file, target / file.relative_to(source)))
    for name in ('settings', 'models'):
        target = agent / f'{name}.json'
        if not target.exists() and not target.is_symlink():
            operations.append(('seed', ROOT / f'config/pi/{name}.example.json', target))
    seen = set()
    for _, _, target in operations:
        if target in seen:
            raise ValueError(f'Public/private resource collision: {target}')
        seen.add(target)
    return operations


def correct(source, target):
    return target.is_symlink() and target.resolve() == source.resolve()


def apply(operations, state):
    changes = [(kind, src, dst) for kind, src, dst in operations if not (kind == 'link' and correct(src, dst))]
    if not changes:
        print('Pi resources already installed; nothing changed.')
        return
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='adoption-', dir=state))
    manifest = backup / 'manifest.json'
    records = []
    try:
        for kind, source, target in changes:
            # Resource directories may contain live dependencies. Keep directories
            # real and swap only files, never whole trees or symlinked profiles.
            if any(p.is_symlink() for p in target.parents if p != Path.home()):
                # /home itself may be a platform symlink; constrain this check to
                # parents below the selected destination's existing resource root.
                for p in list(target.parents)[:2]:
                    if p.is_symlink():
                        raise ValueError(f'Refusing to install through symlinked resource directory: {p}')
            if target.is_dir() and not target.is_symlink():
                raise ValueError(f'Refusing to replace directory: {target}')
            target.parent.mkdir(parents=True, exist_ok=True)
            old = None
            if target.exists() or target.is_symlink():
                if kind == 'seed':
                    continue
                old = backup / str(len(records))
                shutil.copy2(target, old, follow_symlinks=False)
            record = {'target': str(target), 'backup': str(old) if old else None, 'kind': kind,
                      'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest() if kind == 'seed' else None}
            records.append(record)
            manifest.write_text(json.dumps(records, indent=2))
            temp = target.parent / ('.pi-setup-' + backup.name)
            try:
                if kind == 'link':
                    temp.symlink_to(source)
                else:
                    shutil.copyfile(source, temp)
                os.replace(temp, target)
            finally:
                if temp.is_symlink() or temp.exists():
                    temp.unlink()
        print(f'Installed {len(records)} resources. Existing settings, auth, sessions and proxy service were not changed.')
        print(f'Rollback: pi-setup --rollback {manifest}')
    except Exception:
        print(f'Partial adoption; rollback manifest: {manifest}')
        raise


def rollback(manifest):
    records = json.loads(manifest.read_text())
    conflicts = []
    for record in reversed(records):
        target = Path(record['target'])
        old = Path(record['backup']) if record['backup'] else None
        if old and not (old.exists() or old.is_symlink()):
            continue  # Already restored.
        matches = correct(Path(record['source']), target) if record['kind'] == 'link' else (
            target.is_file() and not target.is_symlink()
            and hashlib.sha256(target.read_bytes()).hexdigest() == record['sha256'])
        if not matches:
            if target.exists() or target.is_symlink():
                conflicts.append(str(target))
                continue
        if old:
            os.replace(old, target)
        elif matches:
            target.unlink()
    if conflicts:
        raise ValueError('Rollback preserved resources changed since adoption: ' + ', '.join(conflicts))
    print('Rollback complete. Directories and unrelated live state retained.')


def upstreams(fetch):
    for upstream in json.loads((ROOT / 'config/pi/upstreams.json').read_text()):
        target = Path.home() / '.agents/skills' / upstream['name']
        if not target.exists():
            print(f"Missing pinned skill checkout: {target}")
            if not fetch:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'clone', '--no-checkout', upstream['url'], str(target)], check=True)
            subprocess.run(['git', '-C', str(target), 'checkout', '--detach', upstream['commit']], check=True)
        head = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(target), 'status', '--porcelain'], text=True).strip()
        print(f"{upstream['name']}: {'pinned' if head == upstream['commit'] else 'different revision (preserved)'}; {'local changes preserved' if dirty else 'clean'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Back up and adopt individual resources')
    mode.add_argument('--check', action='store_true', help='Show pending changes; default')
    mode.add_argument('--rollback', type=Path, metavar='MANIFEST')
    mode.add_argument('--fetch-upstreams', action='store_true', help='Clone missing pinned third-party skills; preserve existing checkouts')
    parser.add_argument('--agent-dir', type=Path, default=Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent')))
    parser.add_argument('--private-root', type=Path, default=Path(os.environ.get('LOCAL_CONFIG', Path.home() / 'sync/dotfiles-local')) / 'config/pi')
    parser.add_argument('--pi-bin', default=os.environ.get('PI_CLAUDE_SUB_PI_BIN', 'pi'))
    args = parser.parse_args()
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'pi-dotfiles'
    if args.fetch_upstreams:
        upstreams(True)
        return
    if not args.apply and not args.rollback:
        operations = plan(args.agent_dir.expanduser().absolute(), args.private_root.expanduser(), args.pi_bin)
        pending = [(kind, src, dst) for kind, src, dst in operations if not (kind == 'link' and correct(src, dst))]
        for kind, _, target in pending:
            print(f'{kind}: {target}')
        print(f'{len(pending)} pending changes; use --apply. Credentials and runtime state are excluded.')
        upstreams(False)
        return
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(state / 'install.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.rollback:
            rollback(args.rollback)
        else:
            apply(plan(args.agent_dir.expanduser().absolute(), args.private_root.expanduser(), args.pi_bin), state)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'pi-setup: {error}')
