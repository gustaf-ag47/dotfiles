import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, writeFile, rm, utimes } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { STAGES, STALE_MS, task, lines, restore, autoBind, laneTask, discover, age } from '../../config/pi/lib/work-progress.mjs';
import { setup } from '../../config/pi/extensions/work-progress.ts';

const now = Date.now();
const record = (extra = {}) => ({ id: 'test', title: 'Task', stage: 'building', source: 'parent',
  evidence: 'Test evidence', updatedAt: now, ...extra });

test('all explicit stages render without invented percentage or ETA', () => {
  for (const stage of STAGES) {
    const text = lines([record({ stage })], now).join('\n');
    assert.ok(text.includes(stage));
    assert.doesNotMatch(text, /\d+%|✓/);
  }
  assert.match(lines([record({ milestones: [{ label: 'test', done: true }, { label: 'CI', done: false }] })], now)[1], /\[#\.\] 1\/2 milestones/);
  assert.doesNotMatch(lines([record()], now)[1], /milestones/);
});

test('stale, future and malformed timestamps never display as current completion', () => {
  for (const updatedAt of [now - STALE_MS - 1, now + 1000, NaN]) {
    assert.match(lines([record({ stage: 'verified', updatedAt })], now)[1], /^stale \(independently verified\)/);
  }
  assert.match(lines([record({ stage: 'verified' })], now)[1], /^independently verified · 0m ago/);
  assert.deepEqual([59, 61, 120, 2879, 2880].map(m => age(m * 60000)), ['59m ago', '1h1m ago', '2h ago', '47h59m ago', '2d ago']);
  assert.equal(age(-1), 'age unknown');
  assert.notEqual(lines([record({ stage: 'reported-complete' })], now)[1], lines([record({ stage: 'verified' })], now)[1]);
});

test('manual evidence, waiting reason and finite milestone schema are mandatory', () => {
  assert.throws(() => task(record({ evidence: '' })));
  assert.throws(() => task(record({ stage: 'awaiting-operator' })));
  assert.throws(() => task(record({ milestones: [{ label: 'guess', done: 'yes' }] })));
  assert.throws(() => task(record({ updatedAt: NaN })));
  assert.throws(() => task(record({ id: '../lane' })));
  const safe = task(record({ title: 'a\x1b[31m\nb\u202ec' }));
  assert.doesNotMatch(safe.title, /[\x1b\n\u202e]/);
  assert.ok(lines(Array.from({ length: 20 }, (_, n) => record({ id: `${n}` })), now).length <= 7);
});

test('state belongs to exact session, restores reload, and fails closed on corrupt entries', () => {
  const entry = { type: 'custom', customType: 'work-progress', data: {
    session: 'one', tasks: [record()], bindings: ['lane'], hidden: true } };
  assert.equal(restore([entry], 'one').state.tasks.length, 1);
  assert.equal(restore([entry], 'two').state.tasks.length, 0);
  const bad = { ...entry, data: { ...entry.data, tasks: [{}] } };
  const restored = restore([entry, bad], 'one');
  assert.equal(restored.error, true);
  assert.deepEqual(restored.state.tasks, []);
});

test('auto-binding requires current pane and runtime lifetime, not session title', () => {
  const lane = { run_id: 'lane', parent_pane: '%1', created_at: new Date(now).toISOString() };
  assert.equal(autoBind(lane, '%1', now - 100, now), true);
  assert.equal(autoBind(lane, '%2', now - 100, now), false);
  assert.equal(autoBind(lane, '%1', now + 100, now + 200), false);
  assert.equal(autoBind(lane, '', now - 100, now), false);
  assert.equal(autoBind({ ...lane, created_at: 'invalid' }, '%1', now - 100, now), false);
});

test('lane statuses never imply independent verification, CI timestamps do not use poll time', async () => {
  const root = await mkdtemp(join(tmpdir(), 'work-progress-'));
  try {
    await mkdir(join(root, 'supervisor'));
    const lane = { run_id: 'lane', status: 'open', created_at: new Date(now).toISOString() };
    const put = async extra => writeFile(join(root, 'lane.json'), JSON.stringify({ ...lane, ...extra }));
    await put({});
    assert.equal((await laneTask(root, root, 'lane')).stage, 'unknown');
    for (const [result_status, expected] of [['DONE', 'reported-complete'], ['PASS', 'awaiting-review'], ['FAILED', 'error'], ['BLOCKER', 'error']]) {
      await put({ status: 'closed', result_status });
      assert.equal((await laneTask(root, root, 'lane')).stage, expected);
    }
    await put({ status: 'closed' });
    assert.equal((await laneTask(root, root, 'lane')).stage, 'unknown');
    for (const verdict of ['window-gone', 'never-started (prompt dropped - child has NO task)', 'watch-timeout-8h']) {
      await put({ status: 'closed', result_status: verdict });
      assert.equal((await laneTask(root, root, 'lane')).stage, 'error', verdict);
    }
    await put({});
    await writeFile(join(root, 'supervisor/lane.json'), JSON.stringify({ verdict: 'waiting-on-ci', record: 'pointer' }));
    await writeFile(join(root, 'lane-waiting-ci.md'), 'Never parse this pane transcript');
    const old = new Date(now - STALE_MS - 5000);
    await utimes(join(root, 'lane-waiting-ci.md'), old, old);
    const waiting = await laneTask(root, root, 'lane');
    assert.equal(waiting.stage, 'awaiting-ci');
    assert.match(lines([waiting], now)[1], /^stale/);
    await writeFile(join(root, 'lane.json'), 'broken');
    await assert.rejects(laneTask(root, root, 'lane'));
    await assert.rejects(laneTask(root, root, '../escape'));
    assert.deepEqual(await discover(join(root, 'missing')), []);
  } finally { await rm(root, { recursive: true, force: true }); }
});

// TypeBox and width utility injection avoids npm dependencies in CI; the real
// utility is smoke-tested separately with the installed Pi runtime.
const Type = new Proxy({}, { get: () => (...args) => args });

test('extension persists, guards no-UI, reloads, bounds width, and cleans shutdown', async () => {
  const root = await mkdtemp(join(tmpdir(), 'work-progress-ui-'));
  const old = process.env.PI_DELEGATE_REGISTRY;
  process.env.PI_DELEGATE_REGISTRY = root;
  const events = {}, tools = {}, commands = {}, entries = [], widgets = [];
  const pi = { on: (name, fn) => { events[name] = fn; }, registerTool: t => { tools[t.name] = t; },
    registerCommand: (name, cmd) => { commands[name] = cmd; },
    appendEntry: (customType, data) => entries.push({ type: 'custom', customType, data }) };
  const ctx = { mode: 'tui', hasUI: true,
    sessionManager: { getBranch: () => entries, getSessionId: () => 'one' },
    ui: { setWidget: (_key, value) => widgets.push(value), notify: () => {} } };
  try {
    setup(pi, Type, (s, w) => s.slice(0, w));
    assert.equal(widgets.length, 0);
    events.session_start({}, ctx);
    await tools.work_progress.execute('x', { action: 'update', ...record({ stage: 'awaiting-operator', reason: 'Approve apply' }) });
    const render = () => widgets.at(-1)().render(80).join('\n');
    assert.match(render(), /awaiting-operator/);
    assert.ok(widgets.at(-1)().render(4).every(s => s.length <= 4));
    await commands['work-progress'].handler('hide', ctx);
    assert.equal(widgets.at(-1), undefined);
    events.session_shutdown(); events.session_shutdown();
    events.session_start({}, ctx);
    await tools.work_progress.execute('x', { action: 'list' });
    assert.equal(widgets.at(-1), undefined);
    await commands['work-progress'].handler('show', ctx);
    assert.match(render(), /awaiting-operator/);
    events.session_shutdown();
    const count = widgets.length;
    events.session_start({}, { ...ctx, mode: 'print', hasUI: false });
    await tools.work_progress.execute('x', { action: 'list' });
    await tools.work_progress.execute('x', { action: 'update', ...record({ stage: 'verified', evidence: 'Parent ran tests and checked exact SHA CI' }) });
    assert.equal(widgets.length, count);
    events.session_shutdown();
    events.session_start({}, { ...ctx, sessionManager: { getBranch: () => entries, getSessionId: () => 'two' } });
    // Wait on the scan itself, not a tick count: hosted runners are slower than laptops.
    await tools.work_progress.execute('x', { action: 'list' });
    assert.doesNotMatch(render(), /awaiting-operator|verified/);
    // An in-flight scan must not draw after shutdown (real time, not ticks, so it finishes).
    events.session_start({}, ctx); events.session_shutdown();
    const closedCount = widgets.length;
    await new Promise(resolve => setTimeout(resolve, 500));
    assert.equal(widgets.length, closedCount);
  } finally {
    events.session_shutdown?.();
    if (old === undefined) delete process.env.PI_DELEGATE_REGISTRY; else process.env.PI_DELEGATE_REGISTRY = old;
    await rm(root, { recursive: true, force: true });
  }
});

test('timer reads attached lanes, dismissal survives reload, and foreign panes cannot attach', async t => {
  const root = await mkdtemp(join(tmpdir(), 'work-progress-lanes-'));
  const previous = { registry: process.env.PI_DELEGATE_REGISTRY, pane: process.env.TMUX_PANE };
  process.env.PI_DELEGATE_REGISTRY = root;
  process.env.TMUX_PANE = '%123';
  let interval, cleared = 0, widget;
  t.mock.method(globalThis, 'setInterval', fn => { interval = fn; return { unref() {} }; });
  t.mock.method(globalThis, 'clearInterval', () => { cleared++; });
  const events = {}, commands = {}, entries = [];
  let tool;
  const pi = { on: (name, fn) => { events[name] = fn; }, registerTool: value => { tool = value; },
    registerCommand: (name, value) => { commands[name] = value; },
    appendEntry: (customType, data) => entries.push({ type: 'custom', customType, data }) };
  const ctx = { mode: 'tui', hasUI: true,
    sessionManager: { getBranch: () => entries, getSessionId: () => 'one' },
    ui: { setWidget: (_key, value) => { widget = value; }, notify() {} } };
  const lane = { run_id: 'lane', parent_pane: '%123', status: 'open', created_at: new Date(now - 1000).toISOString() };
  const put = extra => writeFile(join(root, 'lane.json'), JSON.stringify({ ...lane, ...extra }));
  try {
    await put({});
    await writeFile(join(root, 'foreign.json'), JSON.stringify({ ...lane, run_id: 'foreign', parent_pane: '%999' }));
    setup(pi, Type, (s, w) => s.slice(0, w));
    events.session_start({}, ctx);
    await tool.execute('x', { action: 'list' });
    assert.match(widget().render(200).join('\n'), /no tracked tasks/);
    await assert.rejects(commands['work-progress'].handler('attach foreign', ctx), /not addressed/);
    await commands['work-progress'].handler('attach lane', ctx);
    assert.match(widget().render(200).join('\n'), /unknown/);
    await put({ result_status: 'DONE', status: 'closed', finished_at: new Date().toISOString() });
    interval(); interval(); // Coalesced local refresh, no network or tool call.
    await tool.execute('x', { action: 'list' });
    assert.match(widget().render(200).join('\n'), /reported-complete/);
    assert.doesNotMatch(widget().render(200).join('\n'), /independently verified/);
    await tool.execute('x', { action: 'update', ...record({ id: 'lane', stage: 'verified' }) });
    assert.match(widget().render(200).join('\n'), /verified/);
    await writeFile(join(root, 'lane.json'), 'broken');
    interval();
    await tool.execute('x', { action: 'list' });
    assert.match(widget().render(200).join('\n'), /error/);
    await tool.execute('x', { action: 'remove', id: 'lane' });
    events.session_start({}, ctx);
    await tool.execute('x', { action: 'list' });
    assert.match(widget().render(200).join('\n'), /no tracked tasks/);
    assert.ok(entries.at(-1).data.dismissed.includes('lane'));
    assert.ok(cleared >= 1);
    events.session_shutdown();
    assert.equal(widget, undefined);
  } finally {
    events.session_shutdown?.();
    for (const [key, value] of [['PI_DELEGATE_REGISTRY', previous.registry], ['TMUX_PANE', previous.pane]]) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    await rm(root, { recursive: true, force: true });
  }
});

test('registry failures and binding limits are surfaced without hiding tracked tasks', async t => {
  const root = await mkdtemp(join(tmpdir(), 'work-progress-limits-'));
  const previous = { registry: process.env.PI_DELEGATE_REGISTRY, pane: process.env.TMUX_PANE };
  process.env.TMUX_PANE = '%7';
  t.mock.method(globalThis, 'setInterval', () => ({ unref() {} }));
  t.mock.method(globalThis, 'clearInterval', () => {});
  const events = {}, entries = [];
  let tool, widget;
  const pi = { on: (name, fn) => { events[name] = fn; }, registerTool: value => { tool = value; },
    registerCommand() {}, appendEntry: (customType, data) => entries.push({ type: 'custom', customType, data }) };
  const ctx = { mode: 'tui', hasUI: true, sessionManager: { getBranch: () => entries, getSessionId: () => 'limits' },
    ui: { setWidget: (_key, value) => { widget = value; }, notify() {} } };
  const view = () => widget().render(300).join('\n');
  try {
    // Registry path is a file: discovery fails (ENOTDIR), the manual task must stay visible.
    const registry = join(root, 'lanes');
    process.env.PI_DELEGATE_REGISTRY = registry; // read once by setup()
    await writeFile(registry, 'not a directory');
    setup(pi, Type, (s, w) => s.slice(0, w));
    events.session_start({}, ctx);
    const result = JSON.parse((await tool.execute('x', { action: 'update',
      ...record({ id: 'manual', stage: 'awaiting-operator', reason: 'Approve apply' }) })).content[0].text);
    assert.equal(result.tasks.length, 1);
    assert.match(result.metadataErrors.join(), /registry unreadable/);
    assert.match(view(), /Work: error — lane registry unreadable/);
    assert.match(view(), /awaiting-operator/);
    assert.doesNotMatch(view(), /no tracked tasks/);
    events.session_shutdown();

    // More than 2000 registry entries (it is never pruned) must not fail the scan,
    // and new lanes beyond the binding limit are reported, not silently dropped.
    await rm(registry);
    await mkdir(registry);
    await Promise.all(Array.from({ length: 2001 }, (_, n) => writeFile(join(registry, `old-${n}.json`), '{}')));
    const created = new Date(Date.now() + 1000).toISOString();
    await Promise.all(Array.from({ length: 51 }, (_, n) => writeFile(join(registry, `z${n}.json`),
      JSON.stringify({ run_id: `z${n}`, parent_pane: '%7', status: 'open', created_at: created }))));
    await writeFile(join(registry, 'foreign.json'), JSON.stringify({ run_id: 'foreign', parent_pane: '%8', created_at: created }));
    events.session_start({}, ctx);
    await new Promise(resolve => setTimeout(resolve, 1100)); // let created_at fall inside the runtime window
    let listed;
    for (let n = 0; n < 30; n++) { // scan budget works through the backlog over ticks
      listed = JSON.parse((await tool.execute('x', { action: 'list' })).content[0].text);
      if (listed.metadataErrors.some(e => /lane limit/.test(e))) break;
    }
    assert.equal(entries.at(-1).data.bindings.length, 50);
    assert.ok(!entries.at(-1).data.bindings.includes('foreign'));
    assert.match(view(), /lane limit \(50\) reached/);
    assert.match(view(), /awaiting-operator/);
    await tool.execute('x', { action: 'remove', id: 'z0' });
    listed = JSON.parse((await tool.execute('x', { action: 'list' })).content[0].text);
    assert.ok(entries.at(-1).data.bindings.includes('z50'));
    assert.ok(!entries.at(-1).data.bindings.includes('z0'));
    assert.doesNotMatch(listed.metadataErrors.join(), /lane limit/);
    // Manual-only IDs never consume dismissal slots; lane IDs do, oldest dropped first.
    for (let n = 0; n < 3; n++) {
      await tool.execute('x', { action: 'update', ...record({ id: `m${n}` }) });
      await tool.execute('x', { action: 'remove', id: `m${n}` });
    }
    await tool.execute('x', { action: 'remove', id: 'manual' });
    const dismissed = entries.at(-1).data.dismissed;
    assert.deepEqual(dismissed, ['z0']);
    // A session switch during remove's lane lookup must not persist the old branch.
    const before = entries.length;
    const pending = tool.execute('x', { action: 'remove', id: 'm-race' });
    events.session_tree({}, ctx);
    await assert.rejects(pending, /Session changed/);
    assert.ok(entries.slice(before).every(e => !e.data.dismissed.includes('m-race')));
    assert.equal(entries.length, before);
    assert.equal(JSON.parse((await tool.execute('x', { action: 'list' })).content[0].text).tasks.length, 50);
  } finally {
    events.session_shutdown?.();
    for (const [key, value] of [['PI_DELEGATE_REGISTRY', previous.registry], ['TMUX_PANE', previous.pane]]) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    await rm(root, { recursive: true, force: true });
  }
});
