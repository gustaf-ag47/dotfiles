// Synthetic credential patterns only; no real secrets, network, or user config.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { DEFAULT_CONFIG } from '../../config/pi/lib/jev.mjs';
import { scoutFiles } from '../../config/pi/lib/jev-scout.mjs';

test('quoted JSON keys and standalone known token formats never reach classifier', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-secret-fixture-'));
  try {
    execFileSync('git', ['init', '-q', root]);
    const payloads = [
      JSON.stringify({ ['api' + '_key']: 'synthetic-placeholder-12345678' }),
      'apikey_' + 'a'.repeat(32) + '_' + 'b'.repeat(64),
      'xai-' + 'c'.repeat(32),
      'sk-ant-' + 'd'.repeat(32),
    ];
    fs.writeFileSync(path.join(root, 'sample.json'), payloads[0]);
    execFileSync('git', ['-C', root, 'add', 'sample.json']);
    let calls = 0;
    for (const content of payloads) {
      fs.writeFileSync(path.join(root, 'sample.json'), content);
      const result = await scoutFiles({
        cwd: root, goal: 'Find configuration parsing', paths: ['sample.json'], enabled: true,
        env: { HOME: root, TYPESAFE_API_KEY: 'test', PI_JEV_MODE: 'observe' },
        config: DEFAULT_CONFIG, stateDir: path.join(root, '.state'), cache: new Map(),
        classifyFn: async () => { calls++; throw new Error('must not execute'); },
      });
      assert.equal(result.skipped[0]?.reason, 'sensitive_content');
      assert.equal(result.stats.networkCalls, 0);
    }
    assert.equal(calls, 0);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
