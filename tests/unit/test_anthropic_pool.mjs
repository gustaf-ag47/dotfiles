import { test } from 'node:test';
import assert from 'node:assert/strict';
import anthropicPool, {
  ANTHROPIC, CLAUDE_CODE_IDENTITY, CLASS_HEADER, PLACEHOLDER_KEY, SESSION_HEADER, fetchStatus, moveHarnessPromptIntoFirstMessage,
  proxyOrigin, sessionKey, statusLine,
} from '../../config/pi/extensions/anthropic-pool.ts';

const oauthPayload = (messages) => ({
  system: [{ type: 'text', text: CLAUDE_CODE_IDENTITY }, { type: 'text', text: 'harness prompt' }],
  messages,
});

function fakePi() {
  const providers = [];
  const handlers = {};
  anthropicPool({
    registerProvider: (name, config) => providers.push([name, config]),
    on: (name, fn) => { handlers[name] = fn; },
  });
  return { providers, handlers };
}

test('proxy origin: default port, CC_PROXY_PORT, explicit URL, opt-out', () => {
  assert.equal(proxyOrigin({}), 'http://127.0.0.1:8788');
  assert.equal(proxyOrigin({ CC_PROXY_PORT: '8790' }), 'http://127.0.0.1:8790');
  assert.equal(proxyOrigin({ PI_ANTHROPIC_PROXY_URL: 'http://127.0.0.1:9000/' }), 'http://127.0.0.1:9000');
  for (const off of ['off', '0', 'none', 'FALSE', 'no']) assert.equal(proxyOrigin({ PI_ANTHROPIC_POOL: off }), null);
  assert.equal(proxyOrigin({ PI_ANTHROPIC_POOL: 'on', PI_ANTHROPIC_PROXY_URL: 'http://127.0.0.1:9000' }), 'http://127.0.0.1:9000');
});

test('registers anthropic with proxy baseUrl, placeholder key and the fallback opt-out header', () => {
  const { providers } = fakePi();
  assert.deepEqual(providers, [[ANTHROPIC, {
    baseUrl: 'http://127.0.0.1:8788', apiKey: PLACEHOLDER_KEY, headers: { 'x-cc-proxy-fallback': 'none' },
  }]]);
  assert.match(PLACEHOLDER_KEY, /^sk-ant-oat/); // pi keys subscription-auth behaviour on this prefix
});

test('opt-out registers nothing at all', () => {
  const saved = process.env.PI_ANTHROPIC_POOL;
  process.env.PI_ANTHROPIC_POOL = 'off';
  try {
    const { providers, handlers } = fakePi();
    assert.deepEqual(providers, []);
    assert.deepEqual(Object.keys(handlers), []);
  } finally {
    if (saved === undefined) delete process.env.PI_ANTHROPIC_POOL; else process.env.PI_ANTHROPIC_POOL = saved;
  }
});

test('harness prompt moves into the first user message (string, blocks, empty)', () => {
  const s = moveHarnessPromptIntoFirstMessage(oauthPayload([{ role: 'user', content: 'hi' }]));
  assert.equal(s.system.length, 1);
  assert.equal(s.messages[0].content, 'harness prompt\n\nhi');
  const b = moveHarnessPromptIntoFirstMessage(oauthPayload([{ role: 'user', content: [{ type: 'text', text: 'hi' }] }]));
  assert.equal(b.messages[0].content[0].text, 'harness prompt\n\nhi');
  const e = moveHarnessPromptIntoFirstMessage(oauthPayload([]));
  assert.deepEqual(e.messages, [{ role: 'user', content: 'harness prompt' }]);
  const img = moveHarnessPromptIntoFirstMessage(oauthPayload([{ role: 'user', content: [{ type: 'image' }] }]));
  assert.equal(img.messages[0].content, 'harness prompt');
  assert.equal(img.messages.length, 2);
});

test('payloads that are not the OAuth shape are left alone, and the input is never mutated', () => {
  assert.equal(moveHarnessPromptIntoFirstMessage(null), null);
  assert.equal(moveHarnessPromptIntoFirstMessage({ system: 'string', messages: [] }), null);
  assert.equal(moveHarnessPromptIntoFirstMessage({ system: [{ text: 'other identity' }, { text: 'x' }], messages: [] }), null);
  assert.equal(moveHarnessPromptIntoFirstMessage({ system: [{ text: CLAUDE_CODE_IDENTITY }], messages: [] }), null);
  const input = oauthPayload([{ role: 'user', content: 'hi' }]);
  moveHarnessPromptIntoFirstMessage(input);
  assert.equal(input.system.length, 2);
  assert.equal(input.messages[0].content, 'hi');
});

