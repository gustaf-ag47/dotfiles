// Synthetic credential patterns only; no real secrets, network, or user config.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { DEFAULT_CONFIG } from '../../config/pi/lib/jev.mjs';
import { scoutFiles } from '../../config/pi/lib/jev-scout.mjs';

test('credential literals and binary data never reach classifier', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-secret-fixture-'));
  try {
    execFileSync('git', ['init', '-q', root]);
    const payloads = [
      [JSON.stringify({ ['api' + '_key']: 'synthetic-placeholder-12345678' }), 'sensitive_content'],
      ['apikey_' + 'a'.repeat(32) + '_' + 'b'.repeat(64), 'sensitive_content'],
      ['xai-' + 'c'.repeat(32), 'sensitive_content'],
      ['sk-ant-' + 'd'.repeat(32), 'sensitive_content'],
      [Buffer.concat([Buffer.alloc(9000, 65), Buffer.from([0])]), 'binary_file'],
      [Buffer.from([0xff, 0xfe, 0xfa]), 'binary_file'],
    ];
    fs.writeFileSync(path.join(root, 'sample.json'), payloads[0][0]);
    execFileSync('git', ['-C', root, 'add', 'sample.json']);
    let calls = 0;
    for (const [content, reason] of payloads) {
      fs.writeFileSync(path.join(root, 'sample.json'), content);
      const result = await scoutFiles({
        cwd: root, goal: 'Find configuration parsing', paths: ['sample.json'], enabled: true,
        env: { HOME: root, TYPESAFE_API_KEY: 'test', PI_JEV_MODE: 'observe' },
        config: DEFAULT_CONFIG, stateDir: path.join(root, '.state'), cache: new Map(),
        classifyFn: async () => { calls++; throw new Error('must not execute'); },
      });
      assert.equal(result.skipped[0]?.reason, reason);
      assert.equal(result.stats.networkCalls, 0);
    }
    assert.equal(calls, 0);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
