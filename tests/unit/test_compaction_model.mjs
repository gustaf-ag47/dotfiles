import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCompactionModel, pickSummaryModel, SUMMARY_RESERVE_TOKENS } from '../../config/pi/extensions/compaction-model.ts';

const models = {
  'anthropic/claude-opus-5-5': { provider: 'anthropic', id: 'claude-opus-5-5', cost: { input: 4 } },
  'anthropic/claude-sonnet-5-5': { provider: 'anthropic', id: 'claude-sonnet-5-5', cost: { input: 2 } },
  'anthropic/claude-sonnet-5': { provider: 'anthropic', id: 'claude-sonnet-5', cost: { input: 2 } },
  'deepseek/deepseek-flash': { provider: 'deepseek', id: 'deepseek-flash', cost: { input: 0.3 } },
  'openai-codex/gpt-6-astra': { provider: 'openai-codex', id: 'gpt-6-astra', cost: { input: 10 } },
  'openai-codex/gpt-6.1-sol': { provider: 'openai-codex', id: 'gpt-6.1-sol', cost: { input: 2 } },
  'openai-codex/gpt-6-luna': { provider: 'openai-codex', id: 'gpt-6-luna', cost: { input: 0.1 } },
};

function registry(extra = {}) {
  return {
    find: (provider, id) => models[`${provider}/${id}`],
    getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'k', headers: { h: '1' }, ...extra }),
  };
}

test('picks the cheaper same-provider summariser', () => {
  assert.equal(pickSummaryModel(models['anthropic/claude-opus-5-5'], registry(), {}).id, 'claude-sonnet-5-5');
});

test('codex: astra summarises with 6.1-sol, cheaper luna keeps its own model', () => {
  assert.equal(pickSummaryModel(models['openai-codex/gpt-6-astra'], registry(), {}).id, 'gpt-6.1-sol');
  assert.equal(pickSummaryModel(models['openai-codex/gpt-6-luna'], registry(), {}), undefined);
});

test('keeps native compaction when already on the summariser or another provider', () => {
  assert.equal(pickSummaryModel(models['anthropic/claude-sonnet-5-5'], registry(), {}), undefined);
  assert.equal(pickSummaryModel(models['deepseek/deepseek-flash'], registry(), {}), undefined);
  assert.equal(pickSummaryModel(undefined, registry(), {}), undefined);
});

test('falls through to the next candidate when the first is missing', () => {
  const reg = { find: (p, id) => (id === 'claude-sonnet-5-5' ? undefined : models[`${p}/${id}`]) };
  assert.equal(pickSummaryModel(models['anthropic/claude-opus-5-5'], reg, {}).id, 'claude-sonnet-5');
});

test('env override disables or forces a model', () => {
  const opus = models['anthropic/claude-opus-5-5'];
  assert.equal(pickSummaryModel(opus, registry(), { PI_COMPACTION_MODEL: 'off' }), undefined);
  assert.equal(pickSummaryModel(opus, registry(), { PI_COMPACTION_MODEL: 'deepseek/deepseek-flash' }).id, 'deepseek-flash');
  assert.equal(pickSummaryModel(opus, registry(), { PI_COMPACTION_MODEL: 'bogus' }), undefined);
});

function run(compact, { auth, signal } = {}) {
  let handler;
  createCompactionModel(async () => compact, {})({ on: (name, fn) => { assert.equal(name, 'session_before_compact'); handler = fn; } });
  const notes = [];
  const event = {
    preparation: { firstKeptEntryId: 'e1', settings: { reserveTokens: 700000, keepRecentTokens: 40000 } },
    customInstructions: 'focus', signal: signal ?? new AbortController().signal,
  };
  const ctx = { model: models['anthropic/claude-opus-5-5'], modelRegistry: registry(auth), ui: { notify: (m, l) => notes.push([l, m]) } };
  return handler(event, ctx).then((result) => ({ result, notes }));
}

test('runs native compact with the cheap model and a capped summary budget', async () => {
  let call;
  const { result } = await run(async (...args) => { call = args; return { summary: 's', firstKeptEntryId: 'e1', tokensBefore: 1 }; },
    { auth: { baseUrl: 'http://proxy' } });
  assert.equal(call[1].id, 'claude-sonnet-5-5');
  assert.equal(call[1].baseUrl, 'http://proxy');
  assert.equal(call[0].settings.reserveTokens, SUMMARY_RESERVE_TOKENS);
  assert.equal(call[0].settings.keepRecentTokens, 40000);
  assert.equal(call[2], 'k');
  assert.equal(call[4], 'focus');
  assert.deepEqual(result, { compaction: { summary: 's', firstKeptEntryId: 'e1', tokensBefore: 1 } });
});

test('falls back to native compaction on failure or missing auth', async () => {
  const failed = await run(async () => { throw new Error('quota'); });
  assert.equal(failed.result, undefined);
  assert.match(failed.notes[0][1], /quota/);
  const noAuth = await run(async () => assert.fail('must not run'), { auth: { ok: false } });
  assert.equal(noAuth.result, undefined);
});
