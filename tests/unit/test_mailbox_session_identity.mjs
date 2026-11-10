import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { execFileSync } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mailbox-session-'));
process.env.PI_DELEGATE_MAILBOX = dir;
process.env.XDG_STATE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'mailbox-state-'));
process.env.TMUX_PANE = '%99';
const { default: setup } = await import('../../config/pi/extensions/delegate-mailbox.ts');
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
function boot(id) {
  const handlers = {}, sent = [];
  const ctx = { hasUI: false, sessionManager: { getSessionId: () => id } };
  setup({ on: (name, fn) => { handlers[name] = fn; }, sendMessage: m => sent.push(m) });
  return { handlers, sent, ctx };
}
function record(name, id) {
  fs.writeFileSync(path.join(dir, name), `# record\n- parent: \`%99\`\n${id ? `- recipient_session_id: \`${id}\`\n` : ''}\nfixture\n`);
}
test('two chats in the SAME pane must not receive each other’s pending mail', async () => {
  record('a.md', A);
  const b = boot(B);
  try {
    await b.handlers.session_start({}, b.ctx);
    assert.equal(b.sent.length, 0, 'B received A’s mail merely because pane was reused');
    assert.ok(fs.existsSync(path.join(dir, 'a.md')), 'wrong chat must not ack');
  } finally { await b.handlers.session_shutdown({}, b.ctx); }
});
test('legacy pane-only mail fails closed', async () => {
  record('legacy.md');
  const b = boot(B);
  try {
    await b.handlers.session_start({}, b.ctx);
    assert.equal(b.sent.length, 0);
    assert.ok(fs.existsSync(path.join(dir, 'quarantine', 'legacy.md')));
    assert.ok(!fs.existsSync(path.join(dir, 'ack', 'legacy.md')));
  } finally { await b.handlers.session_shutdown({}, b.ctx); }
});
test('same session resumed in another pane receives its mail', async () => {
  record('moved.md', A);
  process.env.TMUX_PANE = '%101';
  const a = boot(A);
  try {
    await a.handlers.session_start({}, a.ctx);
    assert.ok(a.sent.some(m => m.details.record.endsWith('/moved.md')));
  } finally { await a.handlers.session_shutdown({}, a.ctx); }
});

test('factory identity is not cached; repeated start/shutdown has only one live watcher', async () => {
  const b = boot(A);
  b.ctx.sessionManager.getSessionId = () => B;
  await b.handlers.session_start({}, b.ctx);
  await b.handlers.session_start({}, b.ctx);
  record('current-b.md', B);
  await delay(450);
  assert.equal(b.sent.filter(m => m.details.record.endsWith('/current-b.md')).length, 1);
  assert.ok(b.sent.every(m => m.details.recipient_session_id === B));
  await b.handlers.session_shutdown({}, b.ctx);
  await b.handlers.session_shutdown({}, b.ctx);
  const before = b.sent.length;
  record('after-stop.md', B);
  await delay(450);
  assert.equal(b.sent.length, before);
});

test('accepted messages cannot cross-ack after a switch; same session resumes elsewhere', async () => {
  record('accepted.md', A);
  const a = boot(A);
  await a.handlers.session_start({}, a.ctx);
  const message = a.sent.find(m => m.details.record.endsWith('/accepted.md'));
  assert.ok(message);
  await a.handlers.message_start({ message: { role: 'custom', ...message } }, boot(B).ctx);
  assert.ok(fs.existsSync(path.join(dir, 'accepted.md')));
  await a.handlers.session_shutdown({}, a.ctx);
  const b = boot(B);
  await b.handlers.session_start({}, b.ctx);
  await b.handlers.message_start({ message: { role: 'custom', ...message } }, b.ctx);
  assert.ok(fs.existsSync(path.join(dir, 'accepted.md')));
  await b.handlers.session_shutdown({}, b.ctx);
  process.env.TMUX_PANE = '%200';
  const resumed = boot(A);
  await resumed.handlers.session_start({}, resumed.ctx);
  const replay = resumed.sent.find(m => m.details.record.endsWith('/accepted.md'));
  await resumed.handlers.message_start({ message: { role: 'custom', ...replay } }, resumed.ctx);
  assert.ok(fs.existsSync(path.join(dir, 'ack', 'accepted.md')));
  const state = JSON.parse(fs.readFileSync(path.join(dir, 'state', 'accepted.md.json')));
  assert.equal(state.recipient_session_id, A);
  assert.equal(state.state, 'delivered');
  await resumed.handlers.session_shutdown({}, resumed.ctx);
});

test('async verification finishing after session replacement cannot deliver or ack', { timeout: 5000 }, async () => {
  const gate = path.join(dir, 'gate');
  execFileSync('mkfifo', [gate]);
  const helper = path.join(dir, 'verify');
  fs.writeFileSync(helper, `#!/bin/bash\necho ready > '${dir}/ready'\nread -r < '${gate}'\necho PASS\n`, { mode: 0o755 });
  process.env.PI_DELEGATE_VERIFY = helper;
  record('race.md', A);
  fs.appendFileSync(path.join(dir, 'race.md'), 'task: DONE abcdef1 - /report\n');
  const ready = new Promise(resolve => {
    const w = fs.watch(dir, (_e, name) => { if (name === 'ready') { w.close(); resolve(); } });
  });
  const a = boot(A);
  const starting = a.handlers.session_start({}, a.ctx);
  await ready;
  await a.handlers.session_shutdown({}, a.ctx);
  a.ctx.sessionManager.getSessionId = () => B;
  await a.handlers.session_start({}, a.ctx);
  fs.writeFileSync(gate, 'continue\n');
  await starting;
  assert.ok(!a.sent.some(m => m.details.record.endsWith('/race.md')));
  assert.ok(fs.existsSync(path.join(dir, 'race.md')));
  assert.ok(!fs.existsSync(path.join(dir, 'ack', 'race.md')));
  await a.handlers.session_shutdown({}, a.ctx);
  delete process.env.PI_DELEGATE_VERIFY;
});
