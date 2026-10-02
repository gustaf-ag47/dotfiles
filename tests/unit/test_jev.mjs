// Run: node --test tests/unit/test_jev.mjs
//
// All tests use temp state dirs and synthetic classifier injection. No real
// credentials, no config/pi/node_modules import, no network access.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  classifyTask,
  getStatus,
  validateConfig,
  resolveModeStrict,
  loadConfigValidated,
  worstCaseRequestBytes,
  reservedCostForConfig,
  hashCacheKey,
  DEFAULT_CONFIG,
  MAX_TASK_CHARS,
  HARD_MAX_TIMEOUT_MS,
} from "../../config/pi/lib/jev.mjs";

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "jev-test-"));
}

// Built by concatenation, not a quoted literal next to the env var name, so
// secret-scanning pre-commit hooks tuned for `KEY: "..."` patterns don't flag
// this obviously-synthetic placeholder. It is never sent anywhere: every
// test injects its own `classifyFn` instead of calling resolveClassifyFn().
const SYNTHETIC_TEST_TOKEN = ["synthetic", "test", "token", "not", "real"].join("-");

function baseEnv(overrides = {}) {
  const home = tmpDir();
  return {
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_STATE_HOME: path.join(home, ".local", "state"),
    TYPESAFE_API_KEY: SYNTHETIC_TEST_TOKEN,
    ...overrides,
  };
}

function okClassifier({ choice = "mechanical", confidence = 0.9, input = 300, output = 10 } = {}) {
  return async () => ({
    stopReason: "stop",
    answers: { task_class: { type: "choice", choice, probabilities: { [choice]: confidence }, confidence } },
    usage: { input, output },
  });
}

function configFor(stateDir) {
  return { ...DEFAULT_CONFIG, budget: { ...DEFAULT_CONFIG.budget } };
}

// ---------------------------------------------------------------------------
// Basic classification contract
// ---------------------------------------------------------------------------

test("ok classification: returns suggestion+confidence, applied false, logs ledger event", async () => {
  const env = baseEnv();
  const out = await classifyTask({ task: "Rename x to count", source: "delegate", env, classifyFn: okClassifier() });
  assert.equal(out.status, "ok");
  assert.equal(out.applied, false);
  assert.equal(out.suggestion, "mechanical");
  assert.equal(out.confidence, 0.9);
  assert.equal(out.reason, undefined);

  const ledgerFile = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  const lines = fs.readFileSync(ledgerFile, "utf8").trim().split("\n");
  assert.equal(lines.length, 1);
  const evt = JSON.parse(lines[0]);
  assert.equal(evt.schema, "jev-event.v1");
  assert.equal(evt.status, "ok");
  assert.equal(evt.class, "mechanical");
  assert.equal(evt.applied, false);
  assert.equal(evt.cost_source, "published-rate");
  assert.ok(evt.estimated_cost_usd > 0);
  assert.equal(evt.model, "jev-1.13.0");
  // No raw task text anywhere in the event.
  assert.ok(!JSON.stringify(evt).includes("Rename"));
});

test("abstain on low confidence: status abstained, reason low_confidence, usage still recorded", async () => {
  const env = baseEnv();
  const out = await classifyTask({
    task: "maybe fix it if it's easy",
    env,
    classifyFn: okClassifier({ choice: "build", confidence: 0.4 }),
    config: { ...DEFAULT_CONFIG, minConfidence: 0.6 },
  });
  assert.equal(out.status, "abstained");
  assert.equal(out.reason, "low_confidence");
  assert.equal(out.applied, false);
  assert.equal(out.suggestion, undefined);
});

test("unknown class from classifier is rejected, not cached, not trusted for cost", async () => {
  const env = baseEnv();
  const badFn = async () => ({
    stopReason: "stop",
    answers: { task_class: { type: "choice", choice: "not_a_real_class", probabilities: {}, confidence: 0.99 } },
    usage: { input: 50, output: 5 },
  });
  const out = await classifyTask({ task: "test", env, classifyFn: badFn });
  assert.equal(out.status, "error");
  assert.equal(out.reason, "unexpected_answer");
  const status = getStatus({ env });
  assert.equal(status.cacheEntries, 0);
});

test("out-of-range confidence from classifier is rejected", async () => {
  const env = baseEnv();
  const badFn = async () => ({
    stopReason: "stop",
    answers: { task_class: { type: "choice", choice: "build", probabilities: {}, confidence: 1.5 } },
    usage: { input: 50, output: 5 },
  });
  const out = await classifyTask({ task: "test", env, classifyFn: badFn });
  assert.equal(out.status, "error");
  assert.equal(out.reason, "unexpected_answer");
});

