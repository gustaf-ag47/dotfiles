import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import mergeBlockers from '../../config/pi/extensions/merge-blockers.ts';

function handler() {
  let callback;
  mergeBlockers({ on: (name, fn) => {
    assert.equal(name, 'before_agent_start');
    callback = fn;
  } });
  return callback;
}

function event() {
  return { systemPromptOptions: { promptGuidelines: ['existing rule'] } };
}

test('injects once for a checkout and a nested worktree directory', async (t) => {
  const root = mkdtempSync(join(tmpdir(), 'merge-blockers-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const checkout = join(root, 'checkout');
  const worktree = join(root, 'worktree');
  mkdirSync(join(checkout, '.git'), { recursive: true });
  mkdirSync(join(worktree, 'nested'), { recursive: true });
  writeFileSync(join(worktree, '.git'), 'gitdir: ../checkout/.git/worktrees/branch\n');
  const onStart = handler();
  for (const cwd of [checkout, join(worktree, 'nested')]) {
    const prompt = event();
    await onStart(prompt, { cwd });
    assert.equal(prompt.systemPromptOptions.promptGuidelines.length, 5);
    assert.match(prompt.systemPromptOptions.promptGuidelines[1], /gh pr checks/);
    await onStart(prompt, { cwd });
    assert.equal(prompt.systemPromptOptions.promptGuidelines.length, 5);
  }
});

test('does not inject outside a repository', async (t) => {
  const root = mkdtempSync(join(tmpdir(), 'merge-blockers-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const prompt = event();
  await handler()(prompt, { cwd: root });
  assert.deepEqual(prompt.systemPromptOptions.promptGuidelines, ['existing rule']);
});
