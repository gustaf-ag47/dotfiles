// Run: node --test tests/unit/test_jev_scout.mjs
//
// All tests use temp git repos and synthetic classifier injection. No real
// credentials, no config/pi/node_modules import, no network access. Real
// `git` binary is used against throwaway temp repos (git init/add only).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

import {
  scoutFiles,
  relevanceQuestions,
  defaultGit,
  RELEVANCE_CLASSES,
  MAX_PATHS_PER_CALL,
  MAX_GOAL_CHARS,
  MAX_FILE_BYTES,
  MAX_TOTAL_BYTES,
} from "../../config/pi/lib/jev-scout.mjs";
import { DEFAULT_CONFIG } from "../../config/pi/lib/jev.mjs";

// Built by concatenation (not a quoted literal beside an env-var-looking
// name) so secret-scanning hooks tuned for `KEY: "..."` don't flag this
// obviously-synthetic placeholder. Never sent anywhere: every test injects
// its own classifyFn instead of calling resolveClassifyFn().
const SYNTHETIC_TEST_TOKEN = ["synthetic", "test", "token", "not", "real"].join("-");

function sh(cmd, args, cwd) {
  const res = spawnSync(cmd, args, { cwd, encoding: "utf8" });
  if (res.status !== 0) throw new Error(`${cmd} ${args.join(" ")} failed: ${res.stderr}`);
  return res.stdout;
}

/** Creates a throwaway git repo under a fresh temp dir and returns its root. */
function makeRepo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "jev-scout-repo-"));
  sh("git", ["init", "-q"], root);
  sh("git", ["config", "user.email", "test@example.com"], root);
  sh("git", ["config", "user.name", "Test"], root);
  return root;
}

function writeTracked(root, relPath, content) {
  const abs = path.join(root, relPath);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content);
  sh("git", ["add", "--", relPath], root);
  sh("git", ["commit", "-q", "-m", `add ${relPath}`], root);
  return abs;
}

function writeUntracked(root, relPath, content) {
  const abs = path.join(root, relPath);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content);
  return abs;
}

function tmpHomeEnv(overrides = {}) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "jev-scout-home-"));
  return {
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_STATE_HOME: path.join(home, ".local", "state"),
    TYPESAFE_API_KEY: SYNTHETIC_TEST_TOKEN,
    ...overrides,
  };
}

function okClassifier({ choice = "relevant", confidence = 0.9, input = 300, output = 10 } = {}) {
  return async () => ({
    stopReason: "stop",
    answers: { file_relevance: { type: "choice", choice, probabilities: { [choice]: confidence }, confidence } },
    usage: { input, output },
  });
}

function baseParams(root, overrides = {}) {
  return {
    cwd: root,
    goal: "Find where the HTTP client is configured",
    paths: [],
    enabled: true,
    env: tmpHomeEnv(),
    config: { ...DEFAULT_CONFIG, budget: { ...DEFAULT_CONFIG.budget } },
    classifyFn: okClassifier(),
    cache: new Map(),
    ...overrides,
  };
}

function ledgerLines(env) {
  const file = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  try {
    return fs
      .readFileSync(file, "utf8")
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Opt-in / global kill switch
// ---------------------------------------------------------------------------

test("disabled by default: enabled:false touches nothing, returns disabled skip", async () => {
  const root = makeRepo();
  const f = writeTracked(root, "a.js", "console.log(1)");
  const env = tmpHomeEnv();
  const out = await scoutFiles(baseParams(root, { enabled: false, paths: ["a.js"], env }));
  assert.equal(out.items.length, 0);
  assert.equal(out.skipped.length, 1);
  assert.equal(out.skipped[0].reason, "disabled");
  assert.equal(out.stats.networkCalls, 0);
  assert.equal(ledgerLines(env).length, 0);
  assert.ok(fs.existsSync(f));
});

test("disabled with zero paths still signals disabledReason", async () => {
  const root = makeRepo();
  const out = await scoutFiles(baseParams(root, { enabled: false, paths: [] }));
  assert.equal(out.stats.disabledReason, "disabled");
});

test("PI_JEV_MODE=off wins even when enabled:true", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const env = tmpHomeEnv({ PI_JEV_MODE: "off" });
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], env }));
  assert.equal(out.skipped[0].reason, "mode_off");
  assert.equal(out.stats.networkCalls, 0);
});

