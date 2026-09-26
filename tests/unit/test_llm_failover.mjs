// Run: node --test --experimental-strip-types tests/unit/test_llm_failover.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createFailover, isPoolExhausted, fetchRoute, noRouteLine, relativeTime, proxyOrigin,
  RECOVERY_POLL_MS, earliestCooldown, planWait, waitSettings, waitLine, clockText,
} from '../../config/pi/extensions/llm-failover.ts';
import llmFailover from '../../config/pi/extensions/llm-failover.ts';
import http from 'node:http';

const PROXY_ERROR = '503 {"type":"error","error":{"type":"overloaded_error","message":'
  + '"Claude subscription request unavailable: no OAuth account can serve claude-fable-5-1 right now.\\n'
  + 'Account status:\\n- alice: cooldown until 2026-09-30T06:00:00+00:00 for claude-fable-5-1; weekly 100%"}}';

const anthropic = (routable, extra = {}) => ({
  provider: 'anthropic', model: 'claude-fable-5-1', routable, reason: routable ? null : 'exhausted',
  reset_at: '2026-09-30T06:00:00+00:00', quota_left_percent: routable ? 12 : 0, ...extra,
});
const codex = (routable) => ({
  provider: 'openai-codex', model: 'gpt-6-astra', routable, reason: routable ? null : 'exhausted',
});
const deepseek = (routable) => ({
  provider: 'deepseek', model: 'deepseek-v4-pro', routable, reason: routable ? null : 'unavailable',
});
const answer = (candidates) => ({
  model: 'claude-fable-5-1', candidates, first_routable: candidates.find(c => c.routable) ?? null,
});

function harness({ routes, setModelOk = () => true, start = 1_000_000, wait }) {
  const calls = { route: [], setModel: [], notify: [], sleep: [] };
  let clock = start;
  const core = createFailover({
    fetchRoute: async (model) => { calls.route.push(model); return routes.shift() ?? null; },
    setModel: async (target) => { calls.setModel.push(target); return setModelOk(target); },
    notify: (line, level) => calls.notify.push([level, line]),
    now: () => clock,
    sleep: async (ms) => { calls.sleep.push(ms); clock += ms; },
    random: () => 0,
    wait: wait ?? { enabled: true, maxWaitMs: 6 * 3_600_000, pollMs: RECOVERY_POLL_MS },
  });
  return { core, calls, tick: (ms) => { clock += ms; } };
}

test('trigger matches only the proxy pool-exhausted error', () => {
  assert.equal(isPoolExhausted(PROXY_ERROR), true);
  assert.equal(isPoolExhausted('503 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'), false);
  assert.equal(isPoolExhausted('529 overloaded_error'), false);
  assert.equal(isPoolExhausted(undefined), false);
});

test('codex routable -> switch with one warning line', async () => {
  const { core, calls } = harness({ routes: [answer([anthropic(false), codex(true), deepseek(false)])] });
  const now = 1_000_000;
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), true);
  assert.deepEqual(calls.route, ['claude-fable-5-1']);
  assert.deepEqual(calls.setModel, [{ provider: 'openai-codex', model: 'gpt-6-astra' }]);
  assert.equal(calls.notify.length, 1);
  const [level, line] = calls.notify[0];
  assert.equal(level, 'warning');
  assert.equal(line, `↪ switched to openai-codex/gpt-6-astra: anthropic pool exhausted (next reset ${relativeTime('2026-09-30T06:00:00+00:00', now)})`);
  assert.deepEqual(core.state.original, { provider: 'anthropic', model: 'claude-fable-5-1' });
  assert.deepEqual(core.state.current, { provider: 'openai-codex', model: 'gpt-6-astra' });
  assert.ok(!line.includes('Account status'), 'never leaks the proxy error payload');
});

test('setModel refusal falls through to the next routable candidate', async () => {
  const { core, calls } = harness({
    routes: [answer([anthropic(false), codex(true), deepseek(true)])],
    setModelOk: (t) => t.provider === 'deepseek',
  });
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), true);
  assert.deepEqual(calls.setModel.map(t => t.provider), ['openai-codex', 'deepseek']);
  assert.equal(calls.notify.length, 1);
  assert.match(calls.notify[0][1], /^↪ switched to deepseek\/deepseek-v4-pro/);
});

