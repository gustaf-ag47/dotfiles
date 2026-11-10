// Run: PI_TEST_SDK=/absolute/path/to/pi-coding-agent/dist/index.js node tests/mailbox-session-e2e.mjs
// Real Pi lifecycle + real tmux + real sender + loopback fixture model; no live agents touched.
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import * as net from 'node:net';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
const sdk = process.env.PI_TEST_SDK;
assert.ok(sdk && fs.existsSync(sdk), 'PI_TEST_SDK must point to the installed SDK dist/index.js');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'session-mailbox-e2e-'));
for (const name of ['cwd', 'state', 'mailbox']) fs.mkdirSync(path.join(root, name));
const tmuxSocket = path.join(root, 'tmux.sock');
const env = { ...process.env, HOME: path.join(root, 'home'), XDG_STATE_HOME: path.join(root, 'state'),
  XDG_CONFIG_HOME: path.join(root, 'config'), XDG_CACHE_HOME: path.join(root, 'cache'), XDG_DATA_HOME: path.join(root, 'data'),
  PI_CODING_AGENT_DIR: path.join(root, 'agent'), PI_DELEGATE_MAILBOX: path.join(root, 'mailbox'), TMUX: tmuxSocket + ',0,0' };
for (const key of ['HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'PI_CODING_AGENT_DIR']) fs.mkdirSync(env[key], { recursive: true });
const tmux = (...args) => execFileSync('tmux', ['-S', tmuxSocket, ...args], { encoding: 'utf8' }).trim();
const quote = s => "'" + s.replaceAll("'", "'\\''") + "'";
const worker = label => ['env', '-u', 'PI_SESSION_ID', '-u', 'PI_SESSION_FILE',
  ...['HOME', 'XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'PI_CODING_AGENT_DIR', 'PI_DELEGATE_MAILBOX'].map(key => `${key}=${env[key]}`), 'PI_OFFLINE=1',
  process.execPath, path.resolve('tests/fixtures/mailbox-runtime.mjs'), root, label, sdk];
function command(label, file) {
  return [...worker(label), ...(file ? [file] : [])].map(quote).join(' ') + ` > ${quote(path.join(root, label + '.log'))} 2>&1`;
}
async function untilFile(file) {
  if (fs.existsSync(file)) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { w.close(); reject(new Error('timed out: ' + file)); }, 15000);
    const w = fs.watch(path.dirname(file), () => { if (fs.existsSync(file)) { clearTimeout(timer); w.close(); resolve(); } });
    if (fs.existsSync(file)) { clearTimeout(timer); w.close(); resolve(); }
  });
}
const call = (label, data = { op: 'state' }) => new Promise((resolve, reject) => {
  const socket = net.createConnection(path.join(root, label + '.sock'));
  socket.setTimeout(15000, () => socket.destroy(new Error('control timeout')));
  let response = '';
  socket.on('connect', () => socket.write(JSON.stringify(data) + '\n'));
  socket.on('data', chunk => { response += chunk; });
  socket.on('error', reject);
  socket.on('end', () => { const result = JSON.parse(response); if (result.error) reject(new Error(result.error)); else resolve(result); });
});
const send = (target, text) => execFileSync(path.resolve('bin/delegate-send'), [target, '--text', text], { env, encoding: 'utf8' }).trim();
const ack = record => untilFile(path.join(root, 'mailbox', 'ack', path.basename(record)));
let passed = 0;
const pass = what => { passed++; console.log('PASS ' + what); };
try {
  fs.writeFileSync(path.join(root, 'tmux.conf'), 'set -g default-shell /bin/bash\n');
  tmux('-f', path.join(root, 'tmux.conf'), 'new-session', '-d', '-s', 'test', '-n', 'one', command('one'));
  await untilFile(path.join(root, 'one.ready'));
  const a = await call('one');
  assert.ok(a.file.startsWith(root + '/')); // SDK journal must never touch the user's sessions
  pass('HOME, all XDG paths, agent dir, journals, mailbox and tmux socket are isolated');
  const paneA = tmux('display', '-p', '-t', 'test:one', '#{pane_id}');
  const first = send(paneA, 'FIXTURE_ACTIVE_A');
  await ack(first);
  await call('one', { op: 'settle' });
  assert.ok((await call('one')).records.some(r => r.record === first && r.session === a.id));
  pass('pane sender resolves real live SDK session A; native custom message starts and acks');
  const metadata = path.join(root, 'state', 'pi-panes');
  const capability = path.join(metadata, fs.readdirSync(metadata).find(name => name.endsWith('.mailbox')));
  fs.renameSync(capability, capability + '.saved');
  const beforeRefusal = fs.readdirSync(path.join(root, 'mailbox')).sort();
  assert.throws(() => send(paneA, 'FIXTURE_OLD_CONSUMER_MUST_REFUSE'), /protocol-2 mailbox consumer/);
  assert.deepEqual(fs.readdirSync(path.join(root, 'mailbox')).sort(), beforeRefusal);
  fs.renameSync(capability + '.saved', capability);
  pass('mixed rollout: new sender clearly refuses old/missing consumer capability and creates no record');

  const b = await call('one', { op: 'new' });
  assert.notEqual(b.id, a.id);
  const pending = send('session:' + a.id, 'FIXTURE_PENDING_A');
  assert.doesNotMatch(fs.readFileSync(pending, 'utf8'), /^- parent: /m, 'old pane-only consumers must not match new records');
  const forB = send(paneA, 'FIXTURE_ONLY_B');
  await ack(forB); await call('one', { op: 'settle' });
  assert.ok(fs.existsSync(pending));
  assert.ok(!(await call('one')).records.some(r => r.record === pending));
  pass('new chat B in SAME real tmux pane does not receive or ack A’s mail; pane sender now targets B');

  const legacy = path.join(root, 'mailbox', 'legacy.md');
  fs.writeFileSync(legacy, `# legacy\n- parent: \`${paneA}\`\n\nFIXTURE_LEGACY`);
  await untilFile(path.join(root, 'mailbox', 'quarantine', 'legacy.md'));
  assert.ok(!fs.existsSync(path.join(root, 'mailbox', 'ack', 'legacy.md')));
  pass('pane-only legacy record preserved in quarantine, never delivered/acked');

  tmux('new-window', '-d', '-t', 'test:', '-n', 'two', command('two', a.file));
  await untilFile(path.join(root, 'two.ready')); await ack(pending);
  const moved = await call('two', { op: 'settle' });
  assert.equal(moved.id, a.id);
  assert.notEqual(tmux('display', '-p', '-t', 'test:two', '#{pane_id}'), paneA);
  assert.ok(moved.records.some(r => r.record === pending && r.session === a.id));
  pass('SAME session A resumed in a DIFFERENT real pane receives its pending mail');

  const fork = await call('two', { op: 'fork' });
  assert.notEqual(fork.id, a.id);
  const afterFork = send('session:' + a.id, 'FIXTURE_NOT_FOR_FORK');
  await delay(650);
  assert.ok(fs.existsSync(afterFork));
  assert.ok(!(await call('two')).records.some(r => r.record === afterFork));
  pass('fork gets a new ID and cannot receive the original session’s pending mail');
  await call('one', { op: 'resume', file: a.file }); await ack(afterFork);
  await call('one', { op: 'settle' });

  await call('one', { op: 'busy' });
  const queued = send('session:' + a.id, 'FIXTURE_QUEUED_BEFORE_SWITCH');
  await untilFile(path.join(root, 'mailbox', 'state', path.basename(queued) + '.json'));
  await delay(650); // allow fs.watch settle + acceptance while fixture model is held
  const queuedState = JSON.parse(fs.readFileSync(path.join(root, 'mailbox', 'state', path.basename(queued) + '.json')));
  assert.equal(queuedState.state, 'accepted');
  const replacement = await call('one', { op: 'new' });
  await delay(650);
  assert.ok(fs.existsSync(queued));
  assert.ok(!(await call('one')).records.some(r => r.record === queued && r.session === replacement.id));
  pass('accepted/queued steering before native newSession cannot escape into replacement chat');
  await call('one', { op: 'resume', file: a.file }); await ack(queued); await call('one', { op: 'settle' });
  const final = await call('one');
  assert.ok(final.records.some(r => r.record === queued && r.session === a.id));
  pass('unconsumed queued mail replays only when its original session resumes');
  const state = JSON.parse(fs.readFileSync(path.join(root, 'mailbox', 'state', path.basename(queued) + '.json')));
  assert.equal(state.recipient_session_id, a.id); assert.equal(state.state, 'delivered');
  pass('queued/accepted/delivered state consistently carries the full recipient session ID');
  // A second ordinary Pi under the SAME pane/TTY/root shell, with no sidecar.
  // The sender must not select the sole publishing process and overlook it.
  const duplicate = path.join(root, 'duplicate.cjs');
  fs.writeFileSync(duplicate, `process.title='pi';require('fs').writeFileSync(${JSON.stringify(path.join(root, 'duplicate.ready'))}, String(process.pid));setInterval(()=>{},1000);`);
  // The worker starts it as its own child, hence both descend from the same pane shell.
  await call('one', { op: 'duplicate', file: duplicate });
  await untilFile(path.join(root, 'duplicate.ready'));
  assert.throws(() => send(paneA, 'FIXTURE_MUST_REFUSE_AMBIGUOUS'), /no unique live Pi/);
  pass('two ordinary Pi processes in same real pane/TTY fail closed even when only one publishes identity');
  await call('one', { op: 'quit' }); await call('two', { op: 'quit' });
  console.log(`E2E PASS: ${passed} checks, native Pi SDK ${sdk}`);
} catch (error) {
  console.error('state files', fs.readdirSync(path.join(root, 'state'), { recursive: true }));
  const mappings = path.join(root, 'state', 'pi-panes');
  if (fs.existsSync(mappings)) for (const f of fs.readdirSync(mappings)) {
    console.error(f, fs.readFileSync(path.join(mappings, f), 'utf8'));
    if (f.endsWith('.json')) { const d = JSON.parse(fs.readFileSync(path.join(mappings, f))); console.error('comm', fs.readFileSync(`/proc/${d.pid}/comm`, 'utf8'), 'stat', fs.readFileSync(`/proc/${d.pid}/stat`, 'utf8'), 'header', fs.readFileSync(d.session_file, 'utf8').split('\n')[0]); }
  }
  console.error('tmux panes', tmux('list-panes', '-a', '-F', '#{pane_id} #{pane_pid} #{pane_current_command} #{socket_path}'));
  for (const name of ['one', 'two']) {
    const file = path.join(root, name + '.log'); if (fs.existsSync(file)) console.error(name, fs.readFileSync(file, 'utf8'));
  }
  throw error;
} finally {
  try { tmux('kill-server'); } catch { /* gone already */ }
  fs.rmSync(root, { recursive: true, force: true });
}
