// Pure UI model and bounded, read-only transport. No credentials or model calls.
export const TABS = ['Overview', 'Accounts', 'Routing', 'Config', 'Events', 'Extensions', 'Fleet'];
export function safe(value, limit = 240) {
  return String(value ?? '?').replace(/sk-[\w.-]+|Bearer\s+\S+/g, '[redacted]')
    .replace(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g, '').slice(0, limit);
}
export function age(value, now = Date.now() / 1000) {
  if (typeof value !== 'number') return '?';
  const n = Math.max(0, Math.floor(now - value));
  return n < 60 ? `${n}s` : n < 3600 ? `${Math.floor(n / 60)}m` : `${Math.floor(n / 3600)}h`;
}
export function originFrom(env = process.env) {
  const u = new URL(env.PI_ANTHROPIC_PROXY_URL || `http://127.0.0.1:${env.CC_PROXY_PORT || '8788'}`);
  if (u.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname) || u.username || u.password || !['', '/'].includes(u.pathname) || u.search || u.hash) throw new Error('Inspector requires loopback HTTP origin');
  return u.origin;
}
export function poolEnabled(env = process.env) {
  return !['0', 'off', 'none', 'false', 'no'].includes((env.PI_ANTHROPIC_POOL || 'on').toLowerCase().trim());
}
export async function fetchSnapshot(origin, session = {}, fetchImpl = fetch, signal) {
  // Validate even when caller did not use originFrom(). Redirects cannot escape loopback.
  origin = originFrom({ PI_ANTHROPIC_PROXY_URL: origin });
  const query = new URLSearchParams({ model: session.model || 'claude-opus-5-5', class: session.taskClass || 'interactive', session: session.id || '', current: session.provider || '' });
  const timeout = AbortSignal.timeout(3000);
  const response = await fetchImpl(`${origin}/_inspect?${query}`, { redirect: 'error', signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
  if (!response.ok) throw new Error([404, 405].includes(response.status) ? 'Proxy inspector unsupported; update/restart proxy' : `Proxy HTTP ${response.status}`);
  // Bound streaming reads, not merely Content-Length (which may be absent).
  const reader = response.body.getReader();
  let size = 0; const chunks = [];
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.length;
      if (size > 1024 * 1024) { await reader.cancel(); throw new Error('Snapshot too large'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  const data = JSON.parse(new TextDecoder().decode(bytes));
  if (data?.schema !== 'llm-inspector.v1' || !Array.isArray(data.accounts) || !data.routing || typeof data.routing !== 'object') throw new Error('Invalid inspector snapshot');
  return data;
}
export function remaining(w, now = Date.now() / 1000) {
  const reset = typeof w.reset_at === 'number' ? w.reset_at : Date.parse(w.reset_at) / 1000;
  if (Number.isFinite(reset) && reset <= now) return '?';
  return typeof w.remaining_percent === 'number' ? `${w.source === 'header estimate' ? '~' : ''}${Math.max(0, Math.min(100, w.remaining_percent)).toFixed(0)}%` : '?';
}
export function registerInspectorStatus(pi, id, getState) {
  if (!pi.events) return () => {};
  let unsubscribe;
  const publish = () => { try { pi.events?.emit('llm:status', { id, state: getState(), at: Date.now() / 1000 }); } catch { /* UI observations must never break work */ } };
  pi.on('session_start', () => { unsubscribe?.(); unsubscribe = pi.events?.on('llm:status-request', publish); publish(); });
  pi.on('session_shutdown', () => { unsubscribe?.(); unsubscribe = undefined; });
  return publish;
}
export function statusLine(view) {
  const { snapshot: s, session = {}, error, extensions = {} } = view;
  const failover = extensions['llm-failover']?.state;
  const model = safe(session.model || 'no model', 45);
  const transport = session.provider === 'anthropic' && session.pool !== false ? 'proxy/local' : 'direct';
  const policy = failover ? `${failover.enabled ? 'auto' : 'switch off'}${failover.pinned ? ' · pressure pin' : ''}` : 'policy unknown';
  if (failover?.waitingSince) return `${model} · WAIT quota ${age(failover.waitingSince / 1000)} · ${policy} · /llm`;
  if (error && transport === 'proxy/local') return `${model} · proxy UNREACHABLE/UNSUPPORTED · last fetch ${age(view.fetchedAt)} ago · /llm`;
  if (transport === 'direct') {
    const p = !error && s?.providers?.[session.provider];
    const w = p?.windows?.[0];
    const reset = typeof w?.reset_at === 'number' ? w.reset_at : Date.parse(w?.resets_at || w?.reset_at) / 1000;
    const left = typeof w?.used_percent === 'number' && !(reset <= Date.now()/1000) ? `${Math.max(0, 100-w.used_percent).toFixed(0)}%` : '?';
    return `${model} · direct · quota ${left}${p ? ` (${age(p.checked_at)} ago)` : ''} · ${policy} · /llm`;
  }
  const last = s?.session?.last_served;
  const account = s?.accounts?.find(a => a.id === last?.account);
  const weekly = account?.windows?.find(w => w.name === (s?.routing?.bucket === 'oi' ? '7d fable' : '7d'));
  const attribution = last ? `${safe(last.label || last.account || last.provider, 28)} (${age(last.accepted_at)} ago)` : 'account unknown';
  const auth = (s?.accounts || []).filter(a => a.auth === 'rejected').length;
  const blocked = s?.routing?.account_applicable !== false && s?.routing?.account_preview && !s.routing.account_preview.would_pick;
  return `${model} · ${transport}${blocked ? ' · NONE ROUTABLE' : ''} · last: ${attribution}${weekly ? ` · week ${remaining(weekly)}` : ''}${auth ? ` · ${auth} AUTH!` : ''} · ${policy} · /llm`;
}
export function renderPanel(view, tab) {
  const s = view.snapshot;
  const session = view.session || {};
  const ext = view.extensions || {};
  const lines = [];
  if (view.error) lines.push(`UNREACHABLE / STALE: ${safe(view.error)} · last fetch ${age(view.fetchedAt)} ago`, '');
  if (tab === 'Extensions') {
    for (const [id, row] of Object.entries(ext)) {
      lines.push(`${safe(id)} · reported ${age(row.at)} ago`);
      for (const [k, v] of Object.entries(row.state || {})) lines.push(`  ${safe(k)}: ${safe(typeof v === 'object' ? JSON.stringify(v) : v)}`);
    }
    if (!Object.keys(ext).length) lines.push('No extension reports received. Reload participating extensions.');
    return [...lines, '', 'Runtime reports only; installed files do not prove a loaded extension.'];
  }
  if (tab === 'Fleet') {
    lines.push('Opt-in SSH fleet · shared accounts are NOT additional quota', '');
    if (view.fleetError) lines.push(`Fleet refresh failed: ${safe(view.fleetError)} (retaining previous observations)`);
    if (!view.fleet) return [...lines, 'Press f to load ~/.config/llm-proxy/fleet.json.', 'No remote connections occur until requested.'];
    const baseline = view.fleet.local?.snapshot?.config;
    for (const [name, row] of Object.entries(view.fleet)) {
      lines.push(`${safe(name)} · ${row.error || view.fleetError ? (row.error_kind === 'unsupported' ? 'UNSUPPORTED' : 'UNREACHABLE / STALE') : 'reachable'} · fetched ${age(row.fetched_at)} ago`);
      const snap = row.snapshot;
      if (row.error) lines.push(`  ${safe(row.error)}`);
      if (!snap) { lines.push('  No previous observation'); continue; }
      lines.push(`  host ${safe(snap.host)} · runtime ${safe(snap.runtime?.revision)}`);
      lines.push(`  ${row.error || view.fleetError ? 'Last known' : 'Current'} account preview: ${safe(snap.routing?.account_preview?.would_pick || 'none')}`);
      for (const [key, table] of Object.entries(snap.config?.tables || {})) {
        const differs = baseline && baseline.tables?.[key]?.loaded_revision !== table.loaded_revision;
        lines.push(`  ${safe(key)} ${safe(table.loaded_revision)}${differs ? ' · DIFFERS from local' : ''}${table.pending ? ' · PENDING/INVALID' : ''}`);
      }
      for (const setting of snap.config?.settings || []) {
        const local = baseline?.settings?.find(x => x.name === setting.name);
        if (local && local.value !== setting.value) lines.push(`  DIFFERS ${safe(setting.name)}: ${safe(setting.value)} (local ${safe(local.value)})`);
      }
      lines.push('');
    }
    return lines;
  }
  if (!s) return [...lines, 'No proxy snapshot. Check service or update proxy for /_inspect.'];
  const accounts = s.accounts || [];
  const label = id => accounts.find(a => a.id === id)?.label || id || 'none';
  const routing = s.routing || {};
  const preview = routing.account_preview || {};
  if (tab === 'Overview') {
    const failover = ext['llm-failover']?.state;
    const last = s.session?.last_served;
    lines.push(`SESSION · ${safe(session.provider)}/${safe(session.model)}`,
      `Transport: ${session.provider === 'anthropic' && session.pool !== false ? 'local proxy' : 'direct (pool telemetry below is separate)'}`,
      `Task class: ${safe(session.taskClass)} · source ${safe(session.classSource)}`,
      `Last proxy acceptance: ${last ? `${safe(last.label || last.account || last.provider)} · ${safe(last.model)} · ${age(last.accepted_at)} ago` : 'unknown; no request-linked evidence'}`,
      `Next account: ${routing.account_applicable === false ? 'not applicable to selected model' : safe(label(preview.would_pick))} · preview only`,
      `Failover: ${failover ? `${failover.enabled ? 'on' : 'off'} · pressure pin ${failover.pinned ? 'on' : 'off'}` : 'unknown; extension has not reported'}`,
      'Pin limits proactive switching, NOT exhaustion failover.', '',
      `POOL · ${accounts.length} accounts · snapshot ${age(s.generated_at)} ago`);
    for (const a of accounts) lines.push(`  ${safe(a.label)}: ${safe(a.state)} · auth ${safe(a.auth)}`);
    lines.push('', 'Quota observations may be older than the snapshot. No model probes.');
  } else if (tab === 'Accounts') {
    for (const a of accounts) {
      const selected = view.accountSelection === accounts.indexOf(a);
      lines.push(`${view.accountSelection != null ? (selected ? '› ' : '  ') : ''}${safe(a.label)} · ${safe(a.state)} · auth ${safe(a.auth)}`);
      if (view.accountSelection != null && view.expandedAccount !== a.id) continue;
      if (a.cooldown_until) lines.push(`  Retry after ${new Date(a.cooldown_until * 1000).toISOString()}`);
      for (const w of a.windows || []) lines.push(`  ${safe(w.name)}: ${remaining(w)} left · ${safe(w.source)} · observed ${age(w.observed_at)} ago · reset ${safe(w.reset_at)}`);
      if (a.quota_scope_denied) lines.push('  Quota API lacks profile scope; inference auth is independent.');
      lines.push('');
    }
    for (const [name, p] of Object.entries(s.providers || {})) {
      lines.push(`${safe(name)} · ${safe(p.status)} · observed ${age(p.checked_at)} ago`);
      for (const w of p.windows || []) lines.push(`  ${safe(w.name)}: ${safe(w.used_percent)}% used · reset ${safe(w.reset_at || w.resets_at)}`);
      if (p.reset_credits != null) lines.push(`  Reset credits: ${safe(p.reset_credits)}`);
      for (const b of p.balances || []) lines.push(`  Balance: ${safe(b.total_balance)} ${safe(b.currency)}`);
    }
  } else if (tab === 'Routing') {
    lines.push(`ACCOUNT PREVIEW · ${safe(s.session?.model)} · class ${safe(s.session?.class)}`,
      `Mode ${safe(routing.mode)} · bucket ${safe(routing.bucket)}`,
      `Affinity: ${safe(label(preview.last_pick))} · would pick ${safe(label(preview.would_pick))}`);
    for (const r of preview.ranking || []) lines.push(`  ${safe(label(r.fp))}: ${safe(r.reason || 'eligible')} · pressure ${safe(r.pressure)}`);
    for (const key of ['provider_preview', 'class_preview']) {
      lines.push('', `${key === 'provider_preview' ? 'MODEL EQUIVALENCE' : 'TASK CLASS'} ORACLE · not session permission to switch`);
      const oracle = routing[key];
      if (!oracle) lines.push('  No mapping for this model/class');
      for (const c of oracle?.candidates || []) lines.push(`  ${safe(c.provider)}/${safe(c.model)}: ${safe(c.reason || 'routable')}`);
      if (oracle?.preferred) lines.push(`  Preferred: ${safe(oracle.preferred.provider)}/${safe(oracle.preferred.model)}`);
    }
    lines.push('', 'Pi owns model switching; proxy owns Claude account selection.', 'Switching provider may change billing and where conversation data goes.');
  } else if (tab === 'Config') {
    lines.push(`Running proxy revision: ${safe(s.runtime?.revision)}`, `Started: ${safe(s.runtime?.started_at)}`);
    for (const item of s.config?.settings || []) lines.push(`${safe(item.name)}: ${safe(item.value)} · ${safe(item.source)} · ${safe(item.owner)}`);
    for (const [name, table] of Object.entries(s.config?.tables || {})) lines.push('', `${safe(name)}: ${table.pending ? 'PENDING/INVALID' : 'applied'}`, `  ${safe(table.path)}`, `  loaded ${safe(table.loaded_revision)} · disk ${safe(table.disk_revision)} · error ${safe(table.error || 'none')}`);
    for (const key of ['routes', 'classes']) {
      lines.push('', `${key} (effective)`);
      for (const [name, value] of Object.entries(s.config?.[key] || {})) {
        lines.push(`  ${safe(name)}:`);
        lines.push(...JSON.stringify(value, null, 2).split('\n').map(line => `    ${safe(line)}`));
      }
    }
    lines.push('', 'Read-only. Environment changes require a session/service restart.');
  } else if (tab === 'Events') {
    for (const e of [...(s.events || []), ...(s.route_events || []), ...(view.events || [])].slice(-100)) lines.push(Object.entries(e).map(([k,v]) => `${safe(k)}=${safe(v)}`).join(' · '));
    if (!lines.length) lines.push('No recorded transitions.');
    lines.push('', 'Bounded history, no prompts, credentials or raw upstream error bodies.');
  }
  return lines;
}
