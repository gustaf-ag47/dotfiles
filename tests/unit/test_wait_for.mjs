// wait-for.ts: background waits for non-CI conditions + cache-aware keepalive.
// Contract under test: an already-true condition returns inline without ending
// the turn; otherwise the tool terminates with the `wait_for registered:` phrase,
// polls outside the model and wakes exactly once with `WAIT RESOLVED`; the
// keepalive fires only while waiting, idle, near cache expiry and while its
// cumulative cost stays under one cache miss; ci_wait watches count as waits.
// exec, file reads, pid checks and the clock are faked.
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { setup, cacheTtlMs, keepaliveDelayMs, keepaliveEconomics, keepaliveWorthIt } =
  await import('../../config/pi/extensions/wait-for.ts');

const MIN = 60_000;
// Opus 5.5 prices ($/Mtok) and 1h cache tier, as in models-store.json.
const OPUS = { cost: { input: 4, output: 20, cacheRead: 0.2, cacheWrite: 5 }, promptCache: { short: 300, long: 3600 } };

function boot({ files = {}, cmd = { code: 1, stdout: '', stderr: '' }, pane = null, alive = new Set(), entries = [], idle = true, tokens = 200_000, model = OPUS } = {}) {
  const sent = [], appended = [], events = [], handlers = {}, listeners = {};
  let tool, command;
  let t = 1_000_000;
  const execCalls = [];
  const pi = {
    on: (name, fn) => { handlers[name] = fn; },
    registerTool: (def) => { tool = def; },
    registerCommand: (name, def) => { command = def; },
    appendEntry: (customType, data) => { appended.push(data); entries.push({ type: 'custom', customType, data }); },
    sendMessage: (message, opts) => sent.push([message, opts]),
    events: { emit: (name, data) => events.push([name, data]), on: (name, fn) => { listeners[name] = fn; } },
  };
  const state = { files, cmd, pane, alive, idle, tokens };
  const exec = async (file, args, opts) => {
    execCalls.push([file, args, opts]);
    if (file === 'bash') return state.cmd;
    if (file === 'tmux') {
      if (!state.pane) return { code: 1, stdout: '', stderr: "can't find pane" };
      if (args[0] === 'display-message') return { code: 0, stdout: `${state.pane.dead ? 1 : 0} ${state.pane.status ?? ''}\n`, stderr: '' };
      return { code: 0, stdout: state.pane.text ?? '', stderr: '' };
    }
    throw new Error(`unexpected ${file}`);
  };
  const api = setup(pi, {
    exec, now: () => t, autoPoll: false,
    readTail: (p) => (p in state.files ? state.files[p] : null),
    pidAlive: (pid) => state.alive.has(pid),
  });
  const ctx = {
    cwd: '/w', hasUI: false, model,
    isIdle: () => state.idle,
    getContextUsage: () => ({ tokens: state.tokens, contextWindow: 1e6, percent: 20 }),
    sessionManager: { getBranch: () => entries },
  };
  return { api, tool, command, handlers, listeners, sent, appended, events, ctx, state, execCalls, advance: (ms) => { t += ms; }, entries };
}

async function start(b) { await b.handlers.session_start({}, b.ctx); }
const run = (b, params) => b.tool.execute('c1', params, undefined, undefined, b.ctx);

test('validates targets and patterns', async () => {
  const b = boot();
  await start(b);
  await assert.rejects(run(b, {}), /exactly one/);
  await assert.rejects(run(b, { command: 'true', pid: 5 }), /exactly one/);
  await assert.rejects(run(b, { file: '/log' }), /needs pattern/);
  await assert.rejects(run(b, { file: '/log', pattern: '(' }), /bad pattern/);
  await assert.rejects(run(b, { pid: 1 }), /process id/);
});

test('already-true condition returns inline and does not end the turn', async () => {
  const b = boot({ cmd: { code: 0, stdout: 'ready\n', stderr: '' } });
  await start(b);
  const res = await run(b, { command: 'curl -sf localhost:8080/health' });
  assert.notEqual(res.terminate, true);
  assert.match(res.content[0].text, /^wait_for: already met/);
  assert.match(res.content[0].text, /ready/);
  assert.equal(b.api.watches.size, 0);
  assert.equal(b.appended.length, 0);
  assert.equal(b.execCalls[0][2].cwd, '/w');
});