test('before_provider_request only rewrites anthropic requests', () => {
  const { handlers } = fakePi();
  const payload = oauthPayload([{ role: 'user', content: 'hi' }]);
  assert.equal(handlers.before_provider_request({ payload }, { model: { provider: 'openai-codex' } }), undefined);
  assert.equal(handlers.before_provider_request({ payload }, { model: undefined }), undefined);
  const out = handlers.before_provider_request({ payload }, { model: { provider: ANTHROPIC } });
  assert.equal(out.system.length, 1);
});

test('status line: unreachable, empty pool, healthy', () => {
  assert.match(statusLine(null, 'http://x'), /not reachable at http:\/\/x/);
  assert.match(statusLine({ available: 0 }, 'http://x'), /no OAuth account/);
  assert.equal(statusLine({ available: 2 }, 'http://x'), null);
});

test('fetchStatus returns null on network error, non-2xx and timeout', async () => {
  assert.equal(await fetchStatus('http://x', async () => { throw new Error('down'); }), null);
  assert.equal(await fetchStatus('http://x', async () => ({ ok: false })), null);
  const hang = (_url, { signal }) => new Promise((_, reject) => signal.addEventListener('abort', () => reject(new Error('abort'))));
  assert.equal(await fetchStatus('http://x', hang, 10), null);
  assert.deepEqual(await fetchStatus('http://x', async () => ({ ok: true, json: async () => ({ available: 1 }) })), { available: 1 });
});

test('session_start warns only for anthropic sessions and only when unhealthy', async () => {
  const { handlers } = fakePi();
  const notes = [];
  const ctx = (provider, hasUI = true) => ({ model: { provider }, hasUI, ui: { notify: (l, lvl) => notes.push([l, lvl]) } });
  await handlers.session_start({}, ctx('openai-codex'));
  assert.deepEqual(notes, []);
  // Nothing listens on this port in the test: unreachable → one warning.
  const saved = process.env.PI_ANTHROPIC_PROXY_URL;
  process.env.PI_ANTHROPIC_PROXY_URL = 'http://127.0.0.1:1';
  try {
    const { handlers: h } = fakePi();
    await h.session_start({}, ctx(ANTHROPIC));
    assert.equal(notes.length, 1);
    assert.equal(notes[0][1], 'warning');
    assert.match(notes[0][0], /not reachable/);
  } finally {
    if (saved === undefined) delete process.env.PI_ANTHROPIC_PROXY_URL; else process.env.PI_ANTHROPIC_PROXY_URL = saved;
  }
});

test('class and escalation headers are sent only to Anthropic', () => {
  const oldClass = process.env.PI_LLM_CLASS;
  const oldEscalate = process.env.PI_LLM_CLASS_ESCALATE;
  process.env.PI_LLM_CLASS = 'build';
  process.env.PI_LLM_CLASS_ESCALATE = '1';
  try {
    const { handlers } = fakePi();
    const headers = {};
    handlers.before_provider_headers({ headers }, { model: { provider: ANTHROPIC } });
    assert.equal(headers[CLASS_HEADER], 'build');
    assert.equal(headers['x-cc-proxy-class-escalate'], '1');
    const other = {};
    handlers.before_provider_headers({ headers: other }, { model: { provider: 'openai-codex' } });
    assert.equal(other[CLASS_HEADER], undefined);
  } finally {
    if (oldClass === undefined) delete process.env.PI_LLM_CLASS; else process.env.PI_LLM_CLASS = oldClass;
    if (oldEscalate === undefined) delete process.env.PI_LLM_CLASS_ESCALATE; else process.env.PI_LLM_CLASS_ESCALATE = oldEscalate;
  }
});

test('session header: anthropic only, stable per session, process fallback', () => {
  const { handlers } = fakePi();
  const sm = { getSessionId: () => 'abc' };
  const h1 = {}; handlers.before_provider_headers({ headers: h1 }, { model: { provider: ANTHROPIC }, sessionManager: sm });
  const h2 = {}; handlers.before_provider_headers({ headers: h2 }, { model: { provider: ANTHROPIC }, sessionManager: sm });
  assert.equal(h1[SESSION_HEADER], 'pi-abc');
  assert.equal(h2[SESSION_HEADER], 'pi-abc');
  assert.equal(h1[CLASS_HEADER], 'interactive');
  const h3 = {}; handlers.before_provider_headers({ headers: h3 }, { model: { provider: 'openai-codex' }, sessionManager: sm });
  assert.equal(h3[SESSION_HEADER], undefined);
  assert.equal(h3[CLASS_HEADER], undefined);
  const h4 = {}; handlers.before_provider_headers({ headers: h4 }, { model: { provider: ANTHROPIC } });
  assert.match(h4[SESSION_HEADER], /^pi-\d+-/);
  assert.equal(sessionKey({ sessionManager: { getSessionId: () => { throw new Error('x'); } } }, 'fb'), 'fb');
});
