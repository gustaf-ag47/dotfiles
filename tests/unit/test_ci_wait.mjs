// ci-wait.ts: register a CI watch, poll gh in the background, re-prompt in-band.
// Contract under test: the tool terminates the turn with the `ci_wait registered:`
// phrase the delegate supervisor matches; pending CI never wakes; green/red/merge/
// conflict/close/post-merge/timeout-ish states wake exactly once with a
// `CI WAIT RESOLVED` custom message; cancelled siblings are not red; gh failures
// are unknown until N in a row; watches survive a restart via session entries;
// a busy agent gets a followUp; `ci-wait:state` tracks the active set.
// gh is faked through the injectable exec (no network).
import { test } from 'node:test';
import assert from 'node:assert/strict';

process.env.PI_CI_WAIT_MAX_FAILURES = '3';
const { setup, summarizeChecks } = await import('../../config/pi/extensions/ci-wait.ts');

const REPO = 'o/r';

// Fake gh: routes on the subcommand; `state` is mutated by each test.
function fakeGh(state) {
  const calls = [];
  const ok = (v) => ({ code: 0, stdout: JSON.stringify(v), stderr: '' });
  const exec = async (args) => {
    calls.push(args);
    if (state.fail) return { code: 1, stdout: '', stderr: 'HTTP 502' };
    const [a, b] = args;
    if (a === 'repo') return { code: 0, stdout: `${REPO}\n`, stderr: '' };
    if (a === 'pr' && b === 'view') return ok({ state: 'OPEN', mergeable: 'MERGEABLE', mergeStateStatus: 'BLOCKED', autoMergeRequest: null, headRefOid: 'a'.repeat(40), baseRefName: 'master', url: 'https://github.com/o/r/pull/7', ...state.pr });
    if (a === 'pr' && b === 'checks') {
      if (state.noRequired && args.includes('--required')) return { code: 1, stdout: '', stderr: "no required checks reported on the 'x' branch" };
      const checks = state.checks ?? [];
      const code = checks.some((c) => c.bucket === 'pending') ? 8 : checks.some((c) => c.bucket === 'fail') ? 1 : 0;
      return { code, stdout: JSON.stringify(checks), stderr: '' };
    }
    if (a === 'run' && b === 'list') return ok((state.runs ?? []).map((r) => ({ event: 'push', ...r })));
    if (a === 'run' && b === 'view' && args.includes('--log-failed')) return { code: 0, stdout: Array.from({ length: 100 }, (_, i) => `log line ${i}`).join('\n'), stderr: '' };
    if (a === 'run' && b === 'view') return ok(state.run);
    throw new Error(`unexpected gh ${args.join(' ')}`);
  };
  return { exec, calls };
}

function boot(state, { entries = [], idle = true, sendThrows = false } = {}) {
  const sent = [], appended = [], events = [], handlers = {};
  let tool, command;
  let t = 1_000_000;
  const pi = {
    on: (name, fn) => { handlers[name] = fn; },
    registerTool: (def) => { tool = def; },
    registerCommand: (name, def) => { command = def; },
    appendEntry: (customType, data) => { appended.push(data); entries.push({ type: 'custom', customType, data }); },
    sendMessage: (message, opts) => {
      if (sendThrows && !opts.deliverAs) throw new Error('busy');
      sent.push([message, opts]);
    },
    events: { emit: (name, data) => events.push([name, data]) },
  };
  const gh = fakeGh(state);
  const api = setup(pi, { exec: gh.exec, now: () => t, autoPoll: false });
  const ctx = { cwd: '/x', hasUI: false, isIdle: () => idle, sessionManager: { getBranch: () => entries } };
  const advance = (ms) => { t += ms; };
  return { api, pi, tool, command, handlers, sent, appended, events, ctx, gh, advance, entries };
}

async function register(b, params) {
  await b.handlers.session_start({}, b.ctx);
  return b.tool.execute('call1', params, undefined, undefined, b.ctx);
}

const check = (name, bucket, link = 'https://github.com/o/r/actions/runs/42/job/1') => ({ name, bucket, state: bucket.toUpperCase(), link, workflow: 'ci' });

