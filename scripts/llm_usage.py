#!/usr/bin/env python3
"""Read-only usage adapters. Never refresh OAuth, execute key commands, or log tokens."""
import argparse
import base64
import concurrent.futures
import datetime
import sys
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import math
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_json(url, headers=None):
    # Do not send local pool telemetry through an inherited HTTP proxy.
    handlers = [NoRedirect()]
    if urllib.parse.urlsplit(url).hostname in ('127.0.0.1', '::1'):
        handlers.append(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={'Accept': 'application/json', **(headers or {})})
    with urllib.request.build_opener(*handlers).open(req, timeout=8) as response:
        return json.loads(response.read(1024 * 1024))


def local_url():
    raw = os.environ.get('PI_ANTHROPIC_PROXY_URL', f"http://127.0.0.1:{os.environ.get('CC_PROXY_PORT', '8788')}")
    url = urllib.parse.urlsplit(raw)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1')
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('Expected an HTTP loopback proxy origin')
    return raw.rstrip('/')


def numeric(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def boolean(value):
    return value if isinstance(value, bool) else None


def text(value):
    return value if isinstance(value, str) and value else None


# Hard-coded; neither endpoint returns its top-up page (see docs/research/openai-deepseek-account-introspection.md).
CODEX_TOPUP_URL = 'https://chatgpt.com/codex/settings/usage'
DEEPSEEK_TOPUP_URL = 'https://platform.deepseek.com/top_up'


def decode_jwt_payload(token):
    """Payload segment decoded locally: no signature check, no network, display-only."""
    parts = str(token).split('.')
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, UnicodeDecodeError):  # binascii.Error is a ValueError
        return None
    return payload if isinstance(payload, dict) else None


def jwt_claims(token):
    """Display-only identity from the access token: payload segment decoded locally, no signature check, no network."""
    payload = decode_jwt_payload(token)
    if payload is None:
        return {}
    profile = payload.get('https://api.openai.com/profile')
    scope = payload.get('https://api.openai.com/auth')
    profile = profile if isinstance(profile, dict) else {}
    scope = scope if isinstance(scope, dict) else {}
    claims = {'email': text(profile.get('email')), 'name': text(profile.get('name')),
              'plan': text(scope.get('chatgpt_plan_type'))}
    return {key: value for key, value in claims.items() if value}


def quota_window(name, window):
    if not isinstance(window, dict):
        return None
    return {'name': name, 'used_percent': numeric(window.get('used_percent')),
            'window_seconds': numeric(window.get('limit_window_seconds')), 'reset_at': numeric(window.get('reset_at'))}


def anthropic(_auth):
    data = get_json(local_url() + '/_usage')
    accounts = []
    for token in data['tokens']:
        quota = token.get('quota') or {}
        windows = []
        for name, header, reset in [('five_hour', 'u5', 'u5_reset'), ('seven_day', 'u7', 'u7_reset'),
                                    ('seven_day_overage_included', 'u7_oi', 'u7_oi_reset'),
                                    ('seven_day_opus', None, None), ('seven_day_sonnet', None, None)]:
            bucket = quota.get(name) or {}
            used = numeric(bucket.get('utilization'))
            source = 'quota API'
            if used is None:
                value = numeric(token.get(header)) if header else None
                used = value * 100 if value is not None else None
                source = 'header observation (may be stale)'
            if used is not None or name in ('five_hour', 'seven_day'):
                forecast_key = {'five_hour': '5h', 'seven_day': '7d', 'seven_day_overage_included': '7d_oi'}.get(name)
                windows.append({'name': name, 'used_percent': used,
                                'resets_at': bucket.get('resets_at') or bucket.get('reset_at') or token.get(reset),
                                'forecast': (token.get('forecast') or {}).get(forecast_key),
                                'source': source if used is not None else 'unavailable'})
        counters = token.get('counters') or {}
        accounts.append({'account': token.get('fp'), 'label': token.get('label') or '', 'valid': token.get('valid'),
                         'forced_down': token.get('forced_down', False),
                         'cooldown_until': token.get('cooldown_until'),
                         'model_cooldowns': token.get('model_cooldowns', {}),
                         'quota_scope_denied': token.get('quota_scope_denied', False),
                         'quota_checked_at': token.get('quota_checked_at'),
                         'windows': windows,
                         'observed': {key: numeric(counters.get(key)) for key in
                                      ('requests', 'input_tokens', 'output_tokens',
                                       'cache_read_input_tokens', 'cache_creation_input_tokens')}})
    return {'status': 'ok', 'kind': 'subscription quota', 'accounts': accounts,
            'routing': data.get('routing'),
            'note': 'Counters cover proxy traffic, including retries; they are not account-wide billing.'}


