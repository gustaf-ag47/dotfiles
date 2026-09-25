import { test } from 'node:test';
import assert from 'node:assert/strict';
import { proxyUrl, proxyOptions, claudeIdentityPayload, PROXY_CREDENTIAL } from '../../config/pi/lib/anthropic-route.mjs';

test('only loopback origins are accepted, without credentials/paths/redirect destinations', () => {
  assert.equal(proxyUrl({}), 'http://127.0.0.1:8788');
  assert.equal(proxyUrl({ CC_PROXY_PORT: '8999' }), 'http://127.0.0.1:8999');
  for (const url of ['https://api.anthropic.com', 'http://localhost:8788', 'http://127.0.0.1/a',
    'http://user:pass@127.0.0.1', 'http://127.0.0.1?key=a', 'http://127.0.0.1#fragment']) {
    assert.throws(() => proxyUrl({ PI_ANTHROPIC_PROXY_URL: url }));
  }
});

test('identity rewrite preserves all harness instructions and never mutates input', () => {
  const payload = { system: [{ text: "You are Claude Code, Anthropic's official CLI for Claude." },
    { text: 'harness' }, { text: 'extra' }], messages: [{ role: 'user', content: 'question' }] };
  const next = claudeIdentityPayload(payload);
  assert.equal(payload.system.length, 3);
  assert.equal(next.system.length, 1);
  assert.equal(next.messages[0].content, 'harness\n\nextra\n\nquestion');
  assert.deepEqual(claudeIdentityPayload(next), next);
  assert.deepEqual(claudeIdentityPayload({ messages: [] }), { messages: [] });
});

test('proxy auth is request scoped and caller callback still runs', async () => {
  const original = { apiKey: 'fake-k', headers: { Authorization: 'fake', 'X-Api-Key': 'fake', 'x-test': 'keep' },
    onPayload: async p => ({ ...p, marker: true }) };
  const options = proxyOptions(original, {});
  assert.equal(options.apiKey, PROXY_CREDENTIAL);
  assert.deepEqual(options.headers, { 'x-test': 'keep' });
  assert.equal(original.apiKey, 'fake-k');
  assert.deepEqual(await options.onPayload({}), { marker: true });
  await assert.rejects(proxyOptions({}, { PI_ANTHROPIC_PROXY_URL: 'https://example.com' }).onPayload({}));
});
