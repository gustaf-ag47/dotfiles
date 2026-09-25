// Run: node --test --experimental-strip-types tests/unit/test_llm_failover.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createFailover, isPoolExhausted, fetchRoute, noRouteLine, relativeTime, proxyOrigin,
  RECOVERY_POLL_MS,
} from '../../config/pi/extensions/llm-failover.ts';

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

function harness({ routes, setModelOk = () => true, start = 1_000_000 }) {
  const calls = { route: [], setModel: [], notify: [] };
  let clock = start;
  const core = createFailover({
    fetchRoute: async (model) => { calls.route.push(model); return routes.shift() ?? null; },
    setModel: async (target) => { calls.setModel.push(target); return setModelOk(target); },
    notify: (line, level) => calls.notify.push([level, line]),
    now: () => clock,
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