def codex(auth):
    credential = auth.get('openai-codex') or {}
    if credential.get('type') != 'oauth' or not credential.get('access'):
        return {'status': 'unavailable', 'reason': 'Log in to openai-codex in Pi.'}
    claims = jwt_claims(credential['access'])
    # Whitelisted identity only: 6-char account prefix, never user ids or the full account id.
    account = {'email': claims.get('email'), 'name': claims.get('name'), 'plan': claims.get('plan'),
               'account_id': str(credential.get('accountId') or '')[:6] or None}
    who = account['email'] or 'this account'
    if not numeric(credential.get('expires')) or credential['expires'] <= time.time() * 1000:
        return {'status': 'unavailable', 'account': account,
                'reason': f'OAuth for {who} expired; log in with Pi. This reader never refreshes tokens.'}
    headers = {'Authorization': 'Bearer ' + credential['access'], 'User-Agent': 'pi-llm-usage'}
    if credential.get('accountId'):
        headers['ChatGPT-Account-Id'] = credential['accountId']
    try:
        data = get_json('https://chatgpt.com/backend-api/wham/usage', headers)
    except urllib.error.HTTPError as error:
        return {'status': 'unavailable', 'account': account,
                'reason': f'Usage endpoint HTTP {error.code} for {who}; inference may still work.'}
    if not isinstance(data, dict):
        data = {}
    account['email'] = text(data.get('email')) or account['email']
    account['plan'] = text(data.get('plan_type')) or account['plan']
    limits = data.get('rate_limit') if isinstance(data.get('rate_limit'), dict) else {}
    windows = [w for w in (quota_window(name, limits.get(name)) for name in ('primary_window', 'secondary_window')) if w]
    for extra in data.get('additional_rate_limits') or []:
        if isinstance(extra, dict):
            inner = extra.get('rate_limit') if isinstance(extra.get('rate_limit'), dict) else {}
            window = quota_window(text(extra.get('limit_name')) or 'additional', inner.get('primary_window'))
            if window:
                windows.append(window)
    if not windows:
        return {'status': 'unavailable', 'account': account,
                'reason': 'Subscription endpoint returned no recognized quota windows.'}
    models = {}
    for slug, row in (data.get('model_usage') or {}).items() if isinstance(data.get('model_usage'), dict) else ():
        if isinstance(row, dict) and isinstance(slug, str):
            models[slug] = {'available': boolean(row.get('available')), 'available_at': text(row.get('available_at')),
                            'credits_would_enable': boolean(row.get('credits_would_enable'))}
    raw_credits = data.get('credits') if isinstance(data.get('credits'), dict) else {}
    balance = raw_credits.get('balance')
    credits = {'balance': balance if isinstance(balance, str) else str(balance) if numeric(balance) is not None else None,
               **{key: boolean(raw_credits.get(key)) for key in ('has_credits', 'unlimited', 'overage_limit_reached')}}
    reached = data.get('rate_limit_reached_type') if isinstance(data.get('rate_limit_reached_type'), dict) else {}
    upsell = data.get('rate_limit_upsell') if isinstance(data.get('rate_limit_upsell'), dict) else {}
    reset_credits = data.get('rate_limit_reset_credits') if isinstance(data.get('rate_limit_reset_credits'), dict) else {}
    return {'status': 'ok', 'kind': 'subscription quota', 'account': account, 'windows': windows,
            'allowed': boolean(limits.get('allowed')), 'limit_reached': boolean(limits.get('limit_reached')),
            'reached_type': text(reached.get('type')), 'upsell': text(upsell.get('title')),
            'models': models, 'credits': credits, 'reset_credits': numeric(reset_credits.get('available_count')),
            'topup_url': CODEX_TOPUP_URL,
            'note': 'ChatGPT subscription only; read-only internal endpoint, not OpenAI API billing.'}


def codex_on_credits(info):
    credits = info.get('credits') or {}
    return bool((credits.get('has_credits') or credits.get('unlimited')) and not credits.get('overage_limit_reached'))


def deepseek_key(auth):
    credential = auth.get('deepseek')
    if credential is not None:
        if credential.get('type') != 'api_key':
            return None
        key = credential.get('key') or ''
        if key.startswith('!'):
            return None  # Status tools must not execute arbitrary credential commands.
        env = {**os.environ, **credential.get('env', {})}
        return re.sub(r'\$\{(\w+)\}|\$(\w+)', lambda m: env.get(m[1] or m[2], ''), key) or None
    return os.environ.get('DEEPSEEK_API_KEY')


def deepseek_label(auth, key):
    """Identity is not queryable with an API key; order per operator decision #6: env, auth.json label, key suffix."""
    env_label = text(os.environ.get('DEEPSEEK_ACCOUNT_LABEL'))
    if env_label:
        return env_label, 'env'
    credential = auth.get('deepseek')
    stored = text(credential.get('label')) if isinstance(credential, dict) else None
    if stored:
        return stored, 'auth.json'
    return f'key \u2026{key[-4:]}', 'key'  # Never the first characters of a key.


