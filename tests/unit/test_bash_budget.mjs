import { test } from 'node:test';
import assert from 'node:assert/strict';
import bashBudget, {
  budgetTimeout, maxTimeout, GUIDELINES, waitReason, foregroundPart, blockMessage,
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
  assert.equal(GUIDELINES.length, 5);
  assert.ok(GUIDELINES.every((g) => !/900/.test(g)), 'the cap is not advertised (agents sized sleeps to it)');
  assert.ok(GUIDELINES.some((g) => /wait_for/.test(g) && /ci_wait/.test(g)));
  assert.match(prompt.systemPromptOptions.promptGuidelines[1], /SECONDS/);
});

// Real shapes from sessions 2026-11-02..05 (sleep-then-check, cap-sized sleeps, poll loops).
test('waitReason blocks waits held inside the tool call', () => {
  for (const cmd of [
    "sleep 280; gh pr view 5574 --json state,mergeCommit",
    "sleep 895; cd ~/x; timeout 60 gh pr checks 5723 --required 2>&1 | cut -f1,2",
    "cd /tmp/wt && git push -q && sleep 420; gh pr checks 6063 2>&1 | head -30",
    "date -u +%T; sleep 200; kubectl --context staging-ro -n global logs deploy/global --since=15m",
    "for i in $(seq 1 14); do sleep 60; out=$(gh pr checks 6116 2>&1); done",
    "for i in $(seq 1 60); do grep -q '^EXIT=' f.log && break; sleep 10; done; tail -15 f.log",
    "while ! curl -sf localhost:8080/health; do sleep 15; done",
    "sleep 20; gh pr ready 1 && sleep 5 && gh pr ready 1; sleep 15; gh run list",
    "sleep 5m && tail log",
    "sleep 1m 30s; tail log",
    "timeout 600 gh pr checks 108 --watch --interval 20 2>&1 | tail -12",
    "gh run watch 123 --exit-status",
    "timeout 900 bash -c 'until test -f done; do sleep 30; done'",
    "ssh host 'sleep 120; uptime'",
    "tmux send-keys -t %375 'make apply' Enter; sleep 100; tmux capture-pane -t %375 -p",
  ]) assert.ok(waitReason(cmd), cmd);
});

test('waitReason allows short settles, tight loops and detached work', () => {
  for (const cmd of [
    "ls -la",
    "sleep 2; curl -s localhost:8080/health",
    "make dev & sleep 8; curl -s localhost:3000",
    "timeout 120 bash -c 'until curl -sf localhost:8080; do sleep 2; done'",
    "tmux new-window -d -n sso \"aws sso login 2>&1 | tee /tmp/sso.log; sleep 3600\"; sleep 8; cat /tmp/sso.log",
    "tmux new-window -d -n tunnel '.agents/x.sh up 2>&1 | tee t.log; sleep 3600'",
    "nohup sh -c 'sleep 600; echo done' >/dev/null 2>&1 &",
    "(sleep 300; notify-send hi) &",
    "cat > run.sh <<'EOF'\nwhile true; do sleep 60; done\nEOF\nchmod +x run.sh",
    "python3 - <<'EOF'\nimport time; time.sleep(300)\nEOF",
    "rg -n 'sleep 280' sessions/ | head",
    "gh search issues 'sleep 270 cache' --repo x/y",
    "echo \"use sleep 300 to wait\"",
    "sleep \"$n\"; echo variable",
    "go test ./... 2>&1 | tee test.log",
  ]) assert.equal(waitReason(cmd), null, cmd);
});

test('foregroundPart keeps code run by bash -c, drops data strings', () => {
  assert.match(foregroundPart("bash -c 'sleep 40'"), /sleep 40/);
  assert.doesNotMatch(foregroundPart("grep 'sleep 40' f"), /sleep 40/);
});

test('tool_call blocks a long sleep with a pointer to ci_wait / wait_for', async () => {
  const saved = process.env.PI_BASH_ALLOW_SLEEP;
  delete process.env.PI_BASH_ALLOW_SLEEP;
  try {
    const { tool_call: onCall } = handlers();
    const res = await onCall({ toolName: 'bash', input: { command: 'sleep 280; gh pr checks 1', timeout: 300 } });
    assert.equal(res.block, true);
    assert.match(res.reason, /^Blocked by bash-budget: `sleep 280`/);
    assert.match(res.reason, /ci_wait/);
    assert.match(res.reason, /wait_for/);
    assert.equal(await onCall({ toolName: 'bash', input: { command: 'sleep 2; ls' } }), undefined);
    process.env.PI_BASH_ALLOW_SLEEP = '1';
    assert.equal(await onCall({ toolName: 'bash', input: { command: 'sleep 280' } }), undefined);
  } finally {
    if (saved === undefined) delete process.env.PI_BASH_ALLOW_SLEEP;
    else process.env.PI_BASH_ALLOW_SLEEP = saved;
  }
  assert.match(blockMessage('x'), /re-reads the whole context/);
});