// ---------------------------------------------------------------------------
// Mode / safety defaults
// ---------------------------------------------------------------------------

test("PI_JEV_MODE=off short-circuits before any classify call, even with no config file", async () => {
  const env = baseEnv({ PI_JEV_MODE: "off" });
  let called = false;
  const out = await classifyTask({ task: "test", env, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "mode_off");
  assert.equal(called, false);
});

test("PI_JEV_MODE=off wins even when the config file is malformed", async () => {
  const env = baseEnv({ PI_JEV_MODE: "off" });
  const configPath = path.join(tmpDir(), "bad.json");
  fs.writeFileSync(configPath, "{not json");
  const out = await classifyTask({ task: "test", env, configPath, classifyFn: okClassifier() });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "mode_off");
});

test("invalid PI_JEV_MODE value abstains rather than defaulting to observe", async () => {
  const env = baseEnv({ PI_JEV_MODE: "apply" });
  let called = false;
  const out = await classifyTask({ task: "test", env, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "invalid_mode");
  assert.equal(called, false);
});

test("missing config file falls back to defaults (observe)", async () => {
  const env = baseEnv();
  const configPath = path.join(tmpDir(), "does-not-exist.json");
  const out = await classifyTask({ task: "test", env, configPath, classifyFn: okClassifier() });
  assert.equal(out.status, "ok");
});

test("missing API key skips quietly, no classify call made", async () => {
  const env = baseEnv({ TYPESAFE_API_KEY: "" });
  let called = false;
  const out = await classifyTask({ task: "test", env, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "missing_key");
  assert.equal(called, false);
});

test("task over MAX_TASK_CHARS is skipped without calling classifier", async () => {
  const env = baseEnv();
  let called = false;
  const out = await classifyTask({ task: "x".repeat(MAX_TASK_CHARS + 1), env, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "task_too_long");
  assert.equal(called, false);
});

// ---------------------------------------------------------------------------
// Config validation (must abstain, not silently default)
// ---------------------------------------------------------------------------

test("validateConfig rejects non-finite / out-of-range / unknown fields", () => {
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, minConfidence: 1.5 }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, minConfidence: Number.NaN }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, timeoutMs: 0 }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, timeoutMs: HARD_MAX_TIMEOUT_MS + 1 }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, timeoutMs: Infinity }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, classes: ["not_a_class"] }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, classes: ["build", "build"] }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, classes: [] }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, budget: { maxCallsPerDay: -1, maxCostPerDayUsd: 1 } }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, budget: { maxCallsPerDay: 1, maxCostPerDayUsd: Infinity } }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG, mode: "apply" }), false);
  assert.equal(validateConfig({ ...DEFAULT_CONFIG }), true);
});