def deepseek(auth):
    key = deepseek_key(auth)
    if not key:
        return {'status': 'unavailable', 'reason': 'No supported DeepSeek API key configured (credential commands are not executed).'}
    label, label_source = deepseek_label(auth, key)
    data = get_json('https://api.deepseek.com/user/balance', {'Authorization': 'Bearer ' + key})
    if not isinstance(data, dict):
        data = {}
    balances = [{key: row.get(key) for key in ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')}
                for row in data.get('balance_infos') or [] if isinstance(row, dict)]
    if not balances:
        return {'status': 'unavailable', 'label': label, 'reason': f'Balance endpoint returned no recognized balances for {label}.'}
    return {'status': 'ok', 'kind': 'prepaid balance', 'label': label, 'label_source': label_source,
            'available': boolean(data.get('is_available')), 'balances': balances, 'topup_url': DEEPSEEK_TOPUP_URL,
            'note': 'Balance is not a subscription quota or a session cost estimate.'}


# cli-chat-proxy.grok.com is the Grok Build CLI's own backend, not the documented
# xAI Inference API; see docs/research/grok-oauth-pi-community.md and
# docs/research/grok-usage-implementation.md. This adapter mirrors the community
# adapter's reverse-engineered quota probe (GET /v1/user, GET /v1/billing) but
# never calls it for inference, and -- like every other adapter in this file --
# reads only the token Pi's own grok-build OAuth provider already resolved into
# auth.json; it never touches ~/.grok/auth.json and never refreshes anything.
GROK_BASE_URL = 'https://cli-chat-proxy.grok.com/v1'
GROK_DEFAULT_CLIENT_VERSION = '1.0.5'


def grok_money(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, dict):
        inner = value.get('val')
        if isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return inner
    return None


def grok_clamp_percent(value):
    n = numeric(value)
    return max(0.0, min(100.0, float(n))) if n is not None else None


def grok_ratio_percent(used, limit):
    if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
        return grok_clamp_percent(100.0 * used / limit)
    return None


def grok_build(auth):
    """Grok quota via Pi's grok-build OAuth credential in auth.json, read-only.

    Pi's native OAuth login/refresh for grok-build is owned elsewhere (sibling
    work); this adapter only reads the access token Pi already resolved, exactly
    like the Codex adapter above, and never refreshes it itself.
    """
    credential = auth.get('grok-build') or {}
    if credential.get('type') != 'oauth' or not credential.get('access'):
        return {'status': 'unavailable', 'reason': 'Log in to grok-build in Pi.'}
    access = credential['access']
    claims = decode_jwt_payload(access) or {}
    email = text(claims.get('email')) or text(credential.get('email'))
    who = email or 'this account'
    if not numeric(credential.get('expires')) or credential['expires'] <= time.time() * 1000:
        return {'status': 'unavailable', 'account': {'email': email},
                'reason': f'OAuth for {who} expired; use Pi to refresh/login. This reader never refreshes tokens.'}
    headers = {'Authorization': 'Bearer ' + access, 'X-XAI-Token-Auth': 'xai-grok-cli',
               'x-authenticateresponse': 'authenticate-response',
               'x-grok-client-version': text(os.environ.get('GROK_CLIENT_VERSION')) or GROK_DEFAULT_CLIENT_VERSION,
               'x-grok-client-identifier': text(os.environ.get('GROK_CLIENT_NAME')) or 'pi',
               'x-grok-client-mode': 'interactive'}
    try:
        user = get_json(GROK_BASE_URL + '/user?include=subscription', headers)
        billing = get_json(GROK_BASE_URL + '/billing?format=credits', headers)
    except urllib.error.HTTPError as error:
        return {'status': 'unavailable', 'account': {'email': email},
                'reason': f'Quota endpoint HTTP {error.code} for {who}; inference may still work.'}
    user = user if isinstance(user, dict) else {}
    billing = billing if isinstance(billing, dict) else {}
    config = billing.get('config') if isinstance(billing.get('config'), dict) else {}
    period = config.get('currentPeriod') if isinstance(config.get('currentPeriod'), dict) else {}
    is_weekly = text(period.get('type')) == 'USAGE_PERIOD_TYPE_WEEKLY'
    resets_at = text(period.get('end')) or text(config.get('billingPeriodEnd'))
    monthly_limit = grok_money(config.get('monthlyLimit'))
    used = grok_money(config.get('used'))
    used_percent = grok_clamp_percent(config.get('creditUsagePercent'))
    if used_percent is None:
        used_percent = grok_ratio_percent(used, monthly_limit)
    windows = [{'name': 'weekly' if is_weekly else 'monthly', 'used_percent': used_percent, 'used': used,
                'limit': monthly_limit, 'unit': 'credits', 'resets_at': resets_at}]
    on_demand_cap = grok_money(config.get('onDemandCap'))
    if on_demand_cap is not None and on_demand_cap > 0:
        windows.append({'name': 'on_demand_cap', 'used_percent': None, 'used': None, 'limit': on_demand_cap,
                        'unit': 'credits', 'resets_at': resets_at})
    account = {'email': email or text(user.get('email')), 'plan': text(user.get('subscriptionTier'))}
    return {'status': 'ok', 'kind': 'subscription quota', 'account': account, 'windows': windows,
            'note': 'Grok Build CLI OAuth session via the unofficial cli-chat-proxy.grok.com backend '
                    '(reverse-engineered, not an xAI-documented API); read-only, never refreshes.'}


ADAPTERS = {'anthropic': anthropic, 'openai-codex': codex, 'deepseek': deepseek, 'grok-build': grok_build}

# The adapter payloads above intentionally remain provider-shaped for the
# existing renderers and proxy integrations.  Consumers of the report should
# use this deliberately boring, provider-neutral projection instead.
REPORT_SCHEMA = 'llm-usage.v1'
REPORT_SOURCES = {
    'anthropic': 'Anthropic proxy _usage observations',
    'openai-codex': 'ChatGPT Codex wham/usage (private endpoint)',
    'deepseek': 'DeepSeek balance API',
    'grok-build': 'Grok Build CLI quota probe (cli-chat-proxy.grok.com, unofficial)',
}


def _freshness(checked_at, now=None):
    now = time.time() if now is None else now
    age = max(0, int(now - checked_at))
    return {'observed_at': datetime.datetime.fromtimestamp(checked_at, datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
            'age_seconds': age, 'state': 'fresh' if age < 300 else 'stale'}


def _observation(provider, raw, checked_at):
    status = raw.get('status', 'unknown')
    freshness = _freshness(checked_at)
    if status != 'ok':
        state = 'scope_denied' if 'scope' in str(raw.get('reason', '')).lower() else 'failed'
        return {'provider': provider, 'status': status, 'source': REPORT_SOURCES.get(provider, 'provider adapter'),
                'reason': raw.get('reason'), 'freshness': {**freshness, 'state': state}, 'confidence': 'none',
                'quota': {'windows': []}, 'credits': {'balances': []},
                'reset_entitlements': {'available_count': None, 'items': []},
                'availability': {'provider': None, 'models': {}}, 'telemetry': {},
                'forecasts': {}, 'unknowns': ['quota', 'credits', 'reset_entitlements', 'availability']}
    return None


def normalize_provider(provider, raw, checked_at):
    """Return the stable, redacted report contract for one provider.

    None is intentional: it means unknown, never zero.  ``unknowns`` keeps
    that distinction machine-readable when an adapter or scope is incomplete.
    """
    failed = _observation(provider, raw, checked_at)
    if failed:
        return failed
    freshness = _freshness(checked_at)
    confidence = 'high'
    quota, credits, resets, availability, telemetry, forecasts = [], {'balances': [], 'state': 'unknown'}, {'available_count': None, 'items': [], 'state': 'unknown'}, {'provider': None, 'models': {}, 'state': 'unknown'}, {}, {}
    if provider == 'anthropic':
        confidence = 'medium'
        accounts = raw.get('accounts') if isinstance(raw.get('accounts'), list) else []
        for account in accounts:
            if not isinstance(account, dict):
                continue
            windows = []
            account_windows = account.get('windows') if isinstance(account.get('windows'), list) else []
            for window in account_windows:
                if not isinstance(window, dict):
                    continue
                item = {'account': account.get('account'), 'name': window.get('name'),
                        'used_percent': window.get('used_percent'), 'remaining_percent':
                        None if not numeric(window.get('used_percent')) else max(0, 100 - window['used_percent']),
                        'reset_at': window.get('resets_at') or window.get('reset_at'),
                        'source': window.get('source'),
                        'freshness': 'stale' if str(window.get('source', '')).startswith('header') else freshness['state'],
                        'state': 'unknown' if window.get('used_percent') is None else 'known'}
                windows.append(item)
                if window.get('forecast') is not None: forecasts[f"{account.get('account')}:{window.get('name')}"] = window['forecast']
            quota.append({'account': account.get('account'), 'label': account.get('label'), 'windows': windows,
                          'state': 'scope_denied' if account.get('quota_scope_denied') else 'known'})
            telemetry[account.get('account') or 'unknown'] = account.get('observed', {})
        availability['provider'] = any(a.get('valid') and not a.get('forced_down') for a in accounts)
        if any(w.get('freshness') == 'stale' for q in quota for w in q.get('windows', [])):
            freshness = {**freshness, 'state': 'stale'}
            confidence = 'low'
    elif provider == 'openai-codex':
        windows = raw.get('windows') if isinstance(raw.get('windows'), list) else []
        quota = [{'name': w.get('name'), 'used_percent': w.get('used_percent'),
                  'remaining_percent': None if not numeric(w.get('used_percent')) else max(0, 100-w['used_percent']),
                  'window_seconds': w.get('window_seconds'), 'reset_at': w.get('reset_at'), 'state': 'known'}
                 for w in windows if isinstance(w, dict)]
        raw_credits = raw.get('credits') if isinstance(raw.get('credits'), dict) else {}
        balance = raw_credits.get('balance')
        valid_balance = isinstance(balance, str) or numeric(balance) is not None
        credits = {'balances': [{'balance': balance, 'unit': 'provider-native'}],
                   'state': 'known' if valid_balance else 'unknown'}
        reset_count = raw.get('reset_credits') if numeric(raw.get('reset_credits')) is not None else None
        resets = {'available_count': reset_count, 'items': [],
                  'state': 'known' if reset_count is not None else 'unknown'}
        models = raw.get('models') if isinstance(raw.get('models'), dict) else {}
        availability = {'provider': boolean(raw.get('allowed')), 'models': models}
        confidence = 'medium'  # private Codex endpoint; useful but not a public contract
    elif provider == 'grok-build':
        windows_raw = raw.get('windows') if isinstance(raw.get('windows'), list) else []
        quota = [{'name': w.get('name'), 'used_percent': w.get('used_percent'),
                  'remaining_percent': None if not numeric(w.get('used_percent')) else max(0, 100 - w['used_percent']),
                  'reset_at': w.get('resets_at'), 'state': 'known' if numeric(w.get('used_percent')) is not None else 'unknown'}
                 for w in windows_raw if isinstance(w, dict)]
        confidence = 'low'  # unofficial, reverse-engineered endpoint; schema not guaranteed by xAI
    else:
        balances = [{**row, 'unit': row.get('currency')} for row in raw.get('balances', [])
                    if isinstance(row, dict)]
        credits = {'balances': balances, 'state': 'known' if balances else 'unknown'}
        availability['provider'] = boolean(raw.get('available'))
        confidence = 'high'
    unknowns = []
    for name, value in (('quota', quota), ('credits', credits), ('reset_entitlements', resets), ('availability', availability)):
        if value in (None, [], {'balances': []}, {'provider': None, 'models': {}}) or (isinstance(value, dict) and value.get('state') == 'unknown'):
            unknowns.append(name)
    return {'provider': provider, 'status': 'ok', 'source': REPORT_SOURCES.get(provider, 'provider adapter'),
            'reason': None, 'account': raw.get('account') or raw.get('label'),
            'freshness': freshness, 'confidence': confidence, 'quota': {'windows': quota},
            'credits': credits, 'reset_entitlements': resets, 'availability': availability,
            'telemetry': telemetry, 'forecasts': forecasts, 'unknowns': unknowns}


def safe_query(provider, auth):
    try:
        result = ADAPTERS[provider](auth)
    except urllib.error.HTTPError as error:
        result = {'status': 'unavailable', 'reason': f'Usage endpoint HTTP {error.code}; inference may still work.'}
    except Exception as error:
        # No exception text/response bodies: either could carry credentials.
        result = {'status': 'unavailable', 'reason': f'Usage lookup failed ({type(error).__name__}).'}
    checked_at = int(time.time())
    return provider, {**result, 'checked_at': checked_at,
                      'normalized': normalize_provider(provider, result, checked_at)}


def collect(auth, providers):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return dict(pool.map(lambda p: safe_query(p, auth), providers))


WINDOW_LABELS = {'five_hour': '5h', 'seven_day': '7d', 'seven_day_overage_included': '7d fable',
                 'seven_day_opus': '7d opus', 'seven_day_sonnet': '7d sonnet'}
BAR_WIDTH = 20


def use_color():
    return sys.stdout.isatty() and not os.environ.get('NO_COLOR')


def paint(text, code):
    return f'\033[{code}m{text}\033[0m' if use_color() else text


def to_epoch(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return None


def until(epoch, now):
    if epoch is None:
        return '?'
    seconds = int(epoch - now)
    if seconds <= 0:
        return 'passed'
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f'{days}d {hours:02d}h'
    if hours:
        return f'{hours}h {minutes:02d}m'
    return f'{minutes}m'


def bar(left):
    filled = round(left / 100 * BAR_WIDTH)
    body = '█' * filled + '░' * (BAR_WIDTH - filled)
    return paint(body, '32' if left >= 50 else '33' if left >= 20 else '31')


def duration_label(seconds):
    if not seconds:
        return None
    return f'{seconds // 86400}d' if seconds % 86400 == 0 else f'{seconds / 3600:g}h'


def window_label(window):
    name = window['name']
    if name in WINDOW_LABELS:
        return WINDOW_LABELS[name]
    duration = duration_label(window.get('window_seconds'))
    if name in ('primary_window', 'secondary_window'):
        return duration or name
    return f'{name} {duration}' if duration else name  # additional_rate_limits keep their limit_name


def window_line(window, now):
    used = window.get('used_percent')
    reset = to_epoch(window.get('resets_at') or window.get('reset_at'))
    label = window_label(window)
    if reset is not None and reset <= now:
        # Reset passed since the last reading: assume a fresh window (what the
        # proxy's router assumes too) until the next response confirms it.
        return f'    {label:<9} {bar(100)} {paint("~100% left", "32")}  window reset; unconfirmed'
    if used is None:
        return f'    {label:<9} {"?" * BAR_WIDTH}   ?% left'
    left = max(0.0, min(100.0, 100 - used))
    stale = window.get('source', '').startswith('header')
    tail = f'resets in {until(reset, now)}'
    fc = window.get('forecast') or {}
    state = fc.get('forecast')
    burn = fc.get('burn_per_hour')
    if isinstance(burn, (int, float)):
        tail += f' · burn {burn * 100:.1f}%/h'
    if state == 'waste':
        projected = fc.get('projected_at_reset')
        tail += paint(f' · will waste ~{max(0, (1-projected)*100):.0f}%', '33') if isinstance(projected, (int, float)) else paint(' · will waste', '33')
    elif state == 'exhaust':
        exhaust_at = fc.get('exhaust_at')
        tail += paint(' · exhausts in ' + until(to_epoch(exhaust_at), now), '31;1')
    elif state == 'on_track':
        tail += paint(' · on track', '32')
    if stale:
        tail += ' ~'
    pct = paint(f'{left:3.0f}% left', '1' if left < 20 else '0')
    return f'    {label:<9} {bar(left)} {pct}   {tail}'


def account_status(group, now):
    if group.get('forced_down'):
        return paint('OFFLINE', '31;1')
    if not group.get('valid'):
        return paint('PARKED', '31;1')
    cooldown = to_epoch(group.get('cooldown_until'))
    if cooldown and cooldown > now:
        return paint(f'COOLDOWN {until(cooldown, now)}', '31;1')
    # Expired observations cannot establish current exhaustion.
    exhausted = [w for w in group.get('windows', [])
                 if (w.get('used_percent') or 0) >= 100
                 and not ((r := to_epoch(w.get('resets_at') or w.get('reset_at'))) is not None and r <= now)]
    if any(w['name'] == 'five_hour' for w in exhausted):
        return paint('EXHAUSTED', '31;1')
    if exhausted or any((to_epoch(r) or 0) > now for r in group.get('model_cooldowns', {}).values()):
        return paint('PARTIAL · model/bucket limited', '33;1')
    if not any(w.get('used_percent') is not None
               and (to_epoch(w.get('resets_at') or w.get('reset_at')) or 0) > now
               for w in group.get('windows', [])):
        return paint('UNKNOWN · awaiting fresh reading', '33;1')
    return paint('READY', '32;1')


BUCKET_LABELS = {'base': 'opus/sonnet (7d)', 'oi': 'fable (7d fable)'}


def account_name(fp, labels):
    return labels.get(fp) or fp or '?'


def routing_lines(routing, labels):
    if not isinstance(routing, dict):
        return []
    width = max((len(account_name(r['fp'], labels)) for b in routing['buckets'].values() for r in b.get('ranking', [])), default=12)
    lines = ['', paint('routing', '1') + f"  mode={routing.get('mode')} threshold={routing.get('threshold')}"]
    count = routing.get('starved', 0)
    lines.append('  starved this week: ' + paint(str(count), '31;1' if count else '32') )
    summary = routing.get('forecast') or {}
    if summary:
        waste = summary.get('weekly_waste_percent')
        first = summary.get('first_exhaust')
        lines.append('  forecast  weekly waste ' + (f'{waste:.1f}%' if isinstance(waste, (int, float)) else '?') +
                     (f" · first exhaust {first.get('fp')} {first.get('window')} at {first.get('at')}" if first else ' · no projected exhaust'))
        for event in routing.get('recent', [])[-3:]:
            ts = str(event.get('ts', ''))[11:16] or '--:--'
            lines.append(f"  {ts} {event.get('bucket') or event.get('kind','route')} {event.get('from_fp') or event.get('from')}→{event.get('to_fp') or event.get('to')} {event.get('reason','')}")
    for key, bucket in routing['buckets'].items():
        chosen = bucket.get('would_pick')
        head = paint(account_name(chosen, labels), '32;1') if chosen else paint('NONE ROUTABLE', '31;1')
        sticky = '  (sticky)' if chosen and chosen == bucket.get('last_pick') else ''
        lines.append(f"  {BUCKET_LABELS.get(key, key):<18} \u2192 {head}{sticky}")
        for row in bucket.get('ranking', []):
            util = row.get('utilization')
            left = f'{100 - util * 100:3.0f}% left' if util is not None else '  ?% left'
            if row.get('eligible'):
                mark = paint('\u25cf', '32') if row['fp'] == chosen else paint('\u25cb', '2')
                detail = f'pressure {row["pressure"] * 1e6:.2f}'
            else:
                mark = paint('\u2715', '31')
                detail = paint(row.get('reason') or 'ineligible', '31')
            lines.append(f"      {mark} {account_name(row['fp'], labels):<{width}}  {left}  {detail}")
    return lines


def anthropic_lines(info, now):
    lines, stale = [], False
    labels = {g['account']: g.get('label') for g in info.get('accounts', []) if g.get('label')}
    for group in info.get('accounts', []):
        lines.append(f"  {paint(account_name(group['account'], labels), '1')}  {account_status(group, now)}")
        for model, reset in group.get('model_cooldowns', {}).items():
            if (to_epoch(reset) or 0) > now:
                lines.append(f"    {paint(f'{model} cooldown {until(to_epoch(reset), now)}', '31')}")
        for window in group.get('windows', []):
            stale |= window.get('source', '').startswith('header')
            lines.append(window_line(window, now))
    return lines + routing_lines(info.get('routing'), labels), stale


def codex_identity(info):
    account = info.get('account') or {}
    plan = f" ({account['plan']})" if account.get('plan') else ''
    return f"{account.get('email') or '?'}{plan}"


def codex_lines(info, now):
    blocked = info.get('allowed') is False or info.get('limit_reached') is True
    if not blocked:
        verdict = paint('READY', '32;1')
    elif codex_on_credits(info):
        verdict = paint('LIMIT REACHED \u00b7 running on credits', '33;1')
    else:
        verdict = paint('LIMIT REACHED', '31;1')
    lines = [f"  {paint(codex_identity(info), '1')}  {verdict}"]
    forecasts = info.get('forecast') or {}
    lines += [window_line({**window, 'forecast': forecasts.get(window.get('name'))}, now)
              for window in info.get('windows', [])]
    credits = info.get('credits') or {}
    balance = f" (balance {credits['balance']})" if credits.get('balance') is not None else ''
    credit_state = []
    if credits.get('has_credits') is True:
        credit_state.append('enabled')
    elif credits.get('has_credits') is False:
        credit_state.append('none')
    if credits.get('unlimited') is True:
        credit_state.append('unlimited')
    if credits.get('overage_limit_reached') is True:
        credit_state.append('overage limit reached')
    if credit_state or balance:
        lines.append('    credits: ' + ', '.join(credit_state) + balance)
    for slug, row in (info.get('models') or {}).items():
        if row.get('available') is False:
            when = to_epoch(row.get('available_at'))
            line = f'{slug} unavailable' + (f' until {until(when, now)}' if when is not None else '')
            if row.get('credits_would_enable'):
                line += f' \u2014 credits would unlock it{balance}'
            lines.append('    ' + paint(line, '31'))
        elif row.get('available') is True:
            lines.append('    ' + paint(f'{slug} available', '32'))
    if blocked:
        tail = f"    top up: {info.get('topup_url') or CODEX_TOPUP_URL}"
        if info.get('reset_credits') is not None:
            tail += f"   reset credits: {info['reset_credits']:g}"
        lines.append(paint(tail, '2'))
    elif info.get('reset_credits') is not None:
        lines.append(paint(f"    reset credits available: {info['reset_credits']:g}", '2'))
    return lines, False


def money(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def deepseek_lines(info, _now):
    balances = info.get('balances') or []
    totals = [money(row.get('total_balance')) for row in balances]
    funded = info.get('available') is not False and any(total is not None and total > 0 for total in totals)
    verdict = paint('READY', '32;1') if funded else paint('EXHAUSTED', '31;1')
    lines = [f"  {paint(info.get('label') or '?', '1')}  {verdict}"]
    if isinstance(info.get('monthly_cap'), (int, float)):
        spent, cap = info.get('monthly_spend', 0), info['monthly_cap']
        lines.append(f"  cap ${spent:.2f}/${cap:.2f}" + (paint(' (reached)', '31;1') if spent >= cap else ''))
    for row, total in zip(balances, totals):
        ok = total is not None and total > 0 and info.get('available') is not False
        amount = f"{row.get('total_balance')} {row.get('currency')}"
        line = f"    balance {paint(amount, '32;1' if ok else '31;1')}"
        if not ok:
            line += '   ' + paint('UNAVAILABLE', '31;1')
        if row.get('granted_balance') is not None or row.get('topped_up_balance') is not None:
            line += paint(f"   (granted {row.get('granted_balance')} \u00b7 topped-up {row.get('topped_up_balance')})", '2')
        lines.append(line)
    if not funded:
        lines.append(paint(f"    top up: {info.get('topup_url') or DEEPSEEK_TOPUP_URL}", '2'))
    if info.get('label_source') == 'key':
        lines.append(paint('    set DEEPSEEK_ACCOUNT_LABEL (or "label" in auth.json) to name this account', '2'))
    return lines, False


def grok_identity(info):
    account = info.get('account') or {}
    plan = f" ({account['plan']})" if account.get('plan') else ''
    return f"{account.get('email') or '?'}{plan}"


def grok_build_lines(info, now):
    windows = info.get('windows') or []
    known = [w for w in windows if numeric(w.get('used_percent')) is not None]
    if not known:
        verdict = paint('UNKNOWN', '33;1')
    elif any(w['used_percent'] >= 100 for w in known):
        verdict = paint('EXHAUSTED', '31;1')
    else:
        verdict = paint('READY', '32;1')
    lines = [f"  {paint(grok_identity(info), '1')}  {verdict}"]
    lines += [window_line(window, now) for window in windows]
    lines.append(paint('    unofficial endpoint (cli-chat-proxy.grok.com); treat quota as indicative only', '2'))
    return lines, False


RENDERERS = {'anthropic': anthropic_lines, 'openai-codex': codex_lines, 'deepseek': deepseek_lines,
             'grok-build': grok_build_lines}


def waybar_payload(report):
    """Return compact Waybar JSON from an already collected report.

    This is presentation only: it never calls an adapter and unknown capacity
    stays ``?`` rather than being represented as zero.
    """
    remaining = []
    stale = False
    failed = []
    details = []
    for provider, info in report.get('providers', {}).items():
        if info.get('status') != 'ok':
            failed.append(provider)
            details.append(f"{provider}: {info.get('reason') or 'unavailable'}")
            continue
        normalized = info.get('normalized') or {}
        state = (normalized.get('freshness') or {}).get('state', 'unknown')
        stale |= state == 'stale'
        unknowns = normalized.get('unknowns') or []
        suffix = f" unknown={','.join(unknowns)}" if unknowns else ''
        details.append(f"{provider}: {state}{suffix}")
        for window in ((normalized.get('quota') or {}).get('windows') or []):
            value = window.get('remaining_percent')
            if numeric(value) is not None and window.get('state') == 'known':
                remaining.append(max(0, min(100, float(value))))
    if remaining:
        percent = min(remaining)
        text_value = f"LLM {percent:.0f}%" + (' ~' if stale else '') + ('!' if failed else '')
        css_class = 'critical' if percent < 20 else 'warning' if percent < 60 or stale or failed else 'normal'
        payload = {'text': text_value, 'percentage': round(percent)}
    else:
        payload = {'text': 'LLM ?' + ('!' if failed else ''), 'percentage': 0}
        css_class = 'error' if failed else 'warning'
    payload.update({'class': css_class, 'tooltip': 'LLM usage\n' + '\n'.join(details)})
    return payload


def render(report):
    now = time.time()
    checked = max(info['checked_at'] for info in report['providers'].values())
    age = max(0, int(time.time() - checked))
    age_label = f'{age // 60}m' if age >= 60 else f'{age}s'
    lines = [f"LLM usage left   (checked {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(checked))}, {age_label} ago)"]
    stale_seen = False
    for provider, info in report['providers'].items():
        lines.append('')
        if info['status'] != 'ok':
            who = codex_identity(info) if info.get('account') else info.get('label')
            lines.append(f"{paint(provider, '1')}  " + (f"{paint(who, '1')}  " if who else '') + paint(info['reason'], '31'))
            continue
        normalized = info.get('normalized') or {}
        freshness = (normalized.get('freshness') or {}).get('state', 'unknown')
        confidence = normalized.get('confidence', 'unknown')
        unknowns = normalized.get('unknowns') or []
        meta = f'  freshness={freshness} confidence={confidence}'
        if unknowns:
            meta += ' unknown=' + ','.join(unknowns)
        lines.append(paint(provider, '1') + meta)
        body, stale = RENDERERS.get(provider, anthropic_lines)(info, now)
        lines += body
        stale_seen |= stale
    if stale_seen:
        lines += ['', paint('~ from response headers of the last request; may be stale', '2')]
    return '\n'.join(lines)


def weekly_report(auth):
    """Compute conservative rolling-seven-day routing metrics from local telemetry."""
    data = get_json(local_url() + '/_usage')
    anthropic_data = (data.get('providers') or {}).get('anthropic') or {}
    tokens = data.get('tokens') or anthropic_data.get('tokens') or []
    now = time.time(); cutoff = now - 7 * 86400
    state_path = Path(data.get('usage_state_file') or (Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'cc-proxy'/'usage.json'))
    try: state = json.loads(state_path.read_text())
    except (OSError, ValueError): state = {}
    routing_path = Path(data.get('routing_log') or state_path.parent/'routing.log')
    events = []
    try:
        events = [json.loads(line) for line in routing_path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError): pass
    def ts(row):
        try: return datetime.datetime.fromisoformat(str(row.get('ts','')).replace('Z','+00:00')).timestamp()
        except ValueError: return 0
    events = [e for e in events if cutoff <= ts(e) <= now]
    recent = (data.get('routing') or {}).get('recent') or []
    unique_events={json.dumps(e,sort_keys=True):e for e in events + recent}
    starved = int((data.get('routing') or {}).get('starved', 0) or 0) + sum(e.get('kind') == 'starved' for e in unique_events.values())
    windows = {}
    def forecast_rows(provider, rows):
        for token in rows:
            for name, fc in (token.get('forecast') or {}).items():
                if (name in ('7d','7d_oi','primary_window') and isinstance(fc,dict)):
                    projected=fc.get('projected_at_reset')
                    if isinstance(projected,(int,float)):
                        windows[f'{provider}:{name}']=round(max(0,(1-float(projected))*100),1)
                    elif fc.get('forecast') == 'waste':
                        windows[f'{provider}:{name}']=None
    forecast_rows('anthropic', tokens)
    codex=(data.get('providers') or {}).get('openai-codex',{})
    forecast_rows('codex',[{'forecast':codex.get('forecast',{})}])
    samples=state.get('_samples') if isinstance(state.get('_samples'),dict) else {}
    avoidable=0
    for event in events:
        if event.get('reason') != 'cooldown': continue
        at=ts(event)
        exhausted={event.get('from_fp'),event.get('to_fp')}
        had_alternative=False
        for fp, buckets in samples.items():
            if fp in exhausted or not isinstance(buckets,dict): continue
            points=buckets.get('5h') or []
            prior=[point for point in points if isinstance(point,list) and len(point)>=2 and 0 <= at-float(point[0]) <= 600]
            if prior and float(prior[-1][1]) <= .7:
                had_alternative=True; break
        if had_alternative: avoidable += 1
    # P4 from the proxy's per-class counters: non-interactive classes only.
    opus=total=0
    for class_name,models in (((data.get('routing') or {}).get('class_usage') or {}).items()):
        if class_name=='interactive': continue
        for model,row in (models or {}).items():
            count=sum(float(row.get(key,0) or 0) for key in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens'))
            total += count
            if 'opus' in model.lower() or 'fable' in model.lower(): opus += count
    counters=[t.get('counters') or {} for t in tokens]
    if not counters: counters=[r for r in state.values() if isinstance(r,dict)]
    counts=[(int(r.get('input_tokens',0) or 0),int(r.get('cache_read_input_tokens',0) or 0),int(r.get('cache_creation_input_tokens',0) or 0)) for r in counters]
    i,c,cc=(sum(x[n] for x in counts) for n in range(3)); cache=round(100*c/(i+c+cc),1) if i+c+cc else None
    rendered_windows={key:(f"~{value:.1f}%" if isinstance(value,(int,float)) else 'n/a') for key,value in windows.items()}
    return {'period_days':7,'P1_starved_requests':starved,'P2_weekly_waste_percent':rendered_windows or 'n/a','P2_note':'~ denotes current forecast projection; reset-time historical forecasts are unavailable from this telemetry shape.','P3_avoidable_5h_stalls':avoidable,'P3_note':'Approximation: cooldown move events are matched to the latest prior 5h sample within 10 minutes; samples do not prove account eligibility.','P4_opus_fable_token_share_percent':round(100*opus/total,1) if total else 'n/a','cache_hit_percent':cache}


def capacity_report(data, horizon=2):
    """Conservative estimate from observed 5h slopes; unknown slopes have no proven capacity."""
    tokens = data.get('tokens') or []
    active = max(1, int((data.get('routing') or {}).get('active_sessions') or 0))
    burns = [v for t in tokens if t.get('valid', True)
             if (v := numeric(((t.get('forecast') or {}).get('5h') or {}).get('burn_per_hour'))) is not None and v > 0]
    per_session = statistics.median(burns) / active if burns else None
    accounts = {}
    for t in tokens:
        quota = (t.get('quota') or {}).get('five_hour') or {}
        used = numeric(quota.get('utilization'))
        if used is not None and used > 1:
            used /= 100
        else:
            used = numeric(t.get('u5'))
        reset = to_epoch(quota.get('resets_at') or quota.get('reset_at') or t.get('u5_reset'))
        headroom = max(0, 1 - used) if used is not None and (reset is None or reset > time.time()) else None
        count = (max(0, math.floor(headroom / (per_session * horizon)))
                 if headroom is not None and per_session and t.get('valid', True) else 0)
        accounts[t.get('fp', 'unknown')] = count
    return {'capacity': sum(accounts.values()), 'horizon': horizon, 'accounts': accounts,
            'per_session_burn': per_session, 'active_sessions': active if burns else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--waybar', action='store_true', help='Emit compact Waybar JSON')
    parser.add_argument('--week', action='store_true', help='Report rolling-seven-day routing metrics')
    parser.add_argument('--capacity', action='store_true', help='Estimate additional 5h heavy-session capacity')
    parser.add_argument('--news', action='store_true', help='Show cached official OpenAI and Anthropic news')
    parser.add_argument('--news-provider', choices=('openai', 'anthropic'))
    parser.add_argument('--since', help='With --news, only show items on/after YYYY-MM-DD')
    parser.add_argument('--horizon', type=float, default=2, help='Capacity planning horizon in hours (default: 2)')
    parser.add_argument('--refresh', action='store_true', help='Bypass the 60-second report cache (does not refresh OAuth)')
    parser.add_argument('--provider', choices=list(ADAPTERS))
    args = parser.parse_args()
    if args.news:
        import llm_news
        news_args = ['--json'] if args.json else []
        if args.refresh:
            news_args.append('--refresh')
        if args.news_provider:
            news_args += ['--provider', args.news_provider]
        if args.since:
            news_args += ['--since', args.since]
        return llm_news.main(news_args)
    agent = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent')).expanduser()
    auth_path = agent / 'auth.json'
    try:
        auth = json.loads(auth_path.read_text())
    except (OSError, ValueError):
        auth = {}
    if not isinstance(auth, dict):
        auth = {}
    if args.capacity:
        if args.horizon <= 0 or not math.isfinite(args.horizon):
            parser.error('--horizon must be a positive finite number')
        result = capacity_report(get_json(local_url() + '/_usage'), args.horizon)
        accounts = ', '.join(f'{fp} {count}' for fp, count in result['accounts'].items())
        print(json.dumps(result) if args.json else
              f"capacity: {result['capacity']} more heavy sessions are safe for the next {args.horizon:g}h (accounts: {accounts})")
        return
    if args.week:
        report = weekly_report(auth)
        print(json.dumps(report, indent=2) if args.json else '\n'.join(f'{key}: {value}' for key,value in report.items()))
        return
    providers = [args.provider] if args.provider else list(ADAPTERS)
    identity = str(auth_path.resolve()) + str(auth_path.stat().st_mtime_ns if auth_path.exists() else 0)
    identity += os.environ.get('PI_ANTHROPIC_PROXY_URL', '') + os.environ.get('CC_PROXY_PORT', '') + str(providers)
    cache_dir = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'llm-usage'
    report = None
    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(cache_dir, 0o700)
        path = cache_dir / (hashlib.sha256(identity.encode()).hexdigest()[:20] + '.json')
        with open(cache_dir / 'lock', 'a') as lock:
            os.chmod(cache_dir / 'lock', 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not args.refresh and path.exists() and 0 <= time.time() - path.stat().st_mtime < 60:
                report = json.loads(path.read_text())
                os.chmod(path, 0o600)
            if report is None:
                report = {'schema': REPORT_SCHEMA, 'generated_at': int(time.time()),
                          'host_local': True, 'providers': collect(auth, providers)}
                fd, temp = tempfile.mkstemp(dir=cache_dir)
                try:
                    with os.fdopen(fd, 'w') as out:
                        json.dump(report, out)
                    os.chmod(temp, 0o600)
                    os.replace(temp, path)
                finally:
                    if os.path.exists(temp):
                        os.unlink(temp)
    except (OSError, ValueError):
        if report is None:
            report = {'schema': REPORT_SCHEMA, 'generated_at': int(time.time()),
                      'host_local': True, 'providers': collect(auth, providers)}
    if args.waybar:
        print(json.dumps(waybar_payload(report), separators=(',', ':')))
    else:
        print(json.dumps(report, indent=2) if args.json else render(report))


if __name__ == '__main__':
    main()
