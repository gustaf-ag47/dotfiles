// Regression test for the grok-build provider's read-only CLI session bridge
// resolver. This is the fix for a real bug caught in review: native Pi
// `Provider.auth.apiKey.resolve()` return values are used verbatim as the
// bearer token (@earendil-works/pi-ai's resolveApiKey() never interprets a
// leading "!"), so an earlier version of this code sent the literal string
// "!/path/to/script" as the Authorization bearer instead of executing the
// script. resolveGrokCliBridgeToken() must actually execute the script.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveGrokCliBridgeToken } from '../../config/pi/lib/grok-cli-bridge.mjs';

function makeScript(body) {
  const dir = mkdtempSync(join(tmpdir(), 'grok-cli-bridge-test-'));
  const script = join(dir, 'bridge');
  writeFileSync(script, `#!/bin/bash\n${body}\n`);
  chmodSync(script, 0o755);
  return script;
}

test('executes the bridge script and returns its stdout, not the path', () => {
  const script = makeScript('echo RECOGNIZABLE_FAKE_TOKEN_XYZ');
  const token = resolveGrokCliBridgeToken(script);
  assert.equal(token, 'RECOGNIZABLE_FAKE_TOKEN_XYZ');
  // The regression this guards against: an unresolved "!command" literal.
  assert.notEqual(token, `!${script}`);
  assert.ok(!token.startsWith('!'), 'token must not be the unresolved "!<path>" marker');
});

test('trims trailing whitespace/newlines from script output', () => {
  const script = makeScript('printf "TOKEN_WITH_TRAILING_NEWLINE\\n\\n"');
  assert.equal(resolveGrokCliBridgeToken(script), 'TOKEN_WITH_TRAILING_NEWLINE');
});

test('a failing script raises a short, non-secret error using its stderr', () => {
  const script = makeScript('echo "No Grok CLI OAuth session; run grok login --device-auth" >&2; exit 1');
  assert.throws(
    () => resolveGrokCliBridgeToken(script),
    /No Grok CLI OAuth session; run grok login --device-auth/,
  );
});

test('a missing script raises a clear, non-secret error instead of throwing a raw ENOENT', () => {
  const dir = mkdtempSync(join(tmpdir(), 'grok-cli-bridge-test-'));
  assert.throws(
    () => resolveGrokCliBridgeToken(join(dir, 'does-not-exist')),
    /Grok CLI session unavailable; run `grok login --device-auth`\./,
  );
});

test('an empty-output script raises a clear error rather than returning an empty bearer token', () => {
  const script = makeScript('true');
  assert.throws(() => resolveGrokCliBridgeToken(script), /returned no token/);
});

test('a script that leaks no secret on failure is not papered over with a generic error that would hide one', () => {
  const script = makeScript('exit 3');
  assert.throws(() => resolveGrokCliBridgeToken(script), /Grok CLI session unavailable/);
});