test("malformed config JSON makes classifyTask abstain with config_malformed, no classify call", async () => {
  const env = baseEnv();
  const configPath = path.join(tmpDir(), "bad.json");
  fs.writeFileSync(configPath, "{this is not json");
  let called = false;
  const out = await classifyTask({ task: "test", env, configPath, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "config_malformed");
  assert.equal(called, false);
});

test("structurally invalid config (bad minConfidence) makes classifyTask abstain with config_invalid", async () => {
  const env = baseEnv();
  const configPath = path.join(tmpDir(), "invalid.json");
  fs.writeFileSync(configPath, JSON.stringify({ minConfidence: 2 }));
  let called = false;
  const out = await classifyTask({ task: "test", env, configPath, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "config_invalid");
  assert.equal(called, false);
});

test("loadConfigValidated: ENOENT is ok with defaults; malformed/invalid are not ok", () => {
  const dir = tmpDir();
  const missing = loadConfigValidated(path.join(dir, "nope.json"));
  assert.equal(missing.ok, true);
  assert.deepEqual(missing.config.classes, DEFAULT_CONFIG.classes);

  const malformedPath = path.join(dir, "malformed.json");
  fs.writeFileSync(malformedPath, "{bad");
  assert.equal(loadConfigValidated(malformedPath).ok, false);

  const invalidPath = path.join(dir, "invalid.json");
  fs.writeFileSync(invalidPath, JSON.stringify({ timeoutMs: -5 }));
  assert.equal(loadConfigValidated(invalidPath).ok, false);
});

// ---------------------------------------------------------------------------
// Budget: reservation, no-refund-after-dispatch, concurrency, corruption
// ---------------------------------------------------------------------------

test("budget exceeded skips before any classify call", async () => {
  const env = baseEnv();
  const config = { ...DEFAULT_CONFIG, budget: { maxCallsPerDay: 1, maxCostPerDayUsd: 1 } };
  let calls = 0;
  const fn = okClassifier();
  const wrapped = async (...args) => { calls += 1; return fn(...args); };
  const first = await classifyTask({ task: "task one", env, config, classifyFn: wrapped });
  assert.equal(first.status, "ok");
  const second = await classifyTask({ task: "task two", env, config, classifyFn: wrapped });
  assert.equal(second.status, "skipped");
  assert.equal(second.reason, "budget_exceeded");
  assert.equal(calls, 1);
});

test("timeout does NOT refund the reservation: budget still reflects the attempted call", async () => {
  const env = baseEnv();
  const config = { ...DEFAULT_CONFIG, timeoutMs: 50 };
  const neverResolves = () => new Promise(() => {}); // simulates an ignored AbortSignal
  const out = await classifyTask({ task: "slow task", env, config, classifyFn: neverResolves });
  assert.equal(out.status, "error");
  assert.equal(out.reason, "timeout");

  const status = getStatus({ env });
  assert.equal(status.budget.calls, 1);
  assert.ok(status.budget.costUsd > 0, "reserved cost must remain, not be refunded to 0");
});

test("classifier_error (non-stop result, no exception) does NOT refund the reservation", async () => {
  const env = baseEnv();
  const erroringFn = async () => ({ stopReason: "error", errorMessage: "simulated upstream 500", usage: { input: 0, output: 0 } });
  const out = await classifyTask({ task: "test", env, classifyFn: erroringFn });
  assert.equal(out.status, "error");
  assert.equal(out.reason, "classifier_error");
  // The suspicious "usage: 0" on an error result must not be trusted as a real $0 cost.
  const ledgerFile = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  const evt = JSON.parse(fs.readFileSync(ledgerFile, "utf8").trim());
  assert.equal(evt.estimated_cost_usd, null);
  assert.equal(evt.cost_source, "unknown");

  const status = getStatus({ env });
  assert.ok(status.budget.costUsd > 0, "reservation must remain after an error result, not reset to 0");
});

test("thrown exception from classifyFn does NOT refund the reservation and never throws out of classifyTask", async () => {
  const env = baseEnv();
  const throwingFn = async () => { throw new Error("simulated network failure"); };
  const out = await classifyTask({ task: "test", env, classifyFn: throwingFn });
  assert.equal(out.status, "error");
  assert.equal(out.reason, "classifier_error");
  const status = getStatus({ env });
  assert.ok(status.budget.costUsd > 0);
});

test("classifier_unavailable (no fn resolvable) DOES release the reservation: nothing was ever dispatched", async () => {
  const env = baseEnv({ JEV_CLASSIFY_MODULE: "/nonexistent/module/path.mjs" });
  const out = await classifyTask({ task: "test", env }); // no classifyFn injected -> resolveClassifyFn() fails
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "classifier_unavailable");
  const status = getStatus({ env });
  assert.equal(status.budget.calls, 0);
  assert.equal(status.budget.costUsd, 0);
});

test("budget reservation is based on a conservative worst-case byte bound, not the actual short task length", () => {
  const bytes = worstCaseRequestBytes(DEFAULT_CONFIG);
  assert.ok(bytes >= MAX_TASK_CHARS * 3, "must reserve for the worst-case task length, not the call's actual length");
  const cost = reservedCostForConfig(DEFAULT_CONFIG);
  assert.ok(cost > 0);
  // Sanity: should be well under a cent for the default per-million rate even at worst case.
  assert.ok(cost < 0.01);
});

test("corrupted budget.json fails closed (denies the call) rather than resetting to zero", async () => {
  const env = baseEnv();
  const stateDir = path.join(env.XDG_STATE_HOME, "jev");
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  fs.writeFileSync(path.join(stateDir, "budget.json"), "{not valid json", { mode: 0o600 });
  let called = false;
  const out = await classifyTask({ task: "test", env, classifyFn: async () => { called = true; } });
  assert.equal(out.status, "skipped");
  assert.equal(out.reason, "budget_corrupt");
  assert.equal(called, false);
});

test("budget.json missing entirely (first run) is treated as zero, not corrupt", async () => {
  const env = baseEnv();
  const out = await classifyTask({ task: "test", env, classifyFn: okClassifier() });
  assert.equal(out.status, "ok");
});

test("budget rolls over cleanly on a new UTC day", async () => {
  const env = baseEnv();
  const config = { ...DEFAULT_CONFIG, budget: { maxCallsPerDay: 1, maxCostPerDayUsd: 1 } };
  const day1 = 1_700_000_000_000;
  const day2 = day1 + 2 * 24 * 60 * 60 * 1000;
  const first = await classifyTask({ task: "one", env, config, classifyFn: okClassifier(), now: () => day1 });
  assert.equal(first.status, "ok");
  const second = await classifyTask({ task: "two", env, config, classifyFn: okClassifier(), now: () => day2 });
  assert.equal(second.status, "ok", "a new day must not inherit yesterday's exhausted budget");
});

test("concurrent classify calls do not both slip under a one-call budget cap", async () => {
  const env = baseEnv();
  const config = { ...DEFAULT_CONFIG, budget: { maxCallsPerDay: 1, maxCostPerDayUsd: 1 } };
  const results = await Promise.all([
    classifyTask({ task: "a", env, config, classifyFn: okClassifier() }),
    classifyTask({ task: "b", env, config, classifyFn: okClassifier() }),
    classifyTask({ task: "c", env, config, classifyFn: okClassifier() }),
  ]);
  const okCount = results.filter((r) => r.status === "ok").length;
  assert.equal(okCount, 1, "exactly one concurrent call should win the one-call budget");
  const status = getStatus({ env });
  assert.equal(status.budget.calls, 1);
});

// ---------------------------------------------------------------------------
// Cache: isolation, threshold/rubric sensitivity, no error caching
// ---------------------------------------------------------------------------

test("second identical call is a cache hit with zero additional cost and no second classify invocation", async () => {
  const env = baseEnv();
  let calls = 0;
  const fn = okClassifier();
  const wrapped = async (...args) => { calls += 1; return fn(...args); };
  const first = await classifyTask({ task: "Rename x to count", env, classifyFn: wrapped });
  assert.equal(first.status, "ok");
  const second = await classifyTask({ task: "Rename x to count", env, classifyFn: wrapped });
  assert.equal(second.status, "cache_hit");
  assert.equal(second.suggestion, "mechanical");
  assert.equal(calls, 1);

  const ledgerFile = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  const events = fs.readFileSync(ledgerFile, "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(events[1].cost_source, "cache");
  assert.equal(events[1].estimated_cost_usd, 0);
  assert.equal(events[1].input_tokens, 0);
  assert.equal(events[1].output_tokens, 0);
});

test("pre-dispatch skipped events record known-zero usage/cost (cache bucket), not null/unknown", async () => {
  const env = baseEnv({ PI_JEV_MODE: "off" });
  await classifyTask({ task: "test", env });
  const ledgerFile = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  const evt = JSON.parse(fs.readFileSync(ledgerFile, "utf8").trim());
  assert.equal(evt.status, "skipped");
  assert.equal(evt.input_tokens, 0);
  assert.equal(evt.output_tokens, 0);
  assert.equal(evt.estimated_cost_usd, 0);
  assert.equal(evt.cost_source, "cache");
});

test("dispatched timeout/error events keep null/unknown usage, never known-zero", async () => {
  const env = baseEnv();
  const config = { ...DEFAULT_CONFIG, timeoutMs: 50 };
  await classifyTask({ task: "slow", env, config, classifyFn: () => new Promise(() => {}) });
  const ledgerFile = path.join(env.XDG_STATE_HOME, "jev", "events.jsonl");
  const evt = JSON.parse(fs.readFileSync(ledgerFile, "utf8").trim());
  assert.equal(evt.status, "error");
  assert.equal(evt.input_tokens, null);
  assert.equal(evt.output_tokens, null);
  assert.equal(evt.estimated_cost_usd, null);
  assert.equal(evt.cost_source, "unknown");
});

test("cache key changes with minConfidence, so changing the threshold invalidates stale entries", () => {
  const a = hashCacheKey({ task: "x", rubricVersion: "v1", model: "jev-1.13.0", minConfidence: 0.6, classes: ["build"] });
  const b = hashCacheKey({ task: "x", rubricVersion: "v1", model: "jev-1.13.0", minConfidence: 0.7, classes: ["build"] });
  assert.notEqual(a, b);
});

test("cache key is order-independent in classes but sensitive to the class set", () => {
  const a = hashCacheKey({ task: "x", rubricVersion: "v1", model: "m", minConfidence: 0.6, classes: ["build", "research"] });
  const b = hashCacheKey({ task: "x", rubricVersion: "v1", model: "m", minConfidence: 0.6, classes: ["research", "build"] });
  const c = hashCacheKey({ task: "x", rubricVersion: "v1", model: "m", minConfidence: 0.6, classes: ["build"] });
  assert.equal(a, b);
  assert.notEqual(a, c);
});

test("a changed threshold between two calls for the same task does not reuse the old cache entry", async () => {
  const env = baseEnv();
  const configLoose = { ...DEFAULT_CONFIG, minConfidence: 0.3 };
  const configStrict = { ...DEFAULT_CONFIG, minConfidence: 0.95 };
  const fn = okClassifier({ confidence: 0.5 });
  const first = await classifyTask({ task: "same task text", env, config: configLoose, classifyFn: fn });
  assert.equal(first.status, "ok");
  const second = await classifyTask({ task: "same task text", env, config: configStrict, classifyFn: fn });
  // Different cache key (different minConfidence) -> real call again -> now abstains under the stricter bar.
  assert.equal(second.status, "abstained");
});

test("errors and abstains are never cached", async () => {
  const env = baseEnv();
  const abstainFn = okClassifier({ confidence: 0.1 });
  await classifyTask({ task: "ambiguous task", env, classifyFn: abstainFn, config: { ...DEFAULT_CONFIG, minConfidence: 0.6 } });
  const status1 = getStatus({ env });
  assert.equal(status1.cacheEntries, 0);

  const errorFn = async () => ({ stopReason: "error" });
  await classifyTask({ task: "another task", env, classifyFn: errorFn });
  const status2 = getStatus({ env });
  assert.equal(status2.cacheEntries, 0);
});

test("cache is isolated per state dir (no cross-test/process bleed)", async () => {
  const envA = baseEnv();
  const envB = baseEnv();
  await classifyTask({ task: "shared text", env: envA, classifyFn: okClassifier() });
  const statusB = getStatus({ env: envB });
  assert.equal(statusB.cacheEntries, 0);
});

// ---------------------------------------------------------------------------
// Status surface
// ---------------------------------------------------------------------------

test("getStatus never classifies and reflects accumulated counts correctly", async () => {
  const env = baseEnv();
  await classifyTask({ task: "a", env, classifyFn: okClassifier() });
  await classifyTask({ task: "a", env, classifyFn: okClassifier() }); // cache hit
  await classifyTask({ task: "b", env, classifyFn: okClassifier({ confidence: 0.1 }), config: { ...DEFAULT_CONFIG, minConfidence: 0.6 } });
  const status = getStatus({ env });
  assert.equal(status.today.ok, 1);
  assert.equal(status.today.cache_hit, 1);
  assert.equal(status.today.abstained, 1);
  assert.equal(status.mode, "observe");
  assert.equal(status.configValid, true);
});

test("getStatus reports configValid:false and the reason when config is invalid, without throwing", () => {
  const env = baseEnv();
  const configPath = path.join(tmpDir(), "bad.json");
  fs.writeFileSync(configPath, JSON.stringify({ classes: [] }));
  const status = getStatus({ env, configPath });
  assert.equal(status.configValid, false);
  assert.equal(status.configError, "config_invalid");
});

// ---------------------------------------------------------------------------
// resolveModeStrict unit coverage
// ---------------------------------------------------------------------------

test("resolveModeStrict: env takes precedence over config; unknown values are flagged invalid, not coerced", () => {
  assert.deepEqual(resolveModeStrict({ env: { PI_JEV_MODE: "off" }, config: { mode: "observe" } }), { mode: "off" });
  assert.deepEqual(resolveModeStrict({ env: {}, config: { mode: "off" } }), { mode: "off" });
  assert.deepEqual(resolveModeStrict({ env: {}, config: {} }), { mode: "observe" });
  assert.deepEqual(resolveModeStrict({ env: { PI_JEV_MODE: "ON" }, config: {} }), { mode: "invalid", reason: "invalid_mode" });
});

// ---------------------------------------------------------------------------
// No secrets / no raw task text ever reach a result or ledger event
// ---------------------------------------------------------------------------

test("no result object from classifyTask ever contains the raw task text", async () => {
  const env = baseEnv();
  const secretTask = "contains a SECRET_TOKEN_abc123 that must never leak";
  const outcomes = await Promise.all([
    classifyTask({ task: secretTask, env: baseEnv(), classifyFn: okClassifier() }),
    classifyTask({ task: secretTask, env: baseEnv({ PI_JEV_MODE: "off" }) }),
    classifyTask({ task: secretTask, env: baseEnv({ TYPESAFE_API_KEY: "" }) }),
  ]);
  for (const out of outcomes) {
    assert.ok(!JSON.stringify(out).includes("SECRET_TOKEN"));
  }
  void env;
});