test('none routable -> single error line, no model change, no repeat', async () => {
  const cands = [anthropic(false), codex(false), deepseek(false)];
  const { core, calls, tick } = harness({ routes: [answer(cands), answer(cands), answer(cands)] });
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), false);
  tick(2_000); // pi's auto-retry produces the same error again
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), false);
  assert.deepEqual(calls.setModel, []);
  assert.deepEqual(calls.notify, [['error', '✗ no provider routable — anthropic exhausted, codex exhausted, deepseek unavailable']]);
  assert.equal(core.state.original, null);
  assert.equal(noRouteLine([]), '✗ no provider routable — oracle unreachable');
});

test('recovery on two polls >= 60 s apart -> switch back', async () => {
  const { core, calls, tick } = harness({
    routes: [answer([anthropic(false), codex(true), deepseek(false)]),
      answer([anthropic(true), codex(true), deepseek(false)]),
      answer([anthropic(true), codex(true), deepseek(false)])],
  });
  await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' });
  assert.equal(await core.onTurnStart(), false, 'no poll inside the 60 s window right after switching');
  tick(RECOVERY_POLL_MS);
  assert.equal(await core.onTurnStart(), false, 'first routable poll only arms');
  tick(10_000);
  assert.equal(await core.onTurnStart(), false, 'cached: no second fetch within 60 s');
  tick(RECOVERY_POLL_MS);
  assert.equal(await core.onTurnStart(), true);
  assert.deepEqual(calls.route, ['claude-fable-5-1', 'claude-fable-5-1', 'claude-fable-5-1']);
  assert.deepEqual(calls.setModel.at(-1), { provider: 'anthropic', model: 'claude-fable-5-1' });
  assert.deepEqual(calls.notify.at(-1), ['info', '↩ back to anthropic/claude-fable-5-1: pool recovered']);
  assert.equal(core.state.original, null);
});

test('one routable poll only -> no switch back; a non-routable poll resets the streak', async () => {
  const { core, calls, tick } = harness({
    routes: [answer([anthropic(false), codex(true), deepseek(false)]),
      answer([anthropic(true), codex(true), deepseek(false)]),
      answer([anthropic(false), codex(true), deepseek(false)]),
      answer([anthropic(true), codex(true), deepseek(false)])],
  });
  await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' });
  tick(RECOVERY_POLL_MS);
  assert.equal(await core.onTurnStart(), false);
  tick(RECOVERY_POLL_MS);
  assert.equal(await core.onTurnStart(), false, 'pool flapped: streak reset');
  tick(RECOVERY_POLL_MS);
  assert.equal(await core.onTurnStart(), false, 'only one consecutive routable poll again');
  assert.equal(calls.setModel.length, 1, 'only the initial switch away');
  assert.deepEqual(core.state.original, { provider: 'anthropic', model: 'claude-fable-5-1' });
});

test('/failover off -> no switch; on re-enables', async () => {
  const routes = [answer([anthropic(false), codex(true), deepseek(false)]),
    answer([anthropic(false), codex(true), deepseek(false)])];
  const { core, calls } = harness({ routes });
  core.setEnabled(false);
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), false);
  assert.deepEqual(calls.route, []);
  assert.deepEqual(calls.setModel, []);
  assert.deepEqual(calls.notify, []);
  core.setEnabled(true);
  assert.equal(await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' }), true);
});

test('ignores non-anthropic failures and a manual model pick stops tracking', async () => {
  const { core, calls } = harness({ routes: [answer([anthropic(false), codex(true), deepseek(false)])] });
  assert.equal(await core.onPoolExhausted({ provider: 'openai-codex', model: 'gpt-6-astra' }), false);
  assert.deepEqual(calls.route, []);
  await core.onPoolExhausted({ provider: 'anthropic', model: 'claude-fable-5-1' });
  core.onManualModelSelect({ provider: 'deepseek', model: 'deepseek-flash' });
  assert.equal(core.state.original, null);
  assert.equal(await core.onTurnStart(), false);
});

