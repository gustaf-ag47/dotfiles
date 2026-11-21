// No network, transcript reads, or completion inference from pane activity.
import { readFile, stat, readdir } from 'node:fs/promises';
import { join } from 'node:path';

export const STAGES = ['building', 'awaiting-ci', 'awaiting-review', 'awaiting-operator',
  'verifying', 'reported-complete', 'verified', 'unknown', 'error'];
export const STALE_MS = 30 * 60 * 1000;
export const clean = (value, size = 180) => typeof value === 'string'
  ? value.replace(/[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]/g, ' ').trim().slice(0, size) : '';
export const validId = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(value);

export function task(value) {
  if (!value || !validId(value.id) || !STAGES.includes(value.stage) ||
      !clean(value.title) || !clean(value.source) || !clean(value.evidence) ||
      !Number.isFinite(value.updatedAt)) throw new Error('Invalid work progress record');
  if (value.stage.startsWith('awaiting-') && !clean(value.reason)) throw new Error('Waiting reason required');
  const milestones = value.milestones;
  if (milestones !== undefined && (!Array.isArray(milestones) || milestones.length > 8 ||
      milestones.some(m => !m || !clean(m.label) || typeof m.done !== 'boolean'))) {
    throw new Error('Use at most eight explicit named milestones');
  }
  return { id: value.id, title: clean(value.title), stage: value.stage,
    reason: clean(value.reason), evidence: clean(value.evidence, 500), source: clean(value.source),
    updatedAt: value.updatedAt,
    ...(milestones ? { milestones: milestones.map(m => ({ label: clean(m.label, 60), done: m.done })) } : {}) };
}

export function restore(entries, session) {
  let state = { session, tasks: [], bindings: [], dismissed: [], hidden: false };
  let error = false;
  for (const entry of entries) {
    if (entry.type !== 'custom' || entry.customType !== 'work-progress') continue;
    const d = entry.data;
    if (!d || d.session !== session) continue; // Forks must not inherit other sessions' tasks.
    try {
      if (!Array.isArray(d.tasks) || d.tasks.length > 50 || !Array.isArray(d.bindings) ||
          d.bindings.length > 50 || !d.bindings.every(validId) || typeof d.hidden !== 'boolean' ||
          (d.dismissed !== undefined && (!Array.isArray(d.dismissed) || d.dismissed.length > 2000 || !d.dismissed.every(validId)))) throw new Error();
      state = { session, tasks: d.tasks.map(task), bindings: [...new Set(d.bindings)], dismissed: d.dismissed || [], hidden: d.hidden };
      error = false;
    } catch { state = { session, tasks: [], bindings: [], dismissed: [], hidden: false }; error = true; }
  }
  return { state, error };
}

export function autoBind(lane, pane, startedAt, now) {
  const created = Date.parse(lane?.created_at);
  return !!pane && lane?.parent_pane === pane && validId(lane.run_id) &&
    created >= startedAt && created <= now;
}

export async function readJson(file) {
  const info = await stat(file);
  if (!info.isFile() || info.size > 64 * 1024) throw new Error('Invalid metadata file');
  return { data: JSON.parse(await readFile(file, 'utf8')), at: info.mtimeMs };
}

export async function discover(directory) {
  try {
    // The registry is never pruned; callers bound per-scan reads instead of failing.
    return (await readdir(directory)).filter(n => n.endsWith('.json')).sort();
  } catch (e) { if (e.code === 'ENOENT') return []; throw e; }
}

export async function laneTask(directory, mailbox, id) {
  if (!validId(id)) throw new Error('Invalid run id');
  const { data: lane } = await readJson(join(directory, `${id}.json`));
  if (lane?.run_id !== id) throw new Error('Lane identity mismatch');
  let stage = 'unknown', reason = 'No explicit work stage recorded';
  let updatedAt = Date.parse(lane.finished_at || lane.created_at);
  let evidence = 'Lane open is not evidence of active building';
  if (lane.result_status === 'DONE') {
    stage = 'reported-complete'; reason = 'Parent verification required'; evidence = clean(lane.result) || 'Child reported DONE';
  } else if (lane.result_status === 'PASS') {
    stage = 'awaiting-review'; reason = 'PASS is not completion'; evidence = clean(lane.result) || 'Child reported PASS';
  } else if (['FAILED', 'BLOCKER'].includes(lane.result_status)) {
    stage = 'error'; reason = 'Child reported a blocker'; evidence = clean(lane.result) || lane.result_status;
  } else if (lane.status === 'closed' && /^(never-started|window-gone|watch-timeout)/.test(lane.result_status || '')) {
    stage = 'error'; reason = 'Lane ended without a result'; evidence = clean(lane.result_status);
  } else if (lane.status === 'closed') {
    reason = 'Closed without completion evidence'; evidence = clean(lane.result_status) || reason;
  } else {
    // Use the supervisor's structured metadata, never its captured pane output.
    try {
      const { data: s } = await readJson(join(mailbox, 'supervisor', `${id}.json`));
      if (s.verdict === 'waiting-on-ci' && typeof s.record === 'string') {
        // The original record mtime is the evidence age; supervisor polls must not freshen it.
        const name = `${id}-waiting-ci.md`;
        let info;
        try { info = await stat(join(mailbox, name)); }
        catch { info = await stat(join(mailbox, 'ack', name)); }
        stage = 'awaiting-ci'; reason = 'Supervisor reported CI watch; not a check verdict';
        evidence = reason; updatedAt = info.mtimeMs;
      }
    } catch (e) { if (e.code !== 'ENOENT') { stage = 'error'; reason = 'Unreadable supervisor metadata'; evidence = reason; } }
  }
  return { id, title: clean(lane.task || lane.window || id), stage, reason, evidence,
    source: 'delegate lane', updatedAt };
}

const LABELS = { verified: 'independently verified' };
export const label = stage => LABELS[stage] || stage;

export function age(ms) {
  if (!Number.isFinite(ms) || ms < 0) return 'age unknown';
  const m = Math.floor(ms / 60000);
  if (m < 60) return `${m}m ago`;
  if (m < 48 * 60) return `${Math.floor(m / 60)}h${m % 60 ? `${m % 60}m` : ''} ago`;
  return `${Math.floor(m / 1440)}d ago`;
}

export function lines(tasks, now = Date.now(), limit = 5) {
  if (!tasks.length) return ['Work: no tracked tasks · /work-progress attach <run-id>'];
  const rows = tasks.map(t => {
    const ms = now - t.updatedAt;
    const stale = !Number.isFinite(ms) || ms < 0 || ms > STALE_MS;
    const stage = stale ? `stale (${label(t.stage)})` : label(t.stage);
    const elapsed = age(ms);
    const bar = !stale && t.milestones?.length
      ? ` [${t.milestones.map(m => m.done ? '#' : '.').join('')}] ${t.milestones.filter(m => m.done).length}/${t.milestones.length} milestones` : '';
    return { priority: stale || t.stage !== 'verified' ? 0 : 1,
      text: `${stage} · ${elapsed} · ${clean(t.title, 70)}${bar}${t.reason ? ` — ${clean(t.reason)}` : ''} (${clean(t.source, 40)})` };
  }).sort((a, b) => a.priority - b.priority);
  return [`Work: ${tasks.length} tracked · evidence age, not ETA`, ...rows.slice(0, limit).map(r => r.text),
    ...(rows.length > limit ? [`+${rows.length - limit} more · /work-progress list`] : [])];
}
