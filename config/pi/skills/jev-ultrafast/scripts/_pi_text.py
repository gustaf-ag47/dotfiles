"""Tool-less Pi text generation for upstream TYPE_TEXT; no HTTP server/session files.

Only the pinned upstream's small field_context crosses stdin to a one-shot Node
worker. Credentials stay with Pi; generated values are returned to the caller,
never logged. The outer browser process group still owns this subprocess.
"""
from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path

from _text_backend import resolve_text_backend

SCRIPTS_DIR = Path(__file__).resolve().parent
WORKER = SCRIPTS_DIR / '_pi_text_worker.mjs'
MAX_INPUT_BYTES = 32768
MAX_OUTPUT_BYTES = 65536


class PiTextError(RuntimeError):
    """Safe code only, never raw provider/browser text."""


def find_pi_sdk(env):
    override = env.get('PI_PACKAGE_DIR')
    binary = shutil.which(env.get('PI_TEXT_PI_BIN', 'pi'), path=env.get('PATH'))
    candidates = [Path(override)] if override else list(Path(binary).resolve().parents) if binary else []
    for candidate in candidates:
        try:
            if json.loads((candidate / 'package.json').read_text()).get('name') == '@earendil-works/pi-coding-agent':
                return candidate.resolve()
        except (OSError, ValueError, AttributeError):
            pass
    return None


def prerequisites(env):
    return {'pi_sdk_present': find_pi_sdk(env) is not None,
            'node_present': shutil.which('node', path=env.get('PATH')) is not None}


def _validate_context(context):
    if not isinstance(context, dict) or set(context) != {'goal', 'field', 'page', 'recent_actions'}:
        raise PiTextError('invalid_field_context')
    if not isinstance(context['goal'], str) or not context['goal'].strip():
        raise PiTextError('invalid_field_context')
    for name, allowed in [('field', {'label', 'role', 'value'}), ('page', {'title', 'text'})]:
        item = context[name]
        if not isinstance(item, dict) or set(item) - allowed or any(
            not isinstance(v, str) and not (name == 'field' and v is None) for v in item.values()
        ):
            raise PiTextError('invalid_field_context')
    actions = context['recent_actions']
    if not isinstance(actions, list) or len(actions) > 6 or any(
        not isinstance(a, dict) or set(a) - {'action', 'text'} or
        any(v is not None and not isinstance(v, str) for v in a.values()) for a in actions
    ):
        raise PiTextError('invalid_field_context')
    try:
        raw = json.dumps(context, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, TypeError):
        raise PiTextError('invalid_field_context') from None
    if len(raw) > MAX_INPUT_BYTES:
        raise PiTextError('field_context_too_large')


def _worker_env(env):
    # No browser/TypeSafe/API keys, debug logging variables, JS preload options,
    # inherited agent goals, or unrelated extension settings are forwarded.
    keys = {'PATH', 'HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
            'PI_CODING_AGENT_DIR', 'PI_ANTHROPIC_PROXY_URL', 'CC_PROXY_PORT', 'GROK_HOME',
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
            'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NODE_EXTRA_CA_CERTS', 'LANG', 'LC_ALL'}
    return {**{k: v for k, v in env.items() if k in keys}, 'PI_TELEMETRY': '0'}


def run_worker(cmd, payload, *, env, timeout):
    """Bound BOTH output bytes and total time, including a child that won't read stdin.

    Deliberately inherit the browser wrapper's process group: its hard timeout
    must also terminate this Node worker. On our own timeout/interruption kill and
    reap our direct child; the worker has no tools or browser subprocesses.
    """
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env, cwd=str(SCRIPTS_DIR))
    output = bytearray()
    offset = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as sel:
            os.set_blocking(proc.stdin.fileno(), False)
            os.set_blocking(proc.stdout.fileno(), False)
            sel.register(proc.stdin, selectors.EVENT_WRITE, 'input')
            sel.register(proc.stdout, selectors.EVENT_READ, 'output')
            while sel.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PiTextError('pi_text_timeout')
                for key, _ in sel.select(remaining):
                    if key.data == 'input':
                        try:
                            offset += os.write(key.fd, payload[offset:offset + 4096])
                        except BrokenPipeError:
                            offset = len(payload)
                        if offset == len(payload):
                            sel.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            sel.unregister(proc.stdout)
                            continue
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT_BYTES:
                            raise PiTextError('pi_text_output_too_large')
        try:
            code = proc.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise PiTextError('pi_text_timeout') from None
        return code, bytes(output)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for stream in (proc.stdin, proc.stdout):
            if stream and not stream.closed:
                stream.close()