test('fetchRoute: loopback GET with timeout, tolerant of bad answers', async () => {
  const seen = [];
  const ok = async (url, init) => {
    seen.push([url, init.signal instanceof AbortSignal]);
    return { ok: true, json: async () => answer([anthropic(true)]) };
  };
  const got = await fetchRoute('http://127.0.0.1:8788', 'claude-opus-5-5', ok);
  assert.deepEqual(seen, [['http://127.0.0.1:8788/_route?model=claude-opus-5-5', true]]);
  assert.equal(got.first_routable.provider, 'anthropic');
  assert.equal(await fetchRoute('http://127.0.0.1:8788', 'x', async () => ({ ok: false })), null);
  assert.equal(await fetchRoute('http://127.0.0.1:8788', 'x', async () => ({ ok: true, json: async () => ({}) })), null);
  assert.equal(await fetchRoute('http://127.0.0.1:8788', 'x', async () => { throw new Error('ECONNREFUSED'); }), null);
  const hang = (_url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  assert.equal(await fetchRoute('http://127.0.0.1:8788', 'x', hang, 10), null);
});

test('proxy origin follows PI_ANTHROPIC_PROXY_URL / CC_PROXY_PORT', () => {
  assert.equal(proxyOrigin({}), 'http://127.0.0.1:8788');
  assert.equal(proxyOrigin({ CC_PROXY_PORT: '8999' }), 'http://127.0.0.1:8999');
  assert.equal(proxyOrigin({ PI_ANTHROPIC_PROXY_URL: 'http://127.0.0.1:9999/' }), 'http://127.0.0.1:9999');
  assert.equal(relativeTime('2026-09-30T06:00:00+00:00', Date.parse('2026-09-30T02:48:00+00:00')), 'in 3h 12m');
  assert.equal(relativeTime('2026-09-30T06:00:00+00:00', Date.parse('2026-09-30T07:00:00+00:00')), 'now');
  assert.equal(relativeTime(null, 0), 'unknown');
});

// The 503 errorMessage exactly as pi recorded it on 2026-09-26 (JSON-escaped newlines, emails anonymised).
const LIVE_503 = '503 {"type":"error","error":{"type":"overloaded_error","message":"Claude subscription request unavailable: '
  + 'no OAuth account can serve claude-opus-5-5 right now.\\nAccount status:\\n'
  + '- ccb67338fbdb (ops@example.test): cooldown until 2026-09-26T01:59:59.216281+00:00 for claude-opus-5-5; weekly 100% (header); 5-hour 0% (header)\\n'
  + '  detailed quota unavailable: OAuth token does not meet scope requirement user:profile\\n'
  + '- 82a293204226 (gs@example.test): cooldown until 2026-09-26T00:39:59.161403+00:00 for claude-opus-5-5; weekly 78% (header); 5-hour 101% (header)\\n'
  + '- a5de118c98c0 (ant@example.test): cooldown until 2026-09-27T09:59:59.277656+00:00 for claude-opus-5-5; weekly 100% (header); 5-hour 0% (header)\\n'
  + 'Run `claude-usage` for the full account report and reset times."}}';
const AT_0026 = Date.parse('2026-09-26T00:26:29Z');
const RESET_GS = Date.parse('2026-09-26T00:39:59.161403+00:00');
const opus = (routable, extra = {}) => anthropic(routable, { model: 'claude-opus-5-5', reset_at: null, ...extra });

test('earliestCooldown: earliest future reset for the requested model only', () => {
  const got = earliestCooldown(LIVE_503, 'claude-opus-5-5', AT_0026);
  assert.deepEqual(got, { account: 'gs@example.test', at: '2026-09-26T00:39:59.161403+00:00', epoch: RESET_GS });
  assert.equal(earliestCooldown(LIVE_503, 'claude-fable-5-1', AT_0026), null, 'other model');
  assert.equal(earliestCooldown(LIVE_503, 'claude-opus-5-5', RESET_GS + 1).account, 'ops@example.test', 'past resets skipped');
  assert.equal(earliestCooldown(LIVE_503.replaceAll('\\n', '\n'), 'claude-opus-5-5', AT_0026).epoch, RESET_GS, 'raw newlines');
  assert.equal(earliestCooldown('503 Overloaded', 'claude-opus-5-5', AT_0026), null);
  assert.equal(earliestCooldown(PROXY_ERROR.replace('alice', 'deadbeef0001'), 'claude-fable-5-1', 0).account, 'deadbeef0001');
});

test('planWait: earliest of body and oracle, capped', () => {
  const base = { errorMessage: LIVE_503, model: 'claude-opus-5-5', now: AT_0026, waitingSince: 0, maxWaitMs: 6 * 3_600_000 };
  const plan = planWait({ ...base, route: answer([opus(false, { reset_at: '2026-09-26T01:00:00+00:00' })]) });
  assert.deepEqual(plan, { action: 'wait', until: RESET_GS, deadline: AT_0026 + 6 * 3_600_000, account: 'gs@example.test' });
  const earlierOracle = planWait({ ...base, route: answer([opus(false, { reset_at: '2026-09-26T00:30:00+00:00' })]) });
  assert.equal(earlierOracle.until, Date.parse('2026-09-26T00:30:00+00:00'));
  assert.equal(earlierOracle.account, null);
  const unknown = planWait({ ...base, errorMessage: PROXY_ERROR, route: null });
  assert.equal(unknown.action, 'wait');
  assert.equal(unknown.until, null);
  const capped = planWait({ ...base, maxWaitMs: 5 * 60_000, route: null });
  assert.equal(capped.action, 'stop');
  assert.match(capped.line, /next reset 00:39:59Z \(in 13m\) is past the 5m wait cap/);
  const spent = planWait({ ...base, waitingSince: AT_0026 - 7 * 3_600_000, route: null });
  assert.equal(spent.action, 'stop');
  assert.match(spent.line, /after 6h of waiting/);
});

test('waitSettings and the wait line', () => {
  assert.deepEqual(waitSettings({}), { enabled: true, maxWaitMs: 6 * 3_600_000, pollMs: 60_000 });
  assert.deepEqual(waitSettings({ PI_FAILOVER_WAIT: '0', PI_FAILOVER_MAX_WAIT_HOURS: '1.5', PI_FAILOVER_POLL_SECONDS: '2' }),
    { enabled: false, maxWaitMs: 5_400_000, pollMs: 2_000 });
  assert.deepEqual(waitSettings({ PI_FAILOVER_MAX_WAIT_HOURS: 'x', PI_FAILOVER_POLL_SECONDS: '-1' }).maxWaitMs, 6 * 3_600_000);
  const plan = { action: 'wait', until: RESET_GS, deadline: AT_0026 + 3_600_000, account: 'gs@example.test' };
  assert.equal(waitLine('claude-opus-5-5', plan, AT_0026), '⏳ anthropic pool exhausted for claude-opus-5-5; waiting until 00:39:59Z'
    + ' (in 13m) for gs@example.test to reset, then resuming (type a message or /failover off to stop)');
  assert.equal(clockText(Date.parse('2026-09-27T09:59:59Z'), AT_0026), '2026-09-27 09:59:59Z');
});

test('settled exhaustion waits for the reset, polling, then resumes', async () => {
  const { core, calls } = harness({ start: AT_0026, routes: [
    answer([opus(false), codex(false)]), answer([opus(false), codex(false)]), answer([opus(true), codex(false)])] });
  assert.equal(await core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, LIVE_503), true);
  const toReset = RESET_GS - AT_0026;
  assert.deepEqual(calls.sleep, [RECOVERY_POLL_MS, RECOVERY_POLL_MS], 'naps at most one poll interval');
  assert.ok(calls.sleep.reduce((a, b) => a + b, 0) < toReset, 'resumes as soon as the oracle says routable');
  assert.deepEqual(calls.setModel, []);
  assert.equal(calls.notify.length, 2);
  assert.match(calls.notify[0][1], /^⏳ .* waiting until 00:39:59Z \(in 13m\) for gs@example.test/);
  assert.deepEqual(calls.notify[1], ['info', '▶ anthropic pool recovered; resuming anthropic/claude-opus-5-5']);
});

