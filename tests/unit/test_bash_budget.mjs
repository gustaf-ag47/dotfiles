import { test } from 'node:test';
import assert from 'node:assert/strict';
import bashBudget, {
  budgetTimeout, maxTimeout, GUIDELINES,
} from '../../config/pi/extensions/bash-budget.ts';

function handlers() {
  const map = {};
  bashBudget({ on: (name, fn) => { map[name] = fn; } });
  return map;
}

test('budgetTimeout defaults, converts ms and clamps', () => {
  assert.equal(budgetTimeout(undefined, 900), 600);
  assert.equal(budgetTimeout(null, 900), 600);
  assert.equal(budgetTimeout('30', 900), 600);
  assert.equal(budgetTimeout(-5, 900), 600);
  assert.equal(budgetTimeout(Number.NaN, 900), 600);
  assert.equal(budgetTimeout(30, 900), 30);
  assert.equal(budgetTimeout(3600, 900), 900);
  assert.equal(budgetTimeout(120000, 900), 120);
  assert.equal(budgetTimeout(300000, 900), 300);
  assert.equal(budgetTimeout(9999, 900), 900);
});

test('custom cap', () => {
  assert.equal(budgetTimeout(1200, 1800), 1200);
  assert.equal(budgetTimeout(undefined, 300), 300);
});

test('PI_BASH_MAX_TIMEOUT overrides the cap', () => {
  assert.equal(maxTimeout({}), 900);
  assert.equal(maxTimeout({ PI_BASH_MAX_TIMEOUT: '1800' }), 1800);
  assert.equal(maxTimeout({ PI_BASH_MAX_TIMEOUT: 'junk' }), 900);
  assert.equal(maxTimeout({ PI_BASH_MAX_TIMEOUT: '0' }), 900);
  const saved = process.env.PI_BASH_MAX_TIMEOUT;
  process.env.PI_BASH_MAX_TIMEOUT = '1500';
  try {
    assert.equal(budgetTimeout(3600), 1500);
  } finally {
    if (saved === undefined) delete process.env.PI_BASH_MAX_TIMEOUT;
    else process.env.PI_BASH_MAX_TIMEOUT = saved;
  }
});

test('tool_call mutates bash input in place, leaves other tools alone', async () => {
  const saved = process.env.PI_BASH_MAX_TIMEOUT;
  delete process.env.PI_BASH_MAX_TIMEOUT;
  try {
    const { tool_call: onCall } = handlers();
    const bash = { toolName: 'bash', input: { command: 'ls', timeout: 3600 } };
    assert.equal(await onCall(bash), undefined);
    assert.deepEqual(bash.input, { command: 'ls', timeout: 900 });
    const bare = { toolName: 'bash', input: { command: 'ls' } };
    await onCall(bare);
    assert.equal(bare.input.timeout, 600);
    const other = { toolName: 'read', input: { path: 'x', timeout: 3600 } };
    await onCall(other);
    assert.deepEqual(other.input, { path: 'x', timeout: 3600 });
  } finally {
    if (saved !== undefined) process.env.PI_BASH_MAX_TIMEOUT = saved;
  }
});

test('guidelines injected once', async () => {
  const { before_agent_start: onStart } = handlers();
  const prompt = { systemPromptOptions: { promptGuidelines: ['existing rule'] } };
  await onStart(prompt, { cwd: '/' });
  await onStart(prompt, { cwd: '/' });
  assert.equal(prompt.systemPromptOptions.promptGuidelines.length, 1 + GUIDELINES.length);
  assert.equal(GUIDELINES.length, 4);
  assert.match(prompt.systemPromptOptions.promptGuidelines[1], /SECONDS/);
});
