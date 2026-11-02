"""Read-only proxy inspector and opt-in SSH fleet monitor (stdlib only)."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import subprocess
import sys
import termios
import time
import tty
import urllib.parse
import urllib.error
import urllib.request

SCHEMA = 'llm-inspector.v1'
TABS = ('overview', 'accounts', 'routing', 'config', 'events', 'extensions', 'fleet')
MAX_BYTES = 1024 * 1024


class UnsupportedInspector(ValueError):
    pass


def safe(value):
    text = re.sub(r'sk-[A-Za-z0-9_.-]+|Bearer\s+\S+', '[redacted]', str(value))
    return ''.join(c for c in text if c.isprintable())[:300]


def validate(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('schema') != SCHEMA:
        raise ValueError('Inspector unsupported; update/restart proxy')
    if not isinstance(snapshot.get('accounts'), list) or not isinstance(snapshot.get('routing'), dict):
        raise ValueError('Invalid inspector snapshot')
    return snapshot


def loopback_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
        raise ValueError('Inspector requires a loopback HTTP URL')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Inspector URL must be an origin')
    return url.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Inspector redirects refused')


def local_snapshot(origin, model, task_class, session=''):
    query = urllib.parse.urlencode({'model': model, 'class': task_class, 'session': session})
    url = loopback_url(origin) + '/_inspect?' + query
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(url, timeout=3) as response:
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 405):
            raise UnsupportedInspector('restart updated proxy') from None
        raise
    if len(raw) > MAX_BYTES:
        raise ValueError('Inspector response too large')
    return validate(json.loads(raw))


def remote_snapshot(host, model, task_class):
    target = host.get('target', '')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]{0,200}', target):
        raise ValueError('Invalid SSH target')
    port = host.get('port', 8788)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid proxy port')
    url = f'http://127.0.0.1:{port}/_inspect?' + urllib.parse.urlencode({'model': model, 'class': task_class})
    # No remote credential access, shell interpolation, forwarding, or model probe.
    script = ('import urllib.request,urllib.error,json,sys\n'
              'class NoRedirect(urllib.request.HTTPRedirectHandler):\n'
              ' def redirect_request(self,*a,**k): raise ValueError("redirect refused")\n'
              'o=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())\n'
              f'try: r=o.open({url!r},timeout=3).read({MAX_BYTES + 1})\n'
              'except urllib.error.HTTPError as e:\n'
              ' print(json.dumps({"inspector_error":"unsupported" if e.code in (404,405) else "http"}));sys.exit(0)\n'
              f'assert len(r)<={MAX_BYTES}\n'
              'sys.stdout.buffer.write(r)\n')
    alias = host.get('host_key_alias')
    if alias is not None and (not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', alias)):
        raise ValueError('Invalid SSH host key alias')
    options = ['-o', 'HostKeyAlias=' + alias] if alias else []
    result = subprocess.run(['ssh', *options, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                             '-o', 'ServerAliveInterval=3', '-o', 'ServerAliveCountMax=1',
                             '--', target, 'python3 -c ' + shlex.quote(script)],
                            capture_output=True, timeout=9)
    if result.returncode:
        raise ValueError('SSH or remote inspector unavailable')
    data = json.loads(result.stdout)
    if isinstance(data, dict) and data.get('inspector_error') == 'unsupported':
        raise UnsupportedInspector('restart updated remote proxy')
    return validate(data)


def fleet_hosts(path):
    data = json.loads(Path(path).expanduser().read_text())
    hosts = data.get('hosts') if isinstance(data, dict) else None
    if not isinstance(hosts, list) or len(hosts) > 8:
        raise ValueError('Fleet config requires hosts array (maximum 8)')
    seen = {'local'}
    for host in hosts:
        if not isinstance(host, dict) or not isinstance(host.get('name'), str) or host['name'] in seen:
            raise ValueError('Fleet names must be unique (local is reserved)')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,60}', host['name']):
            raise ValueError('Invalid fleet name')
        seen.add(host['name'])
    return hosts


class Monitor:
    def __init__(self, origin, model, task_class, hosts=()):
        self.origin, self.model, self.task_class = origin, model, task_class
        self.hosts = list(hosts)
        self.rows = {}

    def refresh(self):
        jobs = [('local', lambda: local_snapshot(self.origin, self.model, self.task_class))]
        jobs += [(h['name'], lambda h=h: remote_snapshot(h, self.model, self.task_class)) for h in self.hosts]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {pool.submit(fn): name for name, fn in jobs}
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                previous = self.rows.get(name, {})
                try:
                    self.rows[name] = {'snapshot': future.result(), 'fetched_at': time.time(), 'error': None}
                except Exception as exc:
                    self.rows[name] = {**previous,
                        'error': 'Inspector unsupported; restart updated proxy' if isinstance(exc, UnsupportedInspector) else safe(type(exc).__name__) + ': fetch failed',
                        'error_kind': 'unsupported' if isinstance(exc, UnsupportedInspector) else 'unreachable'}
        return self.rows


def age(value, now=None):
    now = time.time() if now is None else now
    if not isinstance(value, (float, int)):
        return '?'
    seconds = max(0, int(now - value))
    return f'{seconds}s' if seconds < 60 else f'{seconds // 60}m' if seconds < 3600 else f'{seconds // 3600}h'


def render_snapshot(snapshot, tab='overview'):
    s = snapshot
    lines = [f"LLM · {safe(s.get('host'))} · {tab} · snapshot {age(s.get('generated_at'))} ago", '']
    accounts = s.get('accounts', [])
    labels = {a['id']: a['label'] for a in accounts}
    route = s.get('routing', {})
    preview = route.get('account_preview') or {}
    if tab in ('overview', 'accounts'):
        lines += [f"Model: {safe(s.get('session', {}).get('model'))}",
                  f"Class: {safe(s.get('session', {}).get('class'))}",
                  'Next account: ' + safe(labels.get(preview.get('would_pick'), preview.get('would_pick') or 'none routable')),
                  'Pi failover/pin state: session-owned; inspect /llm in Pi', '']
        for account in accounts:
            lines.append(f"{safe(account['label'])}  {safe(account['state'])}  auth={safe(account['auth'])}")
            for window in account.get('windows', []):
                value = window.get('remaining_percent')
                percent = '?' if value is None else f'{value:.0f}%'
                prefix = '~' if value is not None and window.get('source') == 'header estimate' else ''
                lines.append(f"  {safe(window['name']):9} {prefix}{percent} left · observed {age(window.get('observed_at'))} ago · reset {safe(window.get('reset_at') or '?')}")
        for name, provider in s.get('providers', {}).items():
            lines.append(f"{safe(name)}  {safe(provider.get('status'))} · observed {age(provider.get('checked_at'))} ago")
    elif tab == 'routing':
        lines += [f"Mode: {safe(route.get('mode'))} · bucket: {safe(route.get('bucket'))}",
                  'Session affinity: ' + safe(preview.get('last_pick') or 'none'),
                  'Would pick: ' + safe(labels.get(preview.get('would_pick'), preview.get('would_pick') or 'none'))]
        for row in preview.get('ranking', []):
            lines.append(f"  {safe(labels.get(row['fp'], row['fp']))}: {safe(row.get('reason') or 'eligible')} · pressure {safe(row.get('pressure'))}")
        for key in ('provider_preview', 'class_preview'):
            lines.append('\n' + key.replace('_', ' ') + ' (not permission to switch):')
            for row in (route.get(key) or {}).get('candidates', []):
                lines.append(f"  {safe(row.get('provider'))}/{safe(row.get('model'))}: {safe(row.get('reason') or 'routable')}")
        lines.append(safe(route.get('note')))
    elif tab == 'config':
        lines.append(f"Running source: {safe(s.get('runtime', {}).get('revision'))}")
        for item in s.get('config', {}).get('settings', []):
            lines.append(f"{safe(item['name'])}: {safe(item['value'])} · source {safe(item['source'])}")
        for name, item in s.get('config', {}).get('tables', {}).items():
            lines += [f"{safe(name)}: loaded {safe(item.get('loaded_revision'))} · disk {safe(item.get('disk_revision'))}",
                      f"  {safe(item.get('path'))} · {'PENDING/INVALID' if item.get('pending') else 'applied'} · {safe(item.get('error') or 'valid')}"]
        for name in ('routes', 'classes'):
            lines.append(name + ' (effective):')
            for key, value in s.get('config', {}).get(name, {}).items():
                lines.append(f'  {safe(key)}: {safe(json.dumps(value))}')
    elif tab == 'events':
        for event in s.get('events', []) + s.get('route_events', []):
            lines.append(' · '.join(f'{safe(k)}={safe(v)}' for k, v in event.items()))
        if len(lines) == 2:
            lines.append('No recorded transitions in this proxy process.')
    elif tab == 'extensions':
        lines.append('Extensions are Pi-session-owned. Use /llm extensions inside Pi.')
    return lines


def render_monitor(rows, tab):
    if tab != 'fleet':
        local = rows.get('local', {})
        lines = render_snapshot(local['snapshot'], tab) if local.get('snapshot') else ['Local proxy unavailable or inspector unsupported.']
        if local.get('error'):
            lines.insert(0, 'STALE / UNREACHABLE · last successful fetch ' + age(local.get('fetched_at')) + ' ago')
        return lines
    lines = ['LLM FLEET · shared accounts are NOT additional quota', '']
    baseline = (rows.get('local', {}).get('snapshot') or {}).get('config')
    for name, row in rows.items():
        snap = row.get('snapshot') or {}
        lines.append(f"{safe(name)} · {('UNSUPPORTED' if row.get('error_kind') == 'unsupported' else 'UNREACHABLE / STALE') if row.get('error') else 'reachable'} · last fetch {age(row.get('fetched_at'))} ago")
        if row.get('error'):
            lines.append('  ' + safe(row['error']))
        if not snap:
            lines.append('  No previous observation'); continue
        lines.append(f"  host {safe(snap.get('host'))} · running {safe(snap.get('runtime', {}).get('revision'))}")
        lines.append('  ' + ('Last known' if row.get('error') else 'Current') + ' account preview: ' + safe(snap.get('routing', {}).get('account_preview', {}).get('would_pick') or 'none'))
        for table, config in snap.get('config', {}).get('tables', {}).items():
            base = (baseline or {}).get('tables', {}).get(table, {})
            differs = base.get('loaded_revision') != config.get('loaded_revision') if baseline else False
            lines.append(f"  {safe(table)}: {safe(config.get('loaded_revision'))}" + (' · DIFFERS from local' if differs else '') + (' · PENDING/INVALID' if config.get('pending') else ''))
        local_settings = {s['name']: s['value'] for s in (baseline or {}).get('settings', [])}
        for setting in snap.get('config', {}).get('settings', []):
            if setting['name'] in local_settings and local_settings[setting['name']] != setting['value']:
                lines.append(f"  DIFFERS {safe(setting['name'])}: {safe(setting['value'])} (local {safe(local_settings[setting['name']])})")
        lines.append('')
    return lines


def run(args, origin):
    hosts = fleet_hosts(args.fleet) if args.fleet else []
    monitor = Monitor(origin, args.model, args.task_class, hosts)
    tab = 'fleet' if args.fleet else args.inspect or 'overview'
    if args.json and args.watch:
        raise ValueError('--watch and --json cannot be combined')
    if not args.watch:
        rows = monitor.refresh()
        print(json.dumps(rows, indent=2) if args.json else '\n'.join(render_monitor(rows, tab)))
        return
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        raise ValueError('--watch requires a terminal; use --inspect --json for scripts')
    if not 2 <= args.interval <= 300:
        raise ValueError('--interval must be 2..300 seconds')
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    offset = 0
    try:
        tty.setcbreak(fd)
        print('\033[?1049h\033[?25l', end='', flush=True)
        due = 0
        while True:
            if time.monotonic() >= due:
                monitor.refresh()
                due = time.monotonic() + args.interval
            width, height = shutil.get_terminal_size((80, 24))
            lines = render_monitor(monitor.rows, tab)
            offset = max(0, min(offset, max(0, len(lines) - max(1, height-3))))
            # Strip controls from data; terminal controls are owned only here.
            import unicodedata
            def fit(line):
                result, columns = '', 0
                for c in safe(line):
                    size = 0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
                    if columns + size > width - 1: break
                    result += c; columns += size
                return result
            body = '\n'.join(fit(line) for line in lines[offset:offset+max(1, height-3)])
            hint = '1 overview 2 accounts 3 routing 4 config 5 events 6 extensions 7 fleet · j/k scroll r refresh q quit'
            print('\033[H\033[2J' + body + '\n\n' + fit(hint), end='', flush=True)
            ready, _, _ = select.select([fd], [], [], min(0.5, max(0, due-time.monotonic())))
            if ready:
                key = os.read(fd, 1).decode(errors='ignore')
                if not key or key in ('q', '\x1b'): break
                if key == 'r': due = 0
                if key == 'j': offset += 1
                if key == 'k': offset -= 1
                if key in '1234567': tab, offset = TABS[int(key)-1], 0
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        print('\033[?25h\033[?1049l', end='', flush=True)