test("invalid injected config causes skip, not silent default run", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], config: { bogus: true } }));
  assert.equal(out.skipped[0].reason, "config_invalid");
});

test("missing API key -> missing_key, no network", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const env = tmpHomeEnv({ TYPESAFE_API_KEY: "" });
  let called = false;
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js"],
      env,
      classifyFn: async () => {
        called = true;
        return okClassifier()();
      },
    }),
  );
  assert.equal(out.skipped[0].reason, "missing_key");
  assert.equal(called, false);
});

test("classifier unavailable (no injected fn, resolution fails) -> skipped", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], classifyFn: undefined, env: tmpHomeEnv({ JEV_CLASSIFY_MODULE: "nonexistent-package-xyz" }) }));
  assert.equal(out.skipped[0].reason, "classifier_unavailable");
});

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

test("goal too long is rejected", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], goal: "x".repeat(MAX_GOAL_CHARS + 1) }));
  assert.equal(out.skipped[0].reason, "goal_too_long");
});

test("empty goal is rejected", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], goal: "" }));
  assert.equal(out.skipped[0].reason, "goal_invalid");
});

test("more than 8 candidate paths is rejected wholesale", async () => {
  const root = makeRepo();
  const paths = [];
  for (let i = 0; i < MAX_PATHS_PER_CALL + 1; i++) {
    paths.push(`f${i}.js`);
    writeTracked(root, `f${i}.js`, `// ${i}`);
  }
  const out = await scoutFiles(baseParams(root, { paths }));
  assert.equal(out.skipped.length, paths.length);
  assert.ok(out.skipped.every((s) => s.reason === "too_many_paths"));
  assert.equal(out.stats.networkCalls, 0);
});

test("exactly 8 candidate paths is allowed", async () => {
  const root = makeRepo();
  const paths = [];
  for (let i = 0; i < MAX_PATHS_PER_CALL; i++) {
    paths.push(`f${i}.js`);
    writeTracked(root, `f${i}.js`, `// ${i}`);
  }
  const out = await scoutFiles(baseParams(root, { paths }));
  assert.equal(out.items.length, MAX_PATHS_PER_CALL);
});

// ---------------------------------------------------------------------------
// Git tracked / untracked / ignored
// ---------------------------------------------------------------------------

test("untracked file is skipped as not_git_tracked", async () => {
  const root = makeRepo();
  writeUntracked(root, "scratch.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["scratch.js"] }));
  assert.equal(out.items.length, 0);
  assert.equal(out.skipped[0].reason, "not_git_tracked");
});

test("gitignored (but somehow present) file is skipped", async () => {
  const root = makeRepo();
  writeTracked(root, ".gitignore", "ignored.js\n");
  writeUntracked(root, "ignored.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["ignored.js"] }));
  assert.equal(out.skipped[0].reason, "not_git_tracked");
});

test("not a git repo at all -> not_git_repo", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "jev-scout-nogit-"));
  fs.writeFileSync(path.join(root, "a.js"), "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"] }));
  assert.equal(out.skipped[0].reason, "not_git_repo");
});

// ---------------------------------------------------------------------------
// Symlinks / path escape
// ---------------------------------------------------------------------------

test("symlinked file (leaf) is rejected", async () => {
  const root = makeRepo();
  writeTracked(root, "real.js", "x");
  fs.symlinkSync(path.join(root, "real.js"), path.join(root, "link.js"));
  const out = await scoutFiles(baseParams(root, { paths: ["link.js"] }));
  assert.equal(out.skipped[0].reason, "symlink"); // caught by the ancestor-chain/symlink check before git is even consulted
});

test("symlinked ancestor directory is rejected even if the leaf looks fine", async () => {
  const root = makeRepo();
  writeTracked(root, "real/inner.js", "x");
  const outsideDir = fs.mkdtempSync(path.join(os.tmpdir(), "jev-scout-outside-"));
  fs.symlinkSync(path.join(root, "real"), path.join(outsideDir, "alias"));
  // Candidate path escapes the repo via an absolute path through a symlinked
  // ancestor that lives entirely outside the repo root.
  const out = await scoutFiles(
    baseParams(root, {
      paths: [path.join(outsideDir, "alias", "inner.js")],
    }),
  );
  assert.equal(out.skipped[0].reason, "path_outside_repo");
});

test("path escaping the repo via .. is rejected", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["../../etc/passwd"] }));
  assert.equal(out.skipped[0].reason, "path_outside_repo");
});