test('settled exhaustion: last nap lands just after the reset (grace, no oracle chatter)', async () => {
  const close = LIVE_503.replace('2026-09-26T00:39:59.161403', '2026-09-26T00:26:49.000000');
  const { core, calls } = harness({ start: AT_0026, routes: [answer([opus(false)]), answer([opus(true)])] });
  assert.equal(await core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, close), true);
  assert.deepEqual(calls.sleep, [25_000], '20 s to reset + 5 s grace');
});

test('settled exhaustion switches when a substitute becomes routable while waiting', async () => {
  const { core, calls } = harness({ start: AT_0026, routes: [
    answer([opus(false), codex(false)]), answer([opus(false), codex(true)]), answer([opus(false), codex(true)])] });
  assert.equal(await core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, LIVE_503), true);
  assert.deepEqual(calls.setModel, [{ provider: 'openai-codex', model: 'gpt-6-astra' }]);
  assert.match(calls.notify.at(-1)[1], /^↪ switched to openai-codex/);
});

test('settled exhaustion: cap, opt-out, cancel and non-anthropic never wait', async () => {
  const capped = harness({ start: AT_0026, routes: [answer([opus(false)])], wait: { enabled: true, maxWaitMs: 60_000, pollMs: RECOVERY_POLL_MS } });
  assert.equal(await capped.core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, LIVE_503), false);
  assert.deepEqual(capped.calls.sleep, []);
  assert.match(capped.calls.notify[0][1], /^✗ .* past the 1m wait cap — not waiting$/);

  const unknownReset = harness({ start: AT_0026, routes: Array.from({ length: 10 }, () => answer([opus(false)])),
    wait: { enabled: true, maxWaitMs: 150_000, pollMs: RECOVERY_POLL_MS } });
  assert.equal(await unknownReset.core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, PROXY_ERROR.replace('claude-fable-5-1', 'other')), false);
  assert.deepEqual(unknownReset.calls.sleep, [60_000, 60_000, 30_000]);
  assert.match(unknownReset.calls.notify.at(-1)[1], /giving up$/);
  assert.equal(unknownReset.core.state.waitingSince, 0);

  const off = harness({ start: AT_0026, routes: [], wait: { enabled: false, maxWaitMs: 1e9, pollMs: 1 } });
  assert.equal(await off.core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, LIVE_503), false);
  assert.deepEqual(off.calls.route, []);

  const cancel = harness({ start: AT_0026, routes: [answer([opus(false)]), answer([opus(false)])] });
  let polls = 0;
  assert.equal(await cancel.core.onSettledExhausted({ provider: 'anthropic', model: 'claude-opus-5-5' }, LIVE_503, () => ++polls > 1), false);
  assert.deepEqual(cancel.calls.notify.at(-1), ['info', '⏹ stopped waiting for the anthropic pool']);

  const codexFail = harness({ start: AT_0026, routes: [] });
  assert.equal(await codexFail.core.onSettledExhausted({ provider: 'openai-codex', model: 'gpt-6-astra' }, LIVE_503), false);
});

