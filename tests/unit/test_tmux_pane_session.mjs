import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import setup from '../../config/pi/extensions/tmux-pane-session.ts';

test('identity sidecar follows current session; legacy text path remains compatible after shutdown', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pane-publisher-'));
  const saved = { ...process.env };
  process.env.XDG_STATE_HOME = dir;
  process.env.TMUX_PANE = '%99';
  process.env.TMUX = '/test/socket,1,0';
  const events = {};
  let id = 'original', file = '/fixture/original.jsonl';
  const ctx = { sessionManager: { getSessionId: () => id, getSessionFile: () => file } };
  setup({ on: (event, fn) => { events[event] = fn; } });
  const base = path.join(dir, 'pi-panes', String(process.pid));
  try {
    await events.session_start({}, ctx);
    assert.equal(fs.readFileSync(base, 'utf8'), file + '\n');
    let sidecar = JSON.parse(fs.readFileSync(base + '.json'));
    assert.equal(sidecar.session_id, id);
    assert.equal(sidecar.pane, '%99');
    assert.equal(sidecar.socket, '/test/socket');
    assert.match(sidecar.start_ticks, /^\d+$/);
    assert.ok(sidecar.boot_id);
    await events.session_shutdown({}, ctx);
    assert.ok(!fs.existsSync(base + '.json'));
    assert.equal(fs.readFileSync(base, 'utf8'), file + '\n', 'tmux-resurrect still reads legacy text');
    id = 'replacement'; file = '/fixture/replacement.jsonl';
    await events.session_start({}, ctx);
    sidecar = JSON.parse(fs.readFileSync(base + '.json'));
    assert.equal(sidecar.session_id, 'replacement');
    assert.equal(fs.readFileSync(base, 'utf8'), file + '\n');
    file = undefined;
    await events.session_start({}, ctx);
    assert.ok(!fs.existsSync(base + '.json'));
    assert.ok(!fs.existsSync(base));
  } finally {
    await events.session_shutdown({}, ctx);
    for (const key of ['XDG_STATE_HOME', 'TMUX_PANE', 'TMUX']) {
      if (saved[key] === undefined) delete process.env[key]; else process.env[key] = saved[key];
    }
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