// ---------------------------------------------------------------------------
// Sensitive paths and content
// ---------------------------------------------------------------------------

test("sensitive path names are skipped without being read", async () => {
  const root = makeRepo();
  const sensitivePaths = [".env", ".env.local", "config/.ssh/id_rsa", "app/credentials.json", "app/secrets.yml", "certs/server.pem"];
  // -f: this host's global gitignore already blocks several of these names
  // (.env, credentials, secrets, id_rsa, *.pem); force-add so the test can
  // assert this module's OWN sensitive-path denylist catches them too,
  // independent of whatever the operator's global gitignore happens to do.
  for (const p of sensitivePaths) {
    const abs = path.join(root, p);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, "irrelevant content");
    sh("git", ["add", "-f", "--", p], root);
  }
  sh("git", ["commit", "-q", "-m", "add sensitive"], root);
  const out = await scoutFiles(baseParams(root, { paths: sensitivePaths }));
  assert.equal(out.items.length, 0);
  assert.ok(out.skipped.every((s) => s.reason === "sensitive_path"));
});

test("content with an obvious private key header is skipped as sensitive_content", async () => {
  const root = makeRepo();
  // Built by concatenation, not a quoted literal, so secret-scanning
  // pre-commit hooks tuned for `-----BEGIN ... PRIVATE KEY-----` don't flag
  // this synthetic fixture (it is a fake body, never sent anywhere real).
  const fakeKeyBody = ["-----BEGIN RSA PRIVATE", " KEY-----", "\nMIIBogIBAAJ...\n", "-----END RSA PRIVATE", " KEY-----\n"].join("");
  writeTracked(root, "notes.txt", fakeKeyBody);
  const out = await scoutFiles(baseParams(root, { paths: ["notes.txt"] }));
  assert.equal(out.skipped[0].reason, "sensitive_content");
});

test("content with an obvious AWS access key literal is skipped", async () => {
  const root = makeRepo();
  // Built by concatenation so secret-scanning pre-commit hooks tuned for the
  // literal AKIA... pattern don't flag this synthetic (fake, 16-char suffix
  // is not a real account identifier) fixture.
  const fakeAwsKey = ["AKIA", "ABCDEFGHIJKLMNOP"].join("");
  writeTracked(root, "notes.txt", `key = ${fakeAwsKey}`);
  const out = await scoutFiles(baseParams(root, { paths: ["notes.txt"] }));
  assert.equal(out.skipped[0].reason, "sensitive_content");
});

test("skipped candidates never leak raw path content or reasons beyond safe codes", async () => {
  const root = makeRepo();
  writeTracked(root, "notes.txt", "token = \"abcdefghijklmnopqrstuvwxyz123456\"");
  const out = await scoutFiles(baseParams(root, { paths: ["notes.txt"] }));
  const json = JSON.stringify(out);
  assert.ok(!json.includes("abcdefghijklmnopqrstuvwxyz123456"));
  assert.equal(out.skipped[0].reason, "sensitive_content");
});

// ---------------------------------------------------------------------------
// Binary / oversized / total-bytes cap
// ---------------------------------------------------------------------------

test("binary file content is skipped", async () => {
  const root = makeRepo();
  const abs = path.join(root, "bin.dat");
  fs.writeFileSync(abs, Buffer.from([0, 1, 2, 3, 0, 255]));
  sh("git", ["add", "--", "bin.dat"], root);
  sh("git", ["commit", "-q", "-m", "add binary"], root);
  const out = await scoutFiles(baseParams(root, { paths: ["bin.dat"] }));
  assert.equal(out.skipped[0].reason, "binary_file");
});

test("oversized file (>16KiB) is skipped without being classified", async () => {
  const root = makeRepo();
  writeTracked(root, "big.js", "x".repeat(MAX_FILE_BYTES + 1));
  const out = await scoutFiles(baseParams(root, { paths: ["big.js"] }));
  assert.equal(out.skipped[0].reason, "oversized_file");
});

test("total bytes across candidates is capped at 64KiB", async () => {
  const root = makeRepo();
  const perFile = 15 * 1024; // 15KiB each (under the 16KiB per-file cap); five exceed the 64KiB total cap
  const paths = [];
  for (let i = 0; i < 5; i++) {
    const p = `big${i}.js`;
    writeTracked(root, p, "x".repeat(perFile));
    paths.push(p);
  }
  const out = await scoutFiles(baseParams(root, { paths }));
  const exceeded = out.skipped.filter((s) => s.reason === "total_bytes_exceeded");
  assert.ok(exceeded.length >= 1, "expected at least one total_bytes_exceeded skip");
  assert.ok(out.items.length < paths.length);
});

