#!/usr/bin/env python3
"""Read-only usage adapters. Never refresh OAuth, execute key commands, or log tokens."""
import argparse
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
    if not numeric(credential.get('expires')) or credential['expires'] <= time.time() * 1000:
        return {'status': 'unavailable', 'reason': 'OAuth expired; use Pi to refresh/login. This reader never refreshes tokens.'}
    headers = {'Authorization': 'Bearer ' + credential['access'], 'User-Agent': 'pi-llm-usage'}
    if credential.get('accountId'):
        headers['ChatGPT-Account-Id'] = credential['accountId']
    data = get_json('https://chatgpt.com/backend-api/wham/usage', headers)
    windows = []
    limits = data.get('rate_limit') or {}
    for name in ('primary_window', 'secondary_window'):
        window = limits.get(name)
        if isinstance(window, dict):
            windows.append({'name': name, 'used_percent': numeric(window.get('used_percent')),
                            'window_seconds': numeric(window.get('limit_window_seconds')),
                            'reset_at': numeric(window.get('reset_at'))})
    if not windows:
        return {'status': 'unavailable', 'reason': 'Subscription endpoint returned no recognized quota windows.'}
    return {'status': 'ok', 'kind': 'subscription quota', 'windows': windows,
            'allowed': limits.get('allowed'), 'limit_reached': limits.get('limit_reached'),
            'note': 'ChatGPT subscription only; read-only internal endpoint, not OpenAI API billing.'}


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


def deepseek(auth):
    key = deepseek_key(auth)
    if not key:
        return {'status': 'unavailable', 'reason': 'No supported DeepSeek API key configured (credential commands are not executed).'}
    data = get_json('https://api.deepseek.com/user/balance', {'Authorization': 'Bearer ' + key})
    balances = [{key: row.get(key) for key in ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')}
                for row in data.get('balance_infos', [])]
    if not balances:
        return {'status': 'unavailable', 'reason': 'Balance endpoint returned no recognized balances.'}
    return {'status': 'ok', 'kind': 'prepaid balance', 'available': data.get('is_available'),
            'balances': balances, 'note': 'Balance is not a subscription quota or a session cost estimate.'}


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


def window_line(window, now):
    used = window.get('used_percent')
    reset = to_epoch(window.get('resets_at') or window.get('reset_at'))
    duration = window.get('window_seconds')
    label = WINDOW_LABELS.get(window['name']) or (f'{duration / 3600:g}h' if duration else window['name'])
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


def render(report):
    now = time.time()
    checked = max(info['checked_at'] for info in report['providers'].values())
    lines = [f"LLM usage left   (checked {time.strftime('%H:%M:%S', time.localtime(checked))})"]
    stale_seen = False
    for provider, info in report['providers'].items():
        lines.append('')
        if info['status'] != 'ok':
            lines.append(f"{paint(provider, '1')}  {paint(info['reason'], '31')}")
            continue
        lines.append(paint(provider, '1'))
        labels = {g['account']: g.get('label') for g in info.get('accounts', []) if g.get('label')}
        for group in info.get('accounts', [info]):
            if 'account' in group:
                lines.append(f"  {paint(account_name(group['account'], labels), '1')}  {account_status(group, now)}")
                for model, reset in group.get('model_cooldowns', {}).items():
                    lines.append(f"    {paint(f'{model} cooldown {until(to_epoch(reset), now)}', '31')}")
            elif info.get('limit_reached') is True:
                lines.append('  ' + paint('LIMIT REACHED', '31;1'))
            for window in group.get('windows', []):
                stale_seen |= window.get('source', '').startswith('header')
                lines.append(window_line(window, now))
        lines += routing_lines(info.get('routing'), labels)
        for balance in info.get('balances', []):
            total = balance.get('total_balance')
            ok = numeric(float(total) if total is not None else None) is not None and float(total) > 0 and info.get('available') is not False
            lines.append(f"  balance {paint(f'{total} {balance.get("currency")}', '32;1' if ok else '31;1')}"
                         + ('' if ok else '   ' + paint('UNAVAILABLE', '31;1')))
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
