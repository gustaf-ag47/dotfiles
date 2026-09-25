#!/usr/bin/env python3
"""Opt-in live tests: creates ONLY its own tmux session and private scratch profile.

Uses small real inference requests. Leaves test windows open for inspection.
No service restarts, credential refresh, or interaction with existing windows.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
MODELS = ['anthropic/claude-fable-5', 'openai-codex/gpt-6-astra', 'deepseek/deepseek-v4-pro']


def tmux(*args):
    return subprocess.check_output(['tmux', *args], text=True).strip()


def send(pane, text):
    tmux('send-keys', '-t', pane, '-l', '--', text)
    time.sleep(0.7)
    tmux('send-keys', '-t', pane, 'Enter')
    time.sleep(0.7)
    tmux('send-keys', '-t', pane, 'Enter')


def messages(profile, cwd):
    out = []
    for file in (profile / 'sessions').glob('**/*.jsonl'):
        lines = file.read_text().splitlines()
        if not lines:
            continue
        try:
            if json.loads(lines[0]).get('cwd') != str(cwd):
                continue
            for line in lines[1:]:
                entry = json.loads(line)
                if entry.get('type') == 'message':
                    out.append(entry['message'])
        except json.JSONDecodeError:
            continue  # An active writer may not have completed the final line.
    return out


def wait_reply(profile, cwd, marker, timeout=240):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for message in messages(profile, cwd):
            if message.get('role') != 'assistant' or message.get('stopReason') in ('error', 'aborted', 'pending'):
                continue
            text = '\n'.join(x.get('text', '') for x in message.get('content', []) if x.get('type') == 'text')
            if marker in text:
                return message
        time.sleep(2)
    raise RuntimeError(f'Timed out waiting for {marker}; inspect the dedicated test tmux session.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True, help='Acknowledge real provider usage')
    args = parser.parse_args()
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'pi-unified-verification'
    state.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='tmux-', dir=state))
    profile = run / 'profile'
    profile.mkdir(mode=0o700)
    # A test-only credential snapshot, never a symlink to live mutable auth.
    # Remove refresh tokens so these agents cannot rotate credentials used by
    # existing sessions. Refuse a near-expired access token before launching.
    auth_path = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent')) / 'auth.json'
    original_auth = json.loads(auth_path.read_text())
    codex = original_auth.get('openai-codex', {})
    if codex.get('expires', 0) < (time.time() + 1800) * 1000:
        raise SystemExit('Codex access token needs refresh in normal Pi before running this isolated test.')
    auth = {name: dict(original_auth[name]) for name in ('openai-codex', 'deepseek')}
    auth['openai-codex']['refresh'] = ''
    fd = os.open(profile / 'auth.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(auth, file)
    subprocess.run([str(ROOT / 'bin/pi-setup'), '--apply', '--agent-dir', str(profile)], check=True)
    settings = json.loads((profile / 'settings.json').read_text())
    settings.update(retry={'enabled': False}, lastChangelogVersion='0.85.1')
    (profile / 'settings.json').write_text(json.dumps(settings))
    name = 'pi-unified-e2e-' + str(int(time.time()))
    print(f'Test tmux session: {name}\nEvidence: {run}', flush=True)
    report = {'session': name, 'run': str(run), 'checks': []}
    panes = []
    executable = shutil.which('pi')
    for index, model in enumerate(MODELS):
        provider, model_id = model.split('/', 1)
        cwd = run / provider
        cwd.mkdir()
        brief = cwd / 'brief.md'
        brief.write_text(f'''This is a tightly scoped live Pi integration smoke test on the operator's PC.
Your only writable directory is {cwd}. Do not inspect credentials, services, other sessions or repositories.
1. Use bash to print ONLY PI_PROVIDER and PI_MODEL (not the rest of the environment).
2. Use write to create smoke.txt containing BEFORE_UNIFIED.
3. Use edit to change BEFORE_UNIFIED to AFTER_UNIFIED.
4. Use read to verify smoke.txt.
5. Reply with E2E_OK_{provider} and the observed provider/model.
Expected provider/model: {model}. Stop after this test; do not delegate or commit anything.
''')
        command = ['env', '-u', 'PI_DOTFILES_LEGACY_CLAUDE_PID', '-u', 'ANTHROPIC_API_KEY',
                   '-u', 'ANTHROPIC_OAUTH_TOKEN', '-u', 'ANTHROPIC_AUTH_TOKEN', '-u', 'CLAUDE_CODE_OAUTH_TOKEN',
                   f'PI_CODING_AGENT_DIR={profile}', 'PI_OFFLINE=1', 'PI_GOAL_MAX_TURNS=2', executable,
                   '--model', model, '--thinking', 'low', '--no-context-files',
                   '--name', f'unified-smoke-{provider}', '@' + str(brief)]
        if index == 0:
            pane = tmux('new-session', '-d', '-s', name, '-n', provider, '-c', str(cwd), '-x', '140', '-y', '42', '-P', '-F', '#{pane_id}', *command)
        else:
            pane = tmux('new-window', '-d', '-t', name, '-n', provider, '-c', str(cwd), '-P', '-F', '#{pane_id}', *command)
        panes.append((pane, cwd))
    try:
        for (pane, cwd), model in zip(panes, MODELS):
            provider = model.split('/')[0]
            message = wait_reply(profile, cwd, 'E2E_OK_' + provider)
            assert message['provider'] == provider, message['provider']
            assert (cwd / 'smoke.txt').read_text().strip() == 'AFTER_UNIFIED'
            tools = {m.get('toolName') for m in messages(profile, cwd) if m.get('role') == 'toolResult' and not m.get('isError')}
            assert {'bash', 'read', 'write', 'edit'} <= tools, tools
            report['checks'].append({'model': model, 'tools': sorted(tools), 'result': 'pass', 'pane': pane})
            print(f'PASS {model}: bash/write/edit/read and final response', flush=True)
        # Same conversation: switch from Claude -> ChatGPT -> DeepSeek -> Claude.
        pane, cwd = panes[0]
        for i, model in enumerate([MODELS[1], MODELS[2], MODELS[0]]):
            send(pane, '/model ' + model)
            time.sleep(3)
            marker = f'HANDOFF_OK_{i}'
            send(pane, f'Read smoke.txt again. Reply {marker} and its current content. No other work.')
            message = wait_reply(profile, cwd, marker)
            assert message['provider'] == model.split('/')[0], message['provider']
            report['checks'].append({'handoff': model, 'result': 'pass'})
            print('PASS handoff -> ' + model, flush=True)
        # Registry-level evaluator requests must use the same Anthropic route.
        send(pane, '/goal Verify smoke.txt contains AFTER_UNIFIED using read, then state that fact. Do nothing else.')
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            capture = tmux('capture-pane', '-p', '-S', '-120', '-t', pane)
            if 'Goal met:' in capture:
                break
            if 'Goal cleared (evaluator error)' in capture or 'Goal stopped after' in capture:
                raise RuntimeError('Goal evaluator failed; inspect test pane')
            time.sleep(2)
        else:
            send(pane, '/goal clear')
            raise RuntimeError('Goal evaluator timed out')
        report['checks'].append({'goal_evaluator': 'pass'})
        send(panes[1][0], '/usage')
        time.sleep(12)
        capture = tmux('capture-pane', '-p', '-S', '-150', '-t', panes[1][0])
        assert 'LLM usage' in capture and 'deepseek' in capture and 'openai-codex' in capture
        report['checks'].append({'usage_command': 'pass'})
        send(pane, '/compact Preserve smoke.txt state and verification markers; summarize only.')
        time.sleep(15)
        send(pane, 'Read smoke.txt. Reply COMPACT_E2E_OK and its content. No other work.')
        wait_reply(profile, cwd, 'COMPACT_E2E_OK')
        session_files = []
        for file in (profile / 'sessions').glob('**/*.jsonl'):
            entries = [json.loads(line) for line in file.read_text().splitlines()]
            if entries and entries[0].get('cwd') == str(cwd):
                assert any(e.get('type') == 'compaction' for e in entries), 'No persisted compaction'
                session_files.append(file)
        assert len(session_files) == 1
        report['checks'].append({'compaction': 'pass'})
        # Gracefully close only our source pane before reopening its session,
        # avoiding two processes writing the same JSONL file concurrently.
        send(pane, '/quit')
        time.sleep(3)
        resume_command = ['env', f'PI_CODING_AGENT_DIR={profile}', 'PI_OFFLINE=1', executable,
                          '--session', str(session_files[0]), '--no-context-files',
                          'Read smoke.txt. Reply RESUME_E2E_OK and its content. No other work.']
        resumed = tmux('new-window', '-d', '-t', name, '-n', 'resumed-anthropic', '-c', str(cwd), '-P', '-F', '#{pane_id}', *resume_command)
        panes[0] = (resumed, cwd)
        wait_reply(profile, cwd, 'RESUME_E2E_OK')
        report['checks'].append({'resume': 'pass', 'pane': resumed})
    finally:
        for pane, cwd in panes:
            try:
                (cwd / 'pane.txt').write_text(tmux('capture-pane', '-p', '-S', '-250', '-t', pane))
            except subprocess.CalledProcessError:
                pass
        (run / 'report.json').write_text(json.dumps(report, indent=2))
        # Access-only test credentials are disposable. Leave sessions/UI evidence,
        # but remove the temporary credential copy when the bounded test ends.
        (profile / 'auth.json').unlink(missing_ok=True)
        print(f'Inspect windows: tmux attach -t {name}\nReport: {run / "report.json"}', flush=True)


if __name__ == '__main__':
    main()