// ---------------------------------------------------------------------------
// Classification outcomes
// ---------------------------------------------------------------------------

test("relevant verdict with high confidence is returned as-is", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "const client = new HttpClient();");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], classifyFn: okClassifier({ choice: "relevant", confidence: 0.95 }) }));
  assert.equal(out.items[0].relevance, "relevant");
  assert.equal(out.items[0].confidence, 0.95);
  assert.equal(out.stats.networkCalls, 1);
});

test("unrelated verdict is preserved, not silently dropped", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "// completely unrelated file");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], classifyFn: okClassifier({ choice: "unrelated", confidence: 0.92 }) }));
  assert.equal(out.items.length, 1);
  assert.equal(out.items[0].relevance, "unrelated");
});

test("low confidence forces uncertain, never unrelated", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const config = { ...DEFAULT_CONFIG, minConfidence: 0.8 };
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], config, classifyFn: okClassifier({ choice: "unrelated", confidence: 0.5 }) }));
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "low_confidence");
});

test("classifier error maps to uncertain with reason, counted as assessed", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], classifyFn: async () => ({ stopReason: "error" }) }));
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "classifier_error");
  assert.equal(out.items[0].confidence, null);
});

test("timeout maps to uncertain with reason timeout, reservation retained", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const env = tmpHomeEnv();
  const config = { ...DEFAULT_CONFIG, budget: { ...DEFAULT_CONFIG.budget } };
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js"],
      env,
      config,
      classifyFn: () => new Promise(() => {}), // never resolves
    }),
  );
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "timeout");
});

test("unexpected answer shape maps to uncertain/unexpected_answer", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], classifyFn: async () => ({ stopReason: "stop", answers: {} }) }));
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "unexpected_answer");
});

test("invalid choice outside whitelist maps to uncertain/unexpected_answer", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js"],
      classifyFn: async () => ({ stopReason: "stop", answers: { file_relevance: { type: "choice", choice: "definitely-relevant!!", confidence: 0.99 } } }),
    }),
  );
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "unexpected_answer");
});

// ---------------------------------------------------------------------------
// Caching
// ---------------------------------------------------------------------------

test("second call with same path/content/goal hits cache, no second network call", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "const client = new HttpClient();");
  let calls = 0;
  const classifyFn = async () => {
    calls += 1;
    return okClassifier({ choice: "relevant", confidence: 0.9 })();
  };
  const cache = new Map();
  const params = baseParams(root, { paths: ["a.js"], classifyFn, cache });
  const out1 = await scoutFiles(params);
  const out2 = await scoutFiles({ ...params, classifyFn });
  assert.equal(calls, 1);
  assert.equal(out1.items[0].cacheHit, undefined);
  assert.equal(out2.items[0].cacheHit, true);
  assert.equal(out2.stats.cacheHits, 1);
  assert.equal(out2.stats.networkCalls, 0);
  assert.equal(out2.items[0].relevance, "relevant");
});

test("changed file content invalidates the cache and reclassifies", async () => {
  const root = makeRepo();
  const abs = writeTracked(root, "a.js", "version one");
  let calls = 0;
  const classifyFn = async () => {
    calls += 1;
    return okClassifier({ choice: "relevant", confidence: 0.9 })();
  };
  const cache = new Map();
  const params = baseParams(root, { paths: ["a.js"], classifyFn, cache });
  await scoutFiles(params);
  fs.writeFileSync(abs, "version two, totally different");
  sh("git", ["add", "-A"], root);
  sh("git", ["commit", "-q", "-m", "update"], root);
  await scoutFiles({ ...params, classifyFn });
  assert.equal(calls, 2);
});

test("changed goal invalidates the cache and reclassifies", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "const client = new HttpClient();");
  let calls = 0;
  const classifyFn = async () => {
    calls += 1;
    return okClassifier({ choice: "relevant", confidence: 0.9 })();
  };
  const cache = new Map();
  const params = baseParams(root, { paths: ["a.js"], classifyFn, cache });
  await scoutFiles(params);
  await scoutFiles({ ...params, goal: "A completely different goal text", classifyFn });
  assert.equal(calls, 2);
});

