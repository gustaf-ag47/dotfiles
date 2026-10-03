import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRuntime, completeField, responseText, validateContext, parseModel } from '../../config/pi/skills/jev-ultrafast/scripts/_pi_text_worker.mjs';

const context = () => ({ goal: 'Enter London as the destination', field: { label: 'Destination', role: 'textbox', value: '' }, page: { title: 'Local fixture', text: 'Destination' }, recent_actions: [] });
const message = text => ({ stopReason: 'stop', content: [{ type: 'text', text }] });

test('bootstrap supports Pi import-only exports without discovery or model refresh', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pi-sdk-fixture-'));
  try {
    fs.mkdirSync(path.join(root, 'dist'));
    fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ name: '@earendil-works/pi-coding-agent', type: 'module', exports: { '.': { import: './dist/index.mjs' } } }));
    fs.writeFileSync(path.join(root, 'dist/index.mjs'), 'export const ModelRuntime = { create: async options => ({options}) };');
    const runtime = await createRuntime({ sdkRoot: root, model: 'openai-codex/test-model', agentDir: root, piDir: root });
    assert.equal(runtime.options.modelsPath, null);
    assert.equal(runtime.options.allowModelNetwork, false);
    assert.equal(runtime.options.refreshOnCreate, false);
    assert.equal(runtime.options.authPath, path.join(root, 'auth.json'));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('one completion gets only field context; no tools, retries or caller history', async () => {
  let calls = 0;
  const runtime = {
    getModel: (provider, id) => ({ provider, id }),
    completeSimple: async (model, ctx, opts) => {
      calls++;
      assert.equal(model.provider, 'openai-codex');
      assert.deepEqual(ctx.tools, []);
      assert.equal(ctx.messages.length, 1);
      assert.deepEqual(JSON.parse(ctx.messages[0].content[0].text), context());
      assert.match(ctx.systemPrompt, /untrusted data/);
      assert.equal(opts.maxRetries, 0);
      assert.equal(opts.toolChoice, 'none');
      assert.equal(opts.cacheRetention, 'none');
      assert.equal(opts.maxTokens, 1024);
      return message('{"text":"London"}');
    },
  };
  const result = await completeField(runtime, 'openai-codex/test-model', context());
  assert.equal(calls, 1);
  assert.deepEqual(result, { ok: true, text: 'London', model: 'openai-codex/test-model', usage: null });
});

test('Anthropic completion forbids silent proxy backend fallback', async () => {
  await completeField({ getModel: () => ({}), completeSimple: async (_m, _c, opts) => {
    assert.equal(opts.headers['x-cc-proxy-fallback'], 'none');
    return message('{"text":"London"}');
  } }, 'anthropic/test-model', context());
});

test('no fallback or retry when the provider rejects or model is missing', async () => {
  let calls = 0;
  const runtime = { getModel: () => ({}), completeSimple: async () => { calls++; return { stopReason: 'error', errorMessage: 'PRIVATE_RAW_ERROR' }; } };
  await assert.rejects(completeField(runtime, 'grok-build/test-model', context()), /^Error: provider_failed$/);
  assert.equal(calls, 1);
  runtime.getModel = () => undefined;
  await assert.rejects(completeField(runtime, 'grok-build/missing', context()), /model_unavailable/);
  assert.equal(calls, 1);
});

test('strict output validation; a model tool call is never executed', () => {
  for (const text of ['London', '```json\n{"text":"London"}\n```', '{"text":"x","extra":1}', '{"text":42}', '{"text":""}', JSON.stringify({ text: 'x'.repeat(2001) }), '{"text":"\\u0000"}']) {
    assert.throws(() => responseText(message(text)), /invalid_response/);
  }
  assert.throws(() => responseText(message('{"text":null}')), /missing_value/);
  assert.throws(() => responseText({ ...message('{"text":"x"}'), stopReason: 'length' }), /provider_failed/);
  assert.throws(() => responseText({ stopReason: 'stop', content: [{ type: 'toolCall', name: 'bash', arguments: { command: 'echo not-run' } }] }), /invalid_response/);
});

test('only the bounded upstream field_context shape is accepted', () => {
  assert.equal(validateContext(context()).goal, context().goal);
  for (const bad of [null, [], { ...context(), history: 'unrelated agent history' }, { ...context(), page: { title: 'x', text: 'x', cookies: 'private' } }, { ...context(), recent_actions: Array(7).fill({ text: 'x' }) }, { ...context(), goal: 'x'.repeat(32769) }]) {
    assert.throws(() => validateContext(bad), /invalid_request/);
  }
});

test('model selection is exact, constrained, and never a shell command', () => {
  assert.deepEqual(parseModel('openai-codex/gpt-5.6-luna'), { provider: 'openai-codex', id: 'gpt-5.6-luna' });
  for (const bad of ['openrouter/paid-model', 'anthropic', 'anthropic/model;echo', 'grok-build/../../file', 'openai-codex/test:high']) {
    assert.throws(() => parseModel(bad), /invalid_request/);
  }
});