test('tool registers, terminates the turn and prints the supervisor phrase', async () => {
  const b = boot({});
  const res = await register(b, { pr: 7 });
  assert.equal(res.terminate, true);
  assert.match(res.content[0].text, /^ci_wait registered: w1 o\/r#7 until checks/);
  assert.equal(b.appended[0].op, 'registered');
  assert.deepEqual(b.events.at(-1), ['ci-wait:state', { active: true, watches: [{ id: 'w1', target: 'o/r#7', until: 'checks' }] }]);
  await assert.rejects(b.tool.execute('c', { pr: 1, run: 2 }, undefined, undefined, b.ctx), /exactly one/);
  await assert.rejects(b.tool.execute('c', { run: 2, until: 'merged' }, undefined, undefined, b.ctx), /needs a pr/);
});

test('pending checks do not wake; all green wakes once and clears state', async () => {
  const state = { checks: [check('test', 'pass'), check('lint', 'pending')] };
  const b = boot(state);
  await register(b, { pr: 7, note: 'then merge' });
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  state.checks = [check('test', 'pass'), check('lint', 'pass')];
  await b.api.tick();
  assert.equal(b.sent.length, 1);
  const [msg, opts] = b.sent[0];
  assert.equal(msg.customType, 'ci-wait');
  assert.equal(msg.display, true);
  assert.deepEqual(opts, { triggerTurn: true });
  assert.match(msg.content, /^CI WAIT RESOLVED - o\/r#7: green - 2\/2 checks/);
  assert.match(msg.content, /note: then merge/);
  assert.equal(b.appended.at(-1).op, 'resolved');
  assert.deepEqual(b.events.at(-1), ['ci-wait:state', { active: false, watches: [] }]);
  await b.api.tick();
  assert.equal(b.sent.length, 1);
});

test('red wakes with failing names, link and a bounded log tail', async () => {
  const b = boot({ checks: [check('test', 'fail'), check('lint', 'pending')] });
  await register(b, { pr: 7 });
  await b.api.tick();
  assert.equal(b.sent.length, 1);
  const text = b.sent[0][0].content;
  assert.match(text, /red - test/);
  assert.match(text, /- test \(ci\): FAIL https:\/\/github.com\/o\/r\/actions\/runs\/42/);
  assert.match(text, /gh run view 42 -R o\/r --log-failed/);
  assert.match(text, /log line 99/);
  assert.doesNotMatch(text, /log line 39\n/);
  assert.equal(b.sent[0][0].details.red, true);
});

test('a cancelled or failed sibling of a live check is not red; lone cancel neither', () => {
  const s = summarizeChecks([check('a', 'cancel'), check('a', 'pending'), check('b', 'fail'), check('b', 'pass'), check('c', 'cancel')]);
  assert.deepEqual(s.failed, []);
  assert.deepEqual(s.pending, ['a']);
  assert.deepEqual(s.cancelled, ['c']);
});

test('cancelled sibling keeps waiting until the live run finishes', async () => {
  const state = { checks: [check('test', 'cancel'), check('test', 'pending')] };
  const b = boot(state);
  await register(b, { pr: 7 });
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  state.checks = [check('test', 'cancel'), check('test', 'pass')];
  await b.api.tick();
  assert.match(b.sent[0][0].content, /green - 1\/1/);
});

test('retries without --required when the repo has no required checks', async () => {
  const b = boot({ noRequired: true, checks: [check('test', 'pass')] });
  await register(b, { pr: 7 });
  await b.api.tick();
  assert.match(b.sent[0][0].content, /green/);
  assert.ok(b.gh.calls.some((a) => a[1] === 'checks' && !a.includes('--required')));
});

for (const [name, pr, re] of [
  ['merged', { state: 'MERGED', mergeCommit: { oid: 'b'.repeat(40) } }, /merged as bbbbbbb/],
  ['closed', { state: 'CLOSED' }, /closed without merge/],
  ['conflict', { mergeable: 'CONFLICTING', mergeStateStatus: 'DIRTY' }, /merge conflict/],
  ['behind without auto-merge', { mergeStateStatus: 'BEHIND' }, /behind master/],
]) {
  test(`PR ${name} wakes`, async () => {
    const b = boot({ pr, checks: [check('t', 'pending')] });
    await register(b, { pr: 7, until: 'merged' });
    await b.api.tick();
    assert.equal(b.sent.length, 1);
    assert.match(b.sent[0][0].content, re);
  });
}

test('until merged: green with auto-merge keeps waiting; auto-merge disabled wakes', async () => {
  const state = { pr: { autoMergeRequest: { enabledAt: 'x' } }, checks: [check('t', 'pass')] };
  const b = boot(state);
  await register(b, { pr: 7, until: 'merged' });
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  state.pr = { autoMergeRequest: null };
  await b.api.tick();
  assert.match(b.sent[0][0].content, /auto-merge was disabled/);
});

test('head SHA change re-arms and is reported at resolution', async () => {
  const state = { checks: [check('t', 'pending')] };
  const b = boot(state);
  await register(b, { pr: 7 });
  await b.api.tick();
  state.pr = { headRefOid: 'c'.repeat(40) };
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  state.checks = [check('t', 'pass')];
  await b.api.tick();
  assert.match(b.sent[0][0].content, /new head ccccccc \(was aaaaaaa\); re-armed/);
});

for (const [verdict, conclusion] of [['green', 'success'], ['red', 'failure']]) {
  test(`post-merge waits for base runs at the merge commit: ${verdict}`, async () => {
    const sha = 'd'.repeat(40);
    const state = { pr: { state: 'OPEN' }, checks: [check('t', 'pass')] };
    state.pr.autoMergeRequest = { enabledAt: 'x' };
    const b = boot(state);
    await register(b, { pr: 7, until: 'post-merge' });
    await b.api.tick();
    state.pr = { state: 'MERGED', mergeCommit: { oid: sha } };
    state.runs = [{ databaseId: 9, workflowName: 'dotfiles', status: 'in_progress', conclusion: '', url: 'u9', headSha: sha }];
    await b.api.tick();
    assert.equal(b.sent.length, 0);
    assert.ok(b.gh.calls.some((a) => a[1] === 'list' && a.includes('--commit') && a.includes(sha) && a.includes('master')));
    state.runs = [{ databaseId: 9, workflowName: 'dotfiles', status: 'completed', conclusion, url: 'u9', headSha: sha }];
    await b.api.tick();
    assert.equal(b.sent.length, 1);
    assert.match(b.sent[0][0].content, new RegExp(`${verdict} - .*master @ ddddddd`));
  });
}

test('run target: completed failure wakes red', async () => {
  const state = { run: { status: 'in_progress', conclusion: '', url: 'u', workflowName: 'ci', jobs: [] } };
  const b = boot(state);
  await register(b, { run: 55 });
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  state.run = { status: 'completed', conclusion: 'failure', url: 'u', workflowName: 'ci', jobs: [{ name: 'lint', status: 'completed', conclusion: 'failure', url: 'j' }] };
  await b.api.tick();
  assert.match(b.sent[0][0].content, /run 55: red - ci failure[\s\S]*- lint: failure j/);
});

test('gh failure is unknown, then actionable after N consecutive failures', async () => {
  const state = { checks: [check('t', 'pending')] };
  const b = boot(state);
  await register(b, { pr: 7 });
  state.fail = true;
  await b.api.tick();
  await b.api.tick();
  assert.equal(b.sent.length, 0);
  await b.api.tick();
  assert.equal(b.sent.length, 1);
  assert.match(b.sent[0][0].content, /cannot read CI \(3 consecutive gh failures\)[\s\S]*HTTP 502/);
});

test('restart reconstructs active watches from session entries', async () => {
  const first = boot({});
  await register(first, { pr: 7 });
  await first.tool.execute('c2', { pr: 8 }, undefined, undefined, first.ctx);
  first.handlers.session_shutdown({}, {});
  // Resolve w1 in the persisted history, then restart on the same entries.
  first.entries.push({ type: 'custom', customType: 'ci-wait', data: { op: 'resolved', id: 'w1' } });
  const second = boot({ checks: [check('t', 'pass')] }, { entries: first.entries });
  await second.handlers.session_start({}, second.ctx);
  assert.deepEqual([...second.api.watches.keys()], ['w2']);
  assert.deepEqual(second.events.at(-1)[1].watches.map((w) => w.target), ['o/r#8']);
  await second.api.tick();
  assert.match(second.sent[0][0].content, /o\/r#8: green/);
  const res = await second.tool.execute('c3', { pr: 9 }, undefined, undefined, second.ctx);
  assert.match(res.content[0].text, /registered: w3 /);
});

test('busy agent gets a followUp delivery (and a rejected triggerTurn falls back)', async () => {
  const busy = boot({ checks: [check('t', 'pass')] }, { idle: false });
  await register(busy, { pr: 7 });
  await busy.api.tick();
  assert.deepEqual(busy.sent[0][1], { triggerTurn: true, deliverAs: 'followUp' });
  const throws = boot({ checks: [check('t', 'pass')] }, { sendThrows: true });
  await register(throws, { pr: 7 });
  await throws.api.tick();
  assert.deepEqual(throws.sent[0][1], { triggerTurn: true, deliverAs: 'followUp' });
});

test('/ci-wait cancel removes watches and re-registering a target replaces it', async () => {
  const b = boot({});
  await register(b, { pr: 7 });
  await b.tool.execute('c2', { pr: 7 }, undefined, undefined, b.ctx);
  assert.deepEqual([...b.api.watches.keys()], ['w2']);
  const notes = [];
  await b.command.handler('cancel all', { ui: { notify: (m) => notes.push(m) } });
  assert.equal(b.api.watches.size, 0);
  assert.match(notes[0], /cancelled w2/);
  assert.deepEqual(b.events.at(-1)[1], { active: false, watches: [] });
});


test('scheduled-only runs cannot establish branch or post-merge health', async () => {
  for (const target of [{ branch: 'master' }, { pr: 7, until: 'post-merge' }]) {
    const sha = 'e'.repeat(40);
    const state = {
      pr: { state: 'MERGED', mergeCommit: { oid: sha } },
      runs: [{ event: 'schedule', databaseId: 99, workflowName: 'Drift Watch',
        status: 'completed', conclusion: 'success', url: 'u99', headSha: sha }],
    };
    const b = boot(state);
    await register(b, target);
    await b.api.tick();
    assert.equal(b.sent.length, 0);
    assert.ok(b.gh.calls.some((a) => a[1] === 'list' && a.includes('--event') && a.includes('push')));
    b.advance(11 * 60_000);
    await b.api.tick();
    assert.equal(b.sent.length, 1);
    assert.match(b.sent[0][0].content, /no workflow runs/);
    assert.doesNotMatch(b.sent[0][0].content, /green/);
  }
});