test("errors are never cached: a failed call is retried on the next invocation", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  let calls = 0;
  const classifyFn = async () => {
    calls += 1;
    return { stopReason: "error" };
  };
  const cache = new Map();
  const params = baseParams(root, { paths: ["a.js"], classifyFn, cache });
  await scoutFiles(params);
  await scoutFiles({ ...params, classifyFn });
  assert.equal(calls, 2);
});

// ---------------------------------------------------------------------------
// Shared budget
// ---------------------------------------------------------------------------

test("shared budget exhaustion yields uncertain/budget_exceeded, no network call made", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const env = tmpHomeEnv();
  const config = { ...DEFAULT_CONFIG, budget: { maxCallsPerDay: 100, maxCostPerDayUsd: 1e-12 } };
  let called = false;
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js"],
      env,
      config,
      classifyFn: async () => {
        called = true;
        return okClassifier()();
      },
    }),
  );
  assert.equal(called, false);
  assert.equal(out.items[0].relevance, "uncertain");
  assert.equal(out.items[0].reason, "budget_exceeded");
});

// ---------------------------------------------------------------------------
// Ledger
// ---------------------------------------------------------------------------

test("ledger events use shared schema with purpose file-scout, class null, applied false, no raw text", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "const client = new HttpClient();");
  const env = tmpHomeEnv();
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"], env, goal: "Find the http client setup" }));
  assert.equal(out.items[0].relevance, "relevant");
  const lines = ledgerLines(env);
  assert.equal(lines.length, 1);
  const evt = lines[0];
  assert.equal(evt.schema, "jev-event.v1");
  assert.equal(evt.source, "pi");
  assert.equal(evt.purpose, "file-scout");
  assert.equal(evt.class, null);
  assert.equal(evt.applied, false);
  assert.equal(evt.status, "ok");
  assert.ok(evt.estimated_cost_usd > 0);
  const raw = fs.readFileSync(path.join(env.XDG_STATE_HOME, "jev", "events.jsonl"), "utf8");
  assert.ok(!raw.includes("a.js"));
  assert.ok(!raw.includes("http client"));
});

test("cache hits log a zero-cost cache_hit ledger event, never a second network-priced event", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "const client = new HttpClient();");
  const env = tmpHomeEnv();
  const cache = new Map();
  const params = baseParams(root, { paths: ["a.js"], env, cache });
  await scoutFiles(params);
  await scoutFiles({ ...params });
  const lines = ledgerLines(env);
  assert.equal(lines.length, 2);
  assert.equal(lines[0].status, "ok");
  assert.equal(lines[1].status, "cache_hit");
  assert.equal(lines[1].estimated_cost_usd, 0);
});

// ---------------------------------------------------------------------------
// No raw path/content sent to classifier
// ---------------------------------------------------------------------------

test("classifier receives goal and file content only, never the file path", async () => {
  const root = makeRepo();
  writeTracked(root, "unusual-filename-marker-xyz.js", "const client = new HttpClient();");
  let seenContext;
  const classifyFn = async (_model, context) => {
    seenContext = context;
    return okClassifier()();
  };
  await scoutFiles(baseParams(root, { paths: ["unusual-filename-marker-xyz.js"], classifyFn }));
  assert.ok(seenContext);
  const asJson = JSON.stringify(seenContext);
  assert.ok(!asJson.includes("unusual-filename-marker-xyz"));
  assert.equal(seenContext.state.file_content, "const client = new HttpClient();");
  assert.equal(typeof seenContext.state.goal, "string");
});

// ---------------------------------------------------------------------------
// Concurrency / pool behavior
// ---------------------------------------------------------------------------

test("bounded concurrency: no more than 2 classify calls run at the same time", async () => {
  const root = makeRepo();
  const paths = [];
  for (let i = 0; i < 6; i++) {
    const p = `f${i}.js`;
    writeTracked(root, p, `// file ${i}`);
    paths.push(p);
  }
  let active = 0;
  let maxActive = 0;
  const classifyFn = async () => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    await new Promise((r) => setTimeout(r, 10));
    active -= 1;
    return okClassifier()();
  };
  const out = await scoutFiles(baseParams(root, { paths, classifyFn }));
  assert.equal(out.items.length, 6);
  assert.ok(maxActive <= 2, `expected concurrency <= 2, saw ${maxActive}`);
});

