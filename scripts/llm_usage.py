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


def jwt_claims(token):
    """Display-only identity from the access token: payload segment decoded locally, no signature check, no network."""
    parts = str(token).split('.')
    if len(parts) != 3:
        return {}
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, UnicodeDecodeError):  # binascii.Error is a ValueError
        return {}
    if not isinstance(payload, dict):
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
                windows.append({'name': name, 'used_percent': used,
                                'resets_at': bucket.get('resets_at') or bucket.get('reset_at') or token.get(reset),
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


ADAPTERS = {'anthropic': anthropic, 'openai-codex': codex, 'deepseek': deepseek}


def safe_query(provider, auth):
    try:
        result = ADAPTERS[provider](auth)
    except urllib.error.HTTPError as error:
        result = {'status': 'unavailable', 'reason': f'Usage endpoint HTTP {error.code}; inference may still work.'}
    except Exception as error:
        # No exception text/response bodies: either could carry credentials.
        result = {'status': 'unavailable', 'reason': f'Usage lookup failed ({type(error).__name__}).'}
    return provider, {**result, 'checked_at': int(time.time())}


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
    if used is None:
        return f'    {label:<9} {"?" * BAR_WIDTH}   ?% left'
    left = max(0.0, min(100.0, 100 - used))
    stale = window.get('source', '').startswith('header')
    if reset is not None and reset <= now and stale:
        return f'    {label:<9} {bar(100)} {paint("100% left", "32"):>9}   window reset since last reading'
    tail = f'resets in {until(reset, now)}'
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
    exhausted = [w for w in group.get('windows', []) if (w.get('used_percent') or 0) >= 100]
    if exhausted:
        return paint('EXHAUSTED', '31;1')
    return paint('READY', '32;1')


BUCKET_LABELS = {'base': 'opus/sonnet (7d)', 'oi': 'fable (7d fable)'}


def account_name(fp, labels):
    return labels.get(fp) or fp or '?'


def routing_lines(routing, labels):
    if not isinstance(routing, dict) or not routing.get('buckets'):
        return []
    width = max((len(account_name(r['fp'], labels)) for b in routing['buckets'].values() for r in b.get('ranking', [])), default=12)
    lines = ['', paint('routing', '1') + f"  mode={routing.get('mode')} threshold={routing.get('threshold')}"]
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
    lines += [window_line(window, now) for window in info.get('windows', [])]
    credits = info.get('credits') or {}
    balance = f" (balance {credits['balance']})" if credits.get('balance') is not None else ''
    for slug, row in (info.get('models') or {}).items():
        if row.get('available') is not False:
            continue
        when = to_epoch(row.get('available_at'))
        line = f'{slug} unavailable' + (f' until {until(when, now)}' if when is not None else '')
        if row.get('credits_would_enable'):
            line += f' \u2014 credits would unlock it{balance}'
        lines.append('    ' + paint(line, '31'))
    if blocked:
        tail = f"    top up: {info.get('topup_url') or CODEX_TOPUP_URL}"
        if info.get('reset_credits') is not None:
            tail += f"   reset credits: {info['reset_credits']:g}"
        lines.append(paint(tail, '2'))
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


RENDERERS = {'anthropic': anthropic_lines, 'openai-codex': codex_lines, 'deepseek': deepseek_lines}


def render(report):
    now = time.time()
    checked = max(info['checked_at'] for info in report['providers'].values())
    lines = [f"LLM usage left   (checked {time.strftime('%H:%M:%S', time.localtime(checked))})"]
    stale_seen = False
    for provider, info in report['providers'].items():
        lines.append('')
        if info['status'] != 'ok':
            who = codex_identity(info) if info.get('account') else info.get('label')
            lines.append(f"{paint(provider, '1')}  " + (f"{paint(who, '1')}  " if who else '') + paint(info['reason'], '31'))
            continue
        lines.append(paint(provider, '1'))
        body, stale = RENDERERS.get(provider, anthropic_lines)(info, now)
        lines += body
        stale_seen |= stale
    if stale_seen:
        lines += ['', paint('~ from response headers of the last request; may be stale', '2')]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='Bypass the 60-second report cache (does not refresh OAuth)')
    parser.add_argument('--provider', choices=list(ADAPTERS))
    args = parser.parse_args()
    agent = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent')).expanduser()
    auth_path = agent / 'auth.json'
    try:
        auth = json.loads(auth_path.read_text())
    except (OSError, ValueError):
        auth = {}
    if not isinstance(auth, dict):
        auth = {}
    providers = [args.provider] if args.provider else list(ADAPTERS)
    identity = str(auth_path.resolve()) + str(auth_path.stat().st_mtime_ns if auth_path.exists() else 0)
    identity += os.environ.get('PI_ANTHROPIC_PROXY_URL', '') + os.environ.get('CC_PROXY_PORT', '') + str(providers)
    cache_dir = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'llm-usage'
    report = None
    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = cache_dir / (hashlib.sha256(identity.encode()).hexdigest()[:20] + '.json')
        with open(cache_dir / 'lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not args.refresh and path.exists() and 0 <= time.time() - path.stat().st_mtime < 60:
                report = json.loads(path.read_text())
            if report is None:
                report = {'schema': 1, 'providers': collect(auth, providers)}
                fd, temp = tempfile.mkstemp(dir=cache_dir)
                try:
                    with os.fdopen(fd, 'w') as out:
                        json.dump(report, out)
                    os.replace(temp, path)
                finally:
                    if os.path.exists(temp):
                        os.unlink(temp)
    except (OSError, ValueError):
        if report is None:
            report = {'schema': 1, 'providers': collect(auth, providers)}
    print(json.dumps(report, indent=2) if args.json else render(report))


if __name__ == '__main__':
    main()