def pi_field_text(context, *, env=None, runner=run_worker):
    env = dict(os.environ) if env is None else env
    selection = resolve_text_backend(env)
    if selection['status'] != 'pi_configured':
        raise PiTextError('pi_text_not_configured')
    _validate_context(context)
    sdk = find_pi_sdk(env)
    node = shutil.which('node', path=env.get('PATH'))
    if sdk is None or node is None:
        raise PiTextError('pi_text_dependencies_missing')
    agent_dir = Path(env.get('PI_CODING_AGENT_DIR') or Path(env.get('HOME', str(Path.home()))) / '.pi' / 'agent').expanduser().absolute()
    packet = {'model': selection['model'], 'context': context, 'sdkRoot': str(sdk),
              'agentDir': str(agent_dir), 'piDir': str(SCRIPTS_DIR.parents[2]),
              'timeoutMs': int(selection['timeout_seconds'] * 1000)}
    started = time.monotonic()
    try:
        code, output = runner([node, str(WORKER)], json.dumps(packet, ensure_ascii=False).encode(),
                              env=_worker_env(env), timeout=selection['timeout_seconds'])
        result = json.loads(output)
    except PiTextError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise PiTextError('pi_text_failed') from None
    allowed_errors = {'invalid_request', 'invalid_response', 'missing_value', 'model_unavailable',
                      'provider_failed', 'timeout', 'sdk_unavailable'}
    if code != 0 or not isinstance(result, dict) or result.get('ok') is not True:
        reason = result.get('error') if isinstance(result, dict) else None
        reason = reason if isinstance(reason, str) and reason in allowed_errors else 'failed'
        raise PiTextError('pi_text_' + reason)
    text = result.get('text')
    if (not isinstance(text, str) or not text.strip() or len(text) > 2000 or '\0' in text
            or result.get('model') != selection['model']):
        raise PiTextError('pi_text_invalid_response')
    return text, {'model': result['model'], 'latency_ms': round((time.monotonic() - started) * 1000),
                  'usage': result.get('usage')}


def install_pi_text_backend(agent_module, env=None):
    """Replace only upstream's field-text callback; keep its fresh-page guards/executor."""
    env = dict(os.environ) if env is None else dict(env)
    selection = resolve_text_backend(env)
    if selection['status'] != 'pi_configured':
        raise PiTextError('pi_text_not_configured')
    # Freeze the chosen model per run. No later env/config change can reroute a field.
    from _text_backend import pin_backend_env
    pinned = pin_backend_env(env, selection)
    agent_module.field_text = lambda context: pi_field_text(context, env=pinned)


def configure_text_backend(agent_module, env=None):
    env = dict(os.environ) if env is None else env
    selection = resolve_text_backend(env)
    if selection['status'] not in ('pi_configured', 'configured', 'unset'):
        raise PiTextError('invalid_text_backend')
    original_name = '_dotfiles_original_field_text'
    if not hasattr(agent_module, original_name):
        setattr(agent_module, original_name, agent_module.field_text)
    if selection['status'] == 'pi_configured':
        install_pi_text_backend(agent_module, env)
    elif selection['backend'] == 'api' and selection['status'] == 'configured':
        agent_module.field_text = getattr(agent_module, original_name)
    elif selection['status'] == 'unset':
        def disabled(_context):
            raise PiTextError('typing_disabled')
        agent_module.field_text = disabled
    else:
        raise PiTextError('invalid_text_backend')
    return selection['backend']