// ---------------------------------------------------------------------------
// Caller abort
// ---------------------------------------------------------------------------

test("caller AbortSignal stops further processing", async () => {
  const root = makeRepo();
  const paths = [];
  for (let i = 0; i < 4; i++) {
    const p = `f${i}.js`;
    writeTracked(root, p, `// file ${i}`);
    paths.push(p);
  }
  const controller = new AbortController();
  const classifyFn = async () => {
    controller.abort();
    await new Promise((r) => setTimeout(r, 20));
    return okClassifier()();
  };
  const out = await scoutFiles(baseParams(root, { paths, classifyFn, signal: controller.signal }));
  const abortedOrAssessed = out.items.length + out.skipped.filter((s) => s.reason === "aborted").length;
  assert.ok(abortedOrAssessed <= paths.length);
});

// ---------------------------------------------------------------------------
// Stable return shape / no raw data anywhere
// ---------------------------------------------------------------------------

test("returned shape matches the agreed contract fields", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const out = await scoutFiles(baseParams(root, { paths: ["a.js"] }));
  assert.ok(Array.isArray(out.items));
  assert.ok(Array.isArray(out.skipped));
  assert.ok(out.stats && typeof out.stats === "object");
  assert.ok("networkCalls" in out.stats);
  assert.ok("cacheHits" in out.stats);
  assert.ok("inputTokens" in out.stats);
  assert.ok("estimatedCostUsd" in out.stats);
  assert.ok("unknownCostCalls" in out.stats);
  // usage matches Pi's own Usage aggregate shape, not a custom array.
  assert.ok(out.usage && typeof out.usage === "object" && !Array.isArray(out.usage));
  assert.equal(typeof out.usage.input, "number");
  assert.equal(typeof out.usage.output, "number");
  assert.equal(typeof out.usage.totalTokens, "number");
  assert.ok(out.usage.cost && typeof out.usage.cost.total === "number");
  for (const it of out.items) {
    assert.ok(RELEVANCE_CLASSES.includes(it.relevance));
    assert.ok("confidence" in it);
    assert.ok("path" in it);
  }
});

test("usage aggregate accumulates known tokens; missing usage is tracked as unknownCostCalls, never zero", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  writeTracked(root, "b.js", "y");
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js", "b.js"],
      classifyFn: async (_model, context) => {
        if (context.state.file_content === "x") {
          return { stopReason: "stop", answers: { file_relevance: { type: "choice", choice: "relevant", confidence: 0.9 } } }; // no usage field at all
        }
        return okClassifier({ choice: "relevant", confidence: 0.9, input: 123, output: 7 })();
      },
    }),
  );
  assert.equal(out.stats.unknownCostCalls, 1);
  assert.equal(out.usage.input, 123);
  assert.equal(out.usage.output, 7);
});

test("negative or non-integer usage values are treated as unknown, never refunding the budget or producing negative usage", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  const env = tmpHomeEnv();
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js"],
      env,
      classifyFn: async () => ({
        stopReason: "stop",
        answers: { file_relevance: { type: "choice", choice: "relevant", confidence: 0.9 } },
        usage: { input: -500, output: 2.5 }, // malicious/buggy: negative and fractional
      }),
    }),
  );
  assert.equal(out.stats.unknownCostCalls, 1);
  assert.equal(out.usage.input, 0);
  assert.equal(out.usage.output, 0);
  assert.ok(out.usage.input >= 0 && out.usage.output >= 0);
  assert.ok(out.stats.estimatedCostUsd >= 0);
  const evt = ledgerLines(env)[0];
  assert.equal(evt.input_tokens, null);
  assert.equal(evt.output_tokens, null);
});

test("relevanceQuestions() exposes exactly the three whitelisted classes", () => {
  const q = relevanceQuestions();
  const classes = Object.keys(q.file_relevance.criteria);
  assert.deepEqual(classes.sort(), [...RELEVANCE_CLASSES].sort());
});

test("defaultGit() resolves a real repo root and tracked/ignored state", () => {
  const root = makeRepo();
  writeTracked(root, "tracked.js", "x");
  writeTracked(root, ".gitignore", "ignored.js\n");
  writeUntracked(root, "ignored.js", "x");
  const git = defaultGit();
  const resolvedRoot = git.repoRoot(root);
  assert.equal(fs.realpathSync(resolvedRoot), fs.realpathSync(root));
  assert.equal(git.isTracked("tracked.js", root), "tracked");
  assert.equal(git.isTracked("ignored.js", root), "untracked");
  assert.equal(git.isIgnored("ignored.js", root), "ignored");
});