test('file wait registers, terminates, wakes once when the pattern appears', async () => {
  const b = boot({ files: { '/log': 'building...\n' } });
  await start(b);
  const res = await run(b, { file: '/log', pattern: '^EXIT=\\d+', note: 'then read the summary' });
  assert.equal(res.terminate, true);
  assert.match(res.content[0].text, /^wait_for registered: wf1 \/log =~ \/\^EXIT=\\d\+\//);
  assert.deepEqual(b.events.at(-1)[0], 'wait-for:state');
  assert.equal(b.events.at(-1)[1].active, true);
  b.advance(10_000); await b.api.tick();
  assert.equal(b.sent.length, 0, 'interval not elapsed: not even checked');
  b.advance(30_000); await b.api.tick();
  assert.equal(b.sent.length, 0);
  b.state.files['/log'] += 'ok 1\nEXIT=0\n';
  b.advance(30_000); await b.api.tick();
  assert.equal(b.sent.length, 1);
  const [msg, opts] = b.sent[0];
  assert.equal(msg.customType, 'wait-for');
  assert.deepEqual(opts, { triggerTurn: true });
  assert.match(msg.content, /^WAIT RESOLVED - wf1 .*: met after 1 min/);
  assert.match(msg.content, /note: then read the summary/);
  assert.match(msg.content, /EXIT=0/);
  assert.equal(b.appended.at(-1).op, 'resolved');
  assert.equal(b.events.at(-1)[1].active, false);
  b.advance(60_000); await b.api.tick();
  assert.equal(b.sent.length, 1, 'wakes exactly once');
});

test('fail_pattern resolves as failed', async () => {
  const b = boot({ files: { '/log': '' } });
  await start(b);
  await run(b, { file: '/log', pattern: 'PASS', fail_pattern: '^(FAIL|panic)' });
  b.state.files['/log'] = 'panic: boom\n';
  b.advance(31_000); await b.api.tick();
  assert.match(b.sent[0][0].content, /: failed after/);
});

test('pane: exit, pattern, and pane gone', async () => {
  let b = boot({ pane: { dead: false, text: 'running' } });
  await start(b);
  await run(b, { pane: '%12' });
  b.state.pane = { dead: true, status: 2, text: 'tests failed' };
  b.advance(31_000); await b.api.tick();
  assert.match(b.sent[0][0].content, /tmux pane %12 exits: met .*\n[\s\S]*pane exited with status 2/);

  b = boot({ pane: { dead: false, text: '' } });
  await start(b);
  await run(b, { pane: '%3', pattern: 'Listening on' });
  b.state.pane = null;
  b.advance(31_000); await b.api.tick();
  assert.match(b.sent[0][0].content, /: gone after/);
});

test('pid wait and timeout', async () => {
  const b = boot({ alive: new Set([4242]) });
  await start(b);
  await run(b, { pid: 4242, max_minutes: 5 });
  b.advance(31_000); await b.api.tick();
  assert.equal(b.sent.length, 0);
  b.advance(5 * MIN); await b.api.tick();
  assert.match(b.sent[0][0].content, /pid 4242 exits: timed out/);
});

test('busy agent gets a followUp; watches survive a restart', async () => {
  const entries = [];
  const b = boot({ files: { '/log': '' }, entries });
  await start(b);
  await run(b, { file: '/log', pattern: 'done' });
  const b2 = boot({ files: { '/log': 'done' }, entries, idle: false });
  await start(b2);
  assert.equal(b2.api.watches.size, 1);
  await b2.api.tick();
  assert.deepEqual(b2.sent[0][1], { triggerTurn: true, deliverAs: 'followUp' });
  const b3 = boot({ entries });
  await start(b3);
  assert.equal(b3.api.watches.size, 0, 'resolved entry clears it');
});

test('cache economics helpers', () => {
  assert.equal(cacheTtlMs(OPUS, { PI_CACHE_RETENTION: 'long' }), 3600_000);
  assert.equal(cacheTtlMs(OPUS, {}), 300_000);
  assert.equal(cacheTtlMs({}, {}), undefined);
  assert.equal(keepaliveDelayMs(3600_000), 3300_000); // 55 min: 5 min margin
  assert.equal(keepaliveDelayMs(300_000), 240_000); // 4 min: 60 s margin
  const long = keepaliveEconomics(OPUS, 200_000, { PI_CACHE_RETENTION: 'long' });
  assert.ok(Math.abs(long.keepalive - 0.046) < 1e-9); // 200k * 0.2 + 300 * 20
  assert.ok(Math.abs(long.miss - 1.56) < 1e-9); // 200k * 8 - read
  assert.equal(keepaliveWorthIt(0, long), true);
  assert.equal(keepaliveWorthIt(32, long), true);
  assert.equal(keepaliveWorthIt(33, long), false); // 34 keepalives (~31 h) would cost more than one miss
  assert.equal(keepaliveEconomics({}, 200_000), null);
  assert.equal(keepaliveEconomics(OPUS, null), null);
  assert.equal(keepaliveWorthIt(0, null), false);
});

test('keepalive: only while waiting, idle and just before the cache expires', async () => {
  const saved = process.env.PI_CACHE_RETENTION;
  process.env.PI_CACHE_RETENTION = 'long';
  try {
    const b = boot({ files: { '/log': '' } });
    await start(b);
    assert.equal(b.api.keepaliveTick(), 'no pending wait');
    await b.handlers.turn_start({});
    await run(b, { file: '/log', pattern: 'done' });
    b.advance(54 * MIN);
    assert.match(b.api.keepaliveTick(), /^next at/);
    b.advance(1 * MIN);
    b.state.idle = false;
    assert.equal(b.api.keepaliveTick(), 'agent busy');
    b.state.idle = true;
    assert.equal(b.api.keepaliveTick(), 'sent');
    const [msg, opts] = b.sent.at(-1);
    assert.equal(msg.customType, 'wait-keepalive');
    assert.match(msg.content, /^WAIT KEEPALIVE - still waiting on: wf1/);
    assert.match(msg.content, /no tool calls/);
    assert.deepEqual(opts, { triggerTurn: true });
    assert.match(b.api.keepaliveTick(), /^next at/, 'no double send');
    // The keepalive turn's request refreshes the clock.
    b.advance(MIN); await b.handlers.turn_start({});
    b.advance(56 * MIN);
    assert.equal(b.api.keepaliveTick(), 'sent');
    assert.equal(b.api.state().keepalivesSent, 2);
    // Past expiry (e.g. laptop asleep) a keepalive no longer saves anything.
    b.advance(2 * 60 * MIN);
    assert.equal(b.api.keepaliveTick(), 'cache already expired');
  } finally {
    if (saved === undefined) delete process.env.PI_CACHE_RETENTION; else process.env.PI_CACHE_RETENTION = saved;
  }
});

test('keepalive counts ci_wait watches and stops when it would cost more than a miss', async () => {
  const saved = process.env.PI_CACHE_RETENTION;
  process.env.PI_CACHE_RETENTION = 'long';
  try {
    // Tiny context: a keepalive (output-dominated) costs more than the miss it avoids.
    const b = boot({ tokens: 500 });
    await start(b);
    b.listeners['ci-wait:state']({ active: true, watches: [{ id: 'w1', target: 'o/r#7', until: 'checks' }] });
    b.advance(56 * MIN);
    assert.match(b.api.keepaliveTick(), /^not worth it/);
    b.state.tokens = 200_000;
    assert.equal(b.api.keepaliveTick(), 'sent');
    assert.match(b.sent.at(-1)[0].content, /ci_wait o\/r#7/);
    b.listeners['ci-wait:state']({ active: false, watches: [] });
    assert.equal(b.api.state().keepalivesSent, 0, 'reset once nothing is pending');
    assert.equal(b.api.keepaliveTick(), 'no pending wait');
  } finally {
    if (saved === undefined) delete process.env.PI_CACHE_RETENTION; else process.env.PI_CACHE_RETENTION = saved;
  }
});
