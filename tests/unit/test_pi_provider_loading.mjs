import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
let loader;
try {
  const dependency = execFileSync('python3', ['-c',
    'from scripts.pi_setup import pi_ai_path; print(pi_ai_path("pi"))'],
    { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  loader = path.join(path.dirname(dependency), 'pi-coding-agent/dist/core/extensions/loader.js');
} catch {
  // CI without a Pi installation still runs the dependency-discovery fixtures.
}

for (const resource of ['config/pi/extensions/grok-build.ts', 'config/pi/lib/anthropic-subscription.ts']) {
  test(`${resource} loads through the installed Pi extension loader`, {
    skip: !loader || !existsSync(loader) ? 'Pi installation unavailable' : false,
  }, async () => {
    // Only instantiate the extension factory: no credential store, sessions,
    // model refresh, OAuth, or inference. A fake TS loader would miss Pi's
    // root alias shadowing individual provider subpath imports.
    const { loadExtensions } = await import(pathToFileURL(loader).href);
    const result = await loadExtensions([path.join(root, resource)], root);
    assert.deepEqual(result.errors, []);
    assert.equal(result.extensions.length, 1);
  });
}