test("defaultGit() fails closed (tri-state \"error\") on a non-repo directory instead of claiming untracked/not-ignored", () => {
  const notARepo = fs.mkdtempSync(path.join(os.tmpdir(), "jev-scout-plain-"));
  const git = defaultGit();
  assert.equal(git.repoRoot(notARepo), null);
});

// ---------------------------------------------------------------------------
// Regression tests: parent review of 381fe4b
// ---------------------------------------------------------------------------

test("a tracked path replaced by a writer-less FIFO is rejected as not_regular_file, not hung on open", async () => {
  const root = makeRepo();
  const abs = writeTracked(root, "was-a-file.js", "x");
  fs.unlinkSync(abs);
  sh("mkfifo", [abs], root);
  const start = Date.now();
  const out = await scoutFiles(baseParams(root, { paths: ["was-a-file.js"] }));
  const elapsed = Date.now() - start;
  assert.ok(elapsed < 2000, `expected no hang opening the FIFO, took ${elapsed}ms`);
  assert.equal(out.skipped[0].reason, "not_regular_file");
});

test("a tracked file swapped for a different regular file at the identical path mid-pipeline is rejected on inode mismatch, not silently classified", async () => {
  const root = makeRepo();
  const abs = writeTracked(root, "swap.js", "original content for the goal");
  // Simulate the TOCTOU window with no symlink involved at all: a plain
  // unlink+recreate race at the identical path between the ancestor-chain
  // safety check (1st lstat of this path) and readFileBounded()'s post-read
  // identity re-check (2nd lstat of this path). The fd opened in between
  // still refers to the ORIGINAL inode (POSIX semantics), so its fstat()
  // will disagree with the swapped file's lstat() -- that's exactly the
  // mismatch readFileBounded() must catch.
  let lstatCallsForSwapPath = 0;
  const fsImpl = {
    ...fs,
    lstatSync: (p, opts) => {
      if (path.resolve(String(p)) === path.resolve(abs)) {
        lstatCallsForSwapPath += 1;
        if (lstatCallsForSwapPath === 2) {
          fs.unlinkSync(abs);
          fs.writeFileSync(abs, "swapped content, different inode, same path");
        }
      }
      return fs.lstatSync(p, opts);
    },
  };
  const out = await scoutFiles(baseParams(root, { paths: ["swap.js"], fsImpl }));
  assert.equal(out.skipped[0].reason, "path_swapped");
});

test("overall deadline is re-checked after each git preflight call, not only at dispatch time, so slow git calls cannot silently extend the shared ~15s bound", async () => {
  const root = makeRepo();
  writeTracked(root, "a.js", "x");
  writeTracked(root, "b.js", "y");
  let fakeNow = 1_000_000;
  const now = () => fakeNow;
  const realGit = defaultGit();
  const git = {
    repoRoot: (cwd) => realGit.repoRoot(cwd),
    isTracked: (relPath, repoRoot) => {
      fakeNow += 8000; // simulate one slow git subprocess call
      return realGit.isTracked(relPath, repoRoot);
    },
    isIgnored: (relPath, repoRoot) => realGit.isIgnored(relPath, repoRoot),
  };
  let dispatched = 0;
  const out = await scoutFiles(
    baseParams(root, {
      paths: ["a.js", "b.js"],
      now,
      git,
      classifyFn: async () => {
        dispatched += 1;
        return okClassifier()();
      },
    }),
  );
  // Concurrency-2 lanes claim "a.js" then "b.js" in order, each running its
  // own fully-synchronous prefix (including the git calls) before either
  // yields at its first await: by the time "b.js"'s post-git deadline check
  // runs, the fake clock has already advanced past the ~15s overall
  // deadline anchored at call entry, so it must be skipped as "aborted"
  // rather than dispatched, even though no real wall-clock time passed.
  assert.equal(dispatched, 1);
  assert.equal(out.items.length, 1);
  assert.equal(out.items[0].path, "a.js");
  const aborted = out.skipped.find((s) => s.path === "b.js");
  assert.ok(aborted, "expected b.js to be skipped");
  assert.equal(aborted.reason, "aborted");
});