test('wait budget spans repeated failures and resets after a successful turn', async () => {
  const { core, tick } = harness({ start: AT_0026, routes: [answer([opus(false)]), answer([opus(true)]), answer([opus(false)])],
    wait: { enabled: true, maxWaitMs: 3 * 60_000, pollMs: RECOVERY_POLL_MS } });
  const target = { provider: 'anthropic', model: 'claude-opus-5-5' };
  assert.equal(await core.onSettledExhausted(target, PROXY_ERROR), true);
  assert.equal(core.state.waitingSince, AT_0026);
  tick(3 * 60_000);
  assert.equal(await core.onSettledExhausted(target, PROXY_ERROR), false, 'budget spent across the resumed failure');
  core.onTurnSucceeded();
  assert.equal(core.state.waitingSince, 0);
});

test('extension: agent_before_settle waits on a fake proxy, then omits the failed entry and continues', async () => {
  let routeCalls = 0;
  const server = http.createServer((req, res) => {
    assert.match(req.url, /^\/_route\?model=claude-opus-5-5$/);
    routeCalls++;
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify(answer([opus(routeCalls >= 3), codex(false)])));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const saved = { ...process.env };
  process.env.PI_ANTHROPIC_PROXY_URL = `http://127.0.0.1:${server.address().port}`;
  process.env.PI_FAILOVER_POLL_SECONDS = '0.05';
  const handlers = {};
  const notes = [];
  try {
    llmFailover({ on: (name, fn) => { handlers[name] = fn; }, registerCommand: () => {}, setModel: async () => true });
    const failed = { role: 'assistant', stopReason: 'error', errorMessage: LIVE_503.replace(/2026-09-26T00:39:59\.161403/, new Date(Date.now() + 200).toISOString().slice(0, -1)) };
    const ctx = { hasUI: true, ui: { notify: (line, level) => notes.push([level, line]) }, model: { provider: 'anthropic', id: 'claude-opus-5-5' },
      hasPendingMessages: () => false, signal: undefined, modelRegistry: { find: () => undefined } };
    const event = (outcome, messages) => ({ type: 'agent_before_settle', outcome, entries: [], continue: false,
      context: { contextEntries: [{ sourceEntry: { id: 'u1' }, messages: [{ role: 'user' }] }, { sourceEntry: { id: 'a9' }, messages }] } });
    assert.equal(await handlers.agent_before_settle(event('completed', [failed]), ctx), undefined);
    assert.equal(await handlers.agent_before_settle(event('error', [{ ...failed, errorMessage: '503 Overloaded' }]), ctx), undefined);
    const started = Date.now();
    const result = await handlers.agent_before_settle(event('error', [failed]), ctx);
    assert.deepEqual(result, { entries: [{ type: 'context_edit', targetId: 'a9', replacement: null }], continue: true });
    assert.equal(routeCalls, 3, 'plan poll + two naps until routable');
    assert.ok(Date.now() - started < 5_000);
    assert.match(notes[0][1], /^⏳ anthropic pool exhausted for claude-opus-5-5; waiting until/);
    assert.deepEqual(notes.at(-1), ['info', '▶ anthropic pool recovered; resuming anthropic/claude-opus-5-5']);
  } finally {
    process.env = saved;
    server.close();
  }
});
