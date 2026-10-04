// delegate-mailbox.ts: the only in-band path that closes delegation loops.
// Contract under test: a record whose `parent:` matches $TMUX_PANE is delivered
// exactly once and moved to ack/; other panes' records are left alone; a
// malformed/unreadable record never throws; shutdown closes the watcher.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

const MAILBOX = fs.mkdtempSync(path.join(os.tmpdir(), 'delegate-mailbox-'));
process.env.PI_DELEGATE_MAILBOX = MAILBOX; // must be set before the module loads
process.env.TMUX_PANE = '%99';
const { default: delegateMailbox } = await import('../../config/pi/extensions/delegate-mailbox.ts');

function boot() {
  const sent = [];
  const handlers = {};
  delegateMailbox({
    sendMessage: (message, opts) => sent.push([message, opts]),
    on: (name, fn) => { handlers[name] = fn; },
  });
  return { sent, handlers };
}

const record = (pane, name, body = 'child finished') =>
  fs.writeFileSync(path.join(MAILBOX, name), `# record\n- parent: \`${pane}\`\n\n${body}\n`);

test('matching record is delivered once, with triggerTurn, and acked', async () => {
  const { sent, handlers } = boot();
  record('%99', 'a-match.md');
  record('%42', 'b-other-pane.md');
  await handlers.session_start({}, { hasUI: false });
  try {
    assert.equal(sent.length, 1);
    const [message, opts] = sent[0];
    assert.equal(message.customType, 'delegate-mailbox');
    assert.match(message.content, /child finished/);
    assert.equal(opts.triggerTurn, true);
    // acked: moved out of the mailbox root into ack/
    assert.ok(!fs.existsSync(path.join(MAILBOX, 'a-match.md')));
    assert.ok(fs.existsSync(path.join(MAILBOX, 'ack', 'a-match.md')));
    // the other pane's record is untouched
    assert.ok(fs.existsSync(path.join(MAILBOX, 'b-other-pane.md')));
  } finally {
    await handlers.session_shutdown({}, {});
    fs.rmSync(path.join(MAILBOX, 'b-other-pane.md'));
  }
});

test('malformed and unreadable records do not throw and are not acked', async () => {
  const { sent, handlers } = boot();
  fs.writeFileSync(path.join(MAILBOX, 'malformed.md'), 'no parent line at all');
  fs.mkdirSync(path.join(MAILBOX, 'a-directory.md')); // readFileSync throws EISDIR
  await handlers.session_start({}, { hasUI: false });
  try {
    assert.equal(sent.length, 0);
    assert.ok(fs.existsSync(path.join(MAILBOX, 'malformed.md')));
  } finally {
    await handlers.session_shutdown({}, {});
    fs.rmSync(path.join(MAILBOX, 'malformed.md'));
    fs.rmdirSync(path.join(MAILBOX, 'a-directory.md'));
  }
});

test('failed sendMessage leaves the record unacked for the keystroke fallback', async () => {
  const handlers = {};
  delegateMailbox({
    sendMessage: () => { throw new Error('mid-stream'); },
    on: (name, fn) => { handlers[name] = fn; },
  });
  record('%99', 'c-fails.md');
  await handlers.session_start({}, { hasUI: false });
  try {
    assert.ok(fs.existsSync(path.join(MAILBOX, 'c-fails.md')), 'record must survive for re-nudges');
  } finally {
    await handlers.session_shutdown({}, {});
    fs.rmSync(path.join(MAILBOX, 'c-fails.md'));
  }
});

test('no TMUX_PANE: session_start is inert (no watcher, nothing delivered)', async () => {
  const savedPane = process.env.TMUX_PANE;
  delete process.env.TMUX_PANE;
  try {
    const { sent, handlers } = boot();
    record('%99', 'd-while-paneless.md');
    await handlers.session_start({}, { hasUI: false });
    assert.equal(sent.length, 0);
    assert.ok(fs.existsSync(path.join(MAILBOX, 'd-while-paneless.md')));
    await handlers.session_shutdown({}, {});
  } finally {
    process.env.TMUX_PANE = savedPane;
    fs.rmSync(path.join(MAILBOX, 'd-while-paneless.md'));
  }
});
