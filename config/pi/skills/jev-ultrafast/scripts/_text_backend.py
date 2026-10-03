"""Explicit text backend selection. No credentials, browser, or network operations."""
from __future__ import annotations

import json
import math
from pathlib import Path

from _bounded import resolve_text_model_config

PI_PROVIDERS = frozenset({'openai-codex', 'anthropic', 'grok-build'})
API_FIELDS = ('TEXT_MODEL_API_KEY', 'TEXT_MODEL_BASE_URL', 'TEXT_MODEL')
DEFAULT_TIMEOUT = 30


def config_path(env):
    base = Path(env.get('XDG_CONFIG_HOME') or Path(env.get('HOME', str(Path.home()))) / '.config')
    return base / 'jev-ultrafast' / 'text-model.json'


def valid_pi_model(model):
    if not isinstance(model, str) or len(model) > 200 or '/' not in model:
        return False
    provider, model_id = model.split('/', 1)
    return provider in PI_PROVIDERS and bool(model_id) and all(
        c.isascii() and (c.isalnum() or c in '._-') for c in model_id)


def _saved_config(env):
    try:
        with config_path(env).open('rb') as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) - {'backend', 'model', 'timeout_seconds'}:
            raise ValueError()
        return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeError):
        return None


def resolve_text_backend(env):
    """Environment selection wins; saved Pi selection is never an API fallback.

    The existing all-three-or-none API contract remains intact. No configured
    backend means click-only mode. Errors expose stable codes, not raw values.
    """
    explicit = (env.get('TEXT_MODEL_BACKEND') or '').strip()
    pi_model = (env.get('PI_TEXT_MODEL') or '').strip()
    api_present = any((env.get(k) or '').strip() for k in API_FIELDS)
    result = {'backend': 'none', 'status': 'unset', 'model': None,
              'timeout_seconds': DEFAULT_TIMEOUT, 'reason': None}
    if explicit == 'none':
        return result
    if explicit and explicit not in ('pi', 'api'):
        return {**result, 'status': 'invalid_config', 'reason': 'unknown_backend'}
    # An explicit API environment must not be silently replaced by a saved Pi choice.
    backend = explicit or ('pi' if pi_model else 'api' if api_present else '')
    if backend == 'api':
        if pi_model:
            return {**result, 'status': 'invalid_config', 'reason': 'mixed_backends'}
        status, detail = resolve_text_model_config(env)
        return {**result, 'backend': 'api', 'status': status, 'reason': detail}
    if backend == 'pi' and api_present:
        return {**result, 'status': 'invalid_config', 'reason': 'mixed_backends'}
    saved = {} if backend == 'pi' and pi_model else _saved_config(env)
    if saved is None:
        return {**result, 'status': 'invalid_config', 'reason': 'invalid_saved_config'}
    backend = backend or saved.get('backend', 'none')
    if backend == 'none':
        return result
    if backend != 'pi':
        return {**result, 'status': 'invalid_config', 'reason': 'saved_backend_must_be_pi'}
    model = pi_model or saved.get('model')
    if not valid_pi_model(model):
        return {**result, 'backend': 'pi', 'status': 'invalid_config', 'reason': 'invalid_pi_model'}
    try:
        raw_timeout = env.get('PI_TEXT_TIMEOUT_SECONDS', saved.get('timeout_seconds', DEFAULT_TIMEOUT))
        if isinstance(raw_timeout, bool):
            raise ValueError()
        timeout = float(raw_timeout)
        if not math.isfinite(timeout) or not 1 <= timeout <= 60:
            raise ValueError()
    except (TypeError, ValueError):
        return {**result, 'backend': 'pi', 'status': 'invalid_config', 'reason': 'invalid_pi_timeout'}
    return {**result, 'backend': 'pi', 'status': 'pi_configured', 'model': model,
            'timeout_seconds': timeout}


def pin_backend_env(env, selection):
    """Freeze one run's selected backend; changes to disk config cannot switch it."""
    result = dict(env)
    result['TEXT_MODEL_BACKEND'] = selection['backend']
    if selection['backend'] == 'pi':
        result['PI_TEXT_MODEL'] = selection['model']
        result['PI_TEXT_TIMEOUT_SECONDS'] = str(selection['timeout_seconds'])
    return result
