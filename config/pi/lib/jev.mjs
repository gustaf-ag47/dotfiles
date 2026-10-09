// Shared Jev (TypeSafe System One) shadow-classifier helper.
//
// Used by bin/jev-classify (CLI, invoked by the delegate shell wrapper) and
// config/pi/extensions/jev.ts (Pi extension, /jev command, manual use only).
// One implementation behind both callers, per the implementation brief
// (operator notes: jev-helper-implementation.md).
//
// Hard constraints enforced here, not just documented:
//   - Never applies a classification result to anything (`applied` is always
//     false in every return value and ledger event).
//   - Default mode is "observe"; PI_JEV_MODE=off|observe is the only runtime
//     override; there is no "apply"/"on" mode in this module at all.
//     PI_JEV_MODE=off always short-circuits, even if the config file on disk
//     is missing or malformed -- an explicit opt-out must never depend on
//     config correctness.
//   - A missing config file is fine (uses built-in defaults); a *present but
//     invalid* config file (malformed JSON, out-of-range numbers, unknown
//     classes, non-finite caps) makes every call abstain with
//     status:"skipped", reason:"config_invalid"/"config_malformed" rather
//     than silently falling back to defaults -- see validateConfig().
//   - Budget reservations are conservative and never refunded once a request
//     has actually been dispatched: a timeout or classifier error does not
//     prove the upstream service didn't bill the request, so that call
//     counts fully against both the daily call cap and the daily cost cap.
//     Reservations are only released when no request was ever sent (e.g. the
//     classifier implementation could not be resolved).
//   - No raw task text, prompts, file contents, or raw provider error text
//     ever reaches the ledger, the cache, or stdout -- only short bounded
//     reason codes and the classifier's own validated, whitelisted answer.
//   - No network access or credential handling happens unless classifyTask()
//     is given a `classifyFn` (tests inject a synthetic one; real callers get
//     one from resolveClassifyFn(), which imports Pi's own installed
//     @earendil-works/pi-ai TypeSafe System One client -- this module does
//     not implement an HTTP client itself).
//
// Timeout honesty: Pi's installed `classifySystemOne` (read directly from
// @earendil-works/pi-ai/dist/api/system-one-shared.js while implementing
// this) threads a caller-supplied `options.signal` straight into its
// `fetch()` call and never rejects -- it always resolves with
// `stopReason: "aborted"|"error"` and sets that error text as
// `errorMessage`, which this module never reads. So aborting our own
// AbortController does cancel the in-flight HTTP request for that verified
// client. This module still wraps every dispatch in a hard Promise.race
// timeout as a backstop for any other `classifyFn` (a different provider, a
// future SDK version, a test double) that might not honor AbortSignal or
// might reject instead of resolving; the abandoned promise is given a no-op
// `.catch()` so it can never become an unhandled rejection.
//
// Redirect honesty: neither this module nor the installed TypeSafe client
// sets an explicit `redirect` option on its `fetch()` call, so redirect
// handling is whatever the active `fetch` implementation defaults to
// (Node's built-in `fetch`/undici follows redirects and applies the
// WHATWG Fetch spec's own credential-stripping rules for cross-origin
// redirects). This has not been exercised against a live redirecting
// endpoint in this environment -- no network access was used while building
// or testing this module -- so this is a description of the code path, not
// a verified behavioral guarantee.
//
// Pricing note: Pi's bundled model catalog lists typesafe/jev-latest at
// cost.input = 0, but TypeSafe's own published pricing (docs.typesafe.ai) is
// $0.042 per million input tokens, output free. This module always computes
// estimated_cost_usd from the official published rate, never from Pi's
// catalog, and labels it cost_source: "published-rate" (see
// operator notes: jev-helper-implementation.md for the discrepancy writeup).

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const SCHEMA_VERSION = "jev-event.v1";
export const DEFAULT_MODEL_ID = "jev-1.13.0";
export const RUBRIC_VERSION = "task-class.v1";
export const CLASSES = Object.freeze(["interactive", "build", "research", "mechanical"]);
export const MAX_TASK_CHARS = 2000;

/** Hard ceiling on the classify timeout regardless of config; config can only tighten, never loosen past this. */
export const HARD_MAX_TIMEOUT_MS = 5000;
/** Grace window added on top of the configured timeout before the Promise.race backstop fires. */
const HARD_TIMEOUT_GRACE_MS = 250;

const CLASS_DESCRIPTIONS = {
  interactive: "Needs back-and-forth with a human; cannot be completed from a single task description alone",
  build: "Ordinary feature or fix work with a reasonably clear scope",
  research: "Investigation, reading, or summarizing; no code change expected",
  mechanical: "Pure syntax/rename/format/mechanical change, no judgment required",
};

const LIB_DIR = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_CONFIG = Object.freeze({
  schema: "jev-config.v1",
  mode: "observe",
  model: DEFAULT_MODEL_ID,
  rubricVersion: RUBRIC_VERSION,
  classes: CLASSES,
  minConfidence: 0.6,
  timeoutMs: 3000,
  budget: { maxCallsPerDay: 100, maxCostPerDayUsd: 0.05 },
  cache: { ttlSeconds: 86400, maxEntries: 500 },
  costPerMillionInputUsd: 0.042,
});

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

export function xdgConfigHome(env = process.env) {
  return env.XDG_CONFIG_HOME || path.join(env.HOME || os.homedir(), ".config");
}

export function xdgStateHome(env = process.env) {
  return env.XDG_STATE_HOME || path.join(env.HOME || os.homedir(), ".local", "state");
}

export function defaultKeyPath(env = process.env) {
  return env.PI_JEV_KEY_FILE || path.join(xdgConfigHome(env), "jev", "api-key");
}

export function defaultStateDir(env = process.env) {
  return env.PI_JEV_STATE_DIR || path.join(xdgStateHome(env), "jev");
}

export function defaultConfigPath() {
  return path.join(LIB_DIR, "..", "..", "llm-proxy", "jev.json");
}

export function ledgerPath(stateDir) {
  return path.join(stateDir, "events.jsonl");
}

// ---------------------------------------------------------------------------
// Config loading + validation
// ---------------------------------------------------------------------------

function deepMerge(base, override) {
  const out = { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (value && typeof value === "object" && !Array.isArray(value) && base[key] && typeof base[key] === "object") {
      out[key] = deepMerge(base[key], value);
    } else if (value !== undefined) {
      out[key] = value;
    }
  }
  return out;
}

function isFiniteNumber(v) {
  return typeof v === "number" && Number.isFinite(v);
}

/** Strict validation: a config that fails this must make callers abstain, never silently run on partial defaults. */
export function validateConfig(cfg) {
  if (!cfg || typeof cfg !== "object") return false;
  if (cfg.mode !== undefined && cfg.mode !== "off" && cfg.mode !== "observe") return false;
  if (typeof cfg.model !== "string" || cfg.model.length === 0) return false;
  if (typeof cfg.rubricVersion !== "string" || cfg.rubricVersion.length === 0) return false;
  if (!Array.isArray(cfg.classes) || cfg.classes.length === 0) return false;
  if (!cfg.classes.every((c) => typeof c === "string" && CLASSES.includes(c))) return false;
  if (new Set(cfg.classes).size !== cfg.classes.length) return false;
  if (!isFiniteNumber(cfg.minConfidence) || cfg.minConfidence < 0 || cfg.minConfidence > 1) return false;
  if (!isFiniteNumber(cfg.timeoutMs) || cfg.timeoutMs <= 0 || cfg.timeoutMs > HARD_MAX_TIMEOUT_MS) return false;
  if (!cfg.budget || typeof cfg.budget !== "object") return false;
  if (!isFiniteNumber(cfg.budget.maxCallsPerDay) || cfg.budget.maxCallsPerDay <= 0) return false;
  if (!isFiniteNumber(cfg.budget.maxCostPerDayUsd) || cfg.budget.maxCostPerDayUsd <= 0) return false;
  if (!isFiniteNumber(cfg.costPerMillionInputUsd) || cfg.costPerMillionInputUsd < 0) return false;
  if (!cfg.cache || typeof cfg.cache !== "object") return false;
  if (!isFiniteNumber(cfg.cache.ttlSeconds) || cfg.cache.ttlSeconds <= 0) return false;
  if (!isFiniteNumber(cfg.cache.maxEntries) || cfg.cache.maxEntries <= 0) return false;
  return true;
}

/**
 * Loads and validates config. A missing file (ENOENT) is not an error: it
 * resolves to the built-in defaults. Any other failure to read, parse, or
 * validate the file is reported as `{ ok: false, reason }` so the caller
 * abstains instead of silently running with defaults it never asked for.
 */
export function loadConfigValidated(configPath = defaultConfigPath(), fsImpl = fs) {
  let raw;
  try {
    raw = fsImpl.readFileSync(configPath, "utf8");
  } catch (err) {
    if (err && err.code === "ENOENT") return { ok: true, config: deepMerge(DEFAULT_CONFIG, {}) };
    return { ok: false, reason: "config_unreadable" };
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, reason: "config_malformed" };
  }
  const merged = deepMerge(DEFAULT_CONFIG, parsed);
  if (!validateConfig(merged)) return { ok: false, reason: "config_invalid" };
  return { ok: true, config: merged };
}

/** Convenience loader for read-only/status callers that don't need to distinguish failure reasons. */
export function loadConfig(configPath = defaultConfigPath(), fsImpl = fs) {
  const loaded = loadConfigValidated(configPath, fsImpl);
  return loaded.ok ? loaded.config : deepMerge(DEFAULT_CONFIG, {});
}

/**
 * Resolves mode strictly. An explicit PI_JEV_MODE value that is neither
 * "off" nor "observe" is reported as invalid rather than silently treated as
 * "observe" -- a typo in an opt-out env var must not accidentally turn
 * observation on.
 */
export function resolveModeStrict({ env = process.env, config = DEFAULT_CONFIG } = {}) {
  const envRaw = env.PI_JEV_MODE;
  if (typeof envRaw === "string" && envRaw.trim().length > 0) {
    const v = envRaw.trim().toLowerCase();
    if (v === "off") return { mode: "off" };
    if (v === "observe") return { mode: "observe" };
    return { mode: "invalid", reason: "invalid_mode" };
  }
  const v = (config.mode ?? "observe").toString().trim().toLowerCase();
  if (v === "off") return { mode: "off" };
  if (v === "observe") return { mode: "observe" };
  return { mode: "invalid", reason: "invalid_mode" };
}

/** Loose variant used by status/display code that just wants a best-effort "off"/"observe" string. */
export function resolveMode({ env = process.env, config = DEFAULT_CONFIG } = {}) {
  const result = resolveModeStrict({ env, config });
  return result.mode === "off" ? "off" : "observe";
}

/** Reads the TypeSafe API key. Never logs it. Returns null (not an error) when absent. */
export function resolveApiKey({ env = process.env, fsImpl = fs } = {}) {
  if (typeof env.TYPESAFE_API_KEY === "string" && env.TYPESAFE_API_KEY.trim()) {
    return env.TYPESAFE_API_KEY.trim();
  }
  const keyPath = defaultKeyPath(env);
  try {
    const raw = fsImpl.readFileSync(keyPath, "utf8").trim();
    return raw || null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Cache key -- includes threshold and class set so a config change
// invalidates stale entries automatically rather than requiring a
// re-validation pass against "current" config at read time.
// ---------------------------------------------------------------------------

export function hashCacheKey({ task, rubricVersion, model, minConfidence, classes }) {
  const classesKey = [...classes].sort().join(",");
  return crypto
    .createHash("sha256")
    .update(`${rubricVersion}\u0000${model}\u0000${minConfidence}\u0000${classesKey}\u0000${task}`, "utf8")
    .digest("hex");
}

export function todayUtc(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Filesystem: dirs, locking, atomic writes, bounded ledger append
// ---------------------------------------------------------------------------

function ensureStateDir(stateDir, fsImpl) {
  fsImpl.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  try {
    fsImpl.chmodSync(stateDir, 0o700);
  } catch {
    /* best effort on filesystems that don't support chmod */
  }
}

const LOCK_STALE_MS = 5000;
const LOCK_RETRY_MS = 15;
const LOCK_MAX_WAIT_MS = 2000;

/** Simple cross-process advisory lock via atomic mkdir. Synchronous, bounded wait, stale takeover. */
function withLock(stateDir, fsImpl, fn) {
  const lockDir = path.join(stateDir, ".lock");
  const deadline = Date.now() + LOCK_MAX_WAIT_MS;
  for (;;) {
    try {
      fsImpl.mkdirSync(lockDir);
      break;
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      try {
        const st = fsImpl.statSync(lockDir);
        if (Date.now() - st.mtimeMs > LOCK_STALE_MS) {
          try {
            fsImpl.rmdirSync(lockDir);
          } catch {
            /* lost the race to another process cleaning it up */
          }
          continue;
        }
      } catch {
        continue; // lock dir vanished between mkdir failing and stat; retry
      }
      if (Date.now() > deadline) throw new Error("jev_lock_timeout");
      busyWait(LOCK_RETRY_MS);
    }
  }
  try {
    return fn();
  } finally {
    try {
      fsImpl.rmdirSync(lockDir);
    } catch {
      /* ignore */
    }
  }
}

// Synchronous micro-sleep. The lock window is a few milliseconds of local
// file IO, so a short busy-wait is simpler and safer here than threading
// async/await through every sync fs call in this module.
function busyWait(ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    /* spin */
  }
}

function atomicWriteFile(file, data, fsImpl, mode = 0o600) {
  const tmp = `${file}.tmp-${process.pid}-${crypto.randomBytes(4).toString("hex")}`;
  fsImpl.writeFileSync(tmp, data, { mode });
  try {
    fsImpl.chmodSync(tmp, mode);
  } catch {
    /* best effort */
  }
  fsImpl.renameSync(tmp, file);
}

const MAX_LEDGER_BYTES = 5 * 1024 * 1024;

function rotateLedgerIfLarge(file, fsImpl) {
  try {
    const st = fsImpl.statSync(file);
    if (st.size > MAX_LEDGER_BYTES) {
      fsImpl.renameSync(file, `${file}.1`);
    }
  } catch {
    /* no existing file yet */
  }
}

/**
 * Appends one ledger event. Schema is fixed by the implementation contract
 * (operator notes: jev-helper-implementation.md): never put task text, prompts,
 * file paths, auth, or raw error text in `event`.
 */
export function appendLedgerEvent(event, { stateDir = defaultStateDir(), fsImpl = fs } = {}) {
  ensureStateDir(stateDir, fsImpl);
  const file = ledgerPath(stateDir);
  withLock(stateDir, fsImpl, () => {
    rotateLedgerIfLarge(file, fsImpl);
    const existed = fsImpl.existsSync(file);
    fsImpl.appendFileSync(file, `${JSON.stringify(event)}\n`, { mode: 0o600 });
    if (!existed) {
      try {
        fsImpl.chmodSync(file, 0o600);
      } catch {
        /* best effort */
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Budget: calls/day and cost/day, concurrency-safe via the same lock.
// Fails closed: a present-but-corrupted budget file denies new calls rather
// than resetting silently to zero (which would let a corrupted/tampered
// counters file erase an already-exhausted budget). A missing file (first
// run) and an ordinary day rollover are both legitimate zero states.
// ---------------------------------------------------------------------------

function budgetPath(stateDir) {
  return path.join(stateDir, "budget.json");
}

/** Returns `{ ok: true, state }` or `{ ok: false }` (present-but-corrupt -> fail closed). */
function readBudgetState(file, fsImpl, today) {
  let raw;
  try {
    raw = fsImpl.readFileSync(file, "utf8");
  } catch (err) {
    if (err && err.code === "ENOENT") return { ok: true, state: { date: today, calls: 0, costUsd: 0 } };
    return { ok: false };
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false };
  }
  if (!parsed || typeof parsed !== "object" || typeof parsed.date !== "string" || !isFiniteNumber(parsed.calls) || !isFiniteNumber(parsed.costUsd)) {
    return { ok: false };
  }
  if (parsed.date !== today) return { ok: true, state: { date: today, calls: 0, costUsd: 0 } }; // rollover is fine
  return { ok: true, state: { date: today, calls: parsed.calls, costUsd: parsed.costUsd } };
}

function writeBudgetState(file, fsImpl, state) {
  atomicWriteFile(file, JSON.stringify(state), fsImpl);
}

/**
 * Worst-case UTF-8 byte reservation for one classify request, computed from
 * the fixed rubric (depends only on config.classes, so it's measured exactly)
 * plus a conservative bound for the task text. MAX_TASK_CHARS counts JS
 * UTF-16 code units; the worst realistic UTF-8 expansion for a single such
 * unit is 3 bytes (BMP chars outside ASCII), and this doubles that to absorb
 * JSON-string-escaping overhead (quotes/backslashes) without having to
 * reason precisely about which characters round-trip through JSON.stringify
 * unescaped. This is intentionally conservative, not a tight estimate: it is
 * used only to bound the daily cost cap reservation, never to compute a
 * displayed/billed cost (actual cost always comes from the provider's own
 * reported usage on success).
 */
export function worstCaseRequestBytes(config) {
  const BYTES_PER_CHAR_WORST_CASE = 6;
  const taskBytes = MAX_TASK_CHARS * BYTES_PER_CHAR_WORST_CASE;
  const questionsBytes = Buffer.byteLength(JSON.stringify(questionsFor(config.classes)), "utf8");
  const overheadBytes = 256; // model id, state wrapper, JSON punctuation, headers are not counted (not billed as input tokens)
  return taskBytes + questionsBytes + overheadBytes;
}

/** Conservative reservation: treats 1 byte as >= 1 priced input unit, which over-reserves for every real tokenizer. */
export function reservedCostForConfig(config) {
  const bytes = worstCaseRequestBytes(config);
  return (bytes / 1_000_000) * config.costPerMillionInputUsd;
}

/**
 * Reserves one call's conservative estimated cost against today's budget
 * before the network call is made, so concurrent launches cannot both slip
 * under the cap by racing the read-modify-write. Returns
 * `{ allowed: true, release(), settle(actualCostUsd) }` or
 * `{ allowed: false, reason }`.
 */
export function reserveBudget({ stateDir = defaultStateDir(), fsImpl = fs, now = Date.now, caps, reservedCostUsd }) {
  ensureStateDir(stateDir, fsImpl);
  const file = budgetPath(stateDir);
  const today = todayUtc(now());
  const outcome = withLock(stateDir, fsImpl, () => {
    const read = readBudgetState(file, fsImpl, today);
    if (!read.ok) return { allowed: false, reason: "budget_corrupt" };
    const state = read.state;
    const wouldCalls = state.calls + 1;
    const wouldCost = state.costUsd + reservedCostUsd;
    if (wouldCalls > caps.maxCallsPerDay || wouldCost > caps.maxCostPerDayUsd) {
      return { allowed: false, reason: "budget_exceeded" };
    }
    writeBudgetState(file, fsImpl, { date: today, calls: wouldCalls, costUsd: wouldCost });
    return { allowed: true, today, reservedCostUsd };
  });
  if (!outcome.allowed) return { allowed: false, reason: outcome.reason };
  return {
    allowed: true,
    release: () => adjustBudget({ stateDir, fsImpl, now, today: outcome.today, deltaCostUsd: -outcome.reservedCostUsd, deltaCalls: -1 }),
    settle: (actualCostUsd) =>
      adjustBudget({
        stateDir,
        fsImpl,
        now,
        today: outcome.today,
        deltaCostUsd: (actualCostUsd ?? outcome.reservedCostUsd) - outcome.reservedCostUsd,
        deltaCalls: 0,
      }),
  };
}

function adjustBudget({ stateDir, fsImpl, now, today, deltaCostUsd, deltaCalls }) {
  const file = budgetPath(stateDir);
  withLock(stateDir, fsImpl, () => {
    const currentToday = todayUtc(now());
    // Only adjust if still the same accounting day; a reservation that spans
    // midnight simply expires harmlessly rather than corrupting the new day.
    if (currentToday !== today) return;
    const read = readBudgetState(file, fsImpl, today);
    if (!read.ok) return; // corrupted since the reservation; fail closed, do not "fix" it here
    const state = read.state;
    writeBudgetState(file, fsImpl, {
      date: today,
      calls: Math.max(0, state.calls + deltaCalls),
      costUsd: Math.max(0, state.costUsd + deltaCostUsd),
    });
  });
}

/** Read-only snapshot for status reporting; never mutates. Corruption is reported, not hidden as zero. */
export function readBudgetSnapshot({ stateDir = defaultStateDir(), fsImpl = fs, now = Date.now } = {}) {
  const file = budgetPath(stateDir);
  const today = todayUtc(now());
  try {
    const read = readBudgetState(file, fsImpl, today);
    if (!read.ok) return { date: today, calls: 0, costUsd: 0, corrupt: true };
    return { ...read.state, corrupt: false };
  } catch {
    return { date: today, calls: 0, costUsd: 0, corrupt: true };
  }
}

// ---------------------------------------------------------------------------
// Cache: bounded TTL cache of successful classifications only. Corrupted
// cache entries are discarded (cache is an optimization, not a safety gate,
// so "fail open to a miss" is the right behavior here, unlike the budget).
// ---------------------------------------------------------------------------

function cachePath(stateDir) {
  return path.join(stateDir, "cache.json");
}

function readCacheFile(file, fsImpl) {
  try {
    const raw = JSON.parse(fsImpl.readFileSync(file, "utf8"));
    if (raw && typeof raw === "object" && raw.entries && typeof raw.entries === "object") return raw;
  } catch {
    /* missing or malformed: start fresh */
  }
  return { entries: {} };
}

function writeCacheFile(file, fsImpl, data) {
  atomicWriteFile(file, JSON.stringify(data), fsImpl);
}

function isValidCacheEntry(entry) {
  return (
    entry &&
    typeof entry.class === "string" &&
    CLASSES.includes(entry.class) &&
    typeof entry.confidence === "number" &&
    Number.isFinite(entry.confidence) &&
    entry.confidence >= 0 &&
    entry.confidence <= 1 &&
    typeof entry.expiresAt === "number" &&
    Number.isFinite(entry.expiresAt)
  );
}

/** Returns `{ class, confidence }` on a live, structurally valid hit, else null. Never caches errors. */
export function getCacheEntry(key, { stateDir = defaultStateDir(), fsImpl = fs, now = Date.now } = {}) {
  ensureStateDir(stateDir, fsImpl);
  const file = cachePath(stateDir);
  return withLock(stateDir, fsImpl, () => {
    const data = readCacheFile(file, fsImpl);
    const entry = data.entries[key];
    if (!entry || !isValidCacheEntry(entry)) {
      if (entry) {
        delete data.entries[key];
        writeCacheFile(file, fsImpl, data);
      }
      return null;
    }
    if (entry.expiresAt <= now()) {
      delete data.entries[key];
      writeCacheFile(file, fsImpl, data);
      return null;
    }
    return { class: entry.class, confidence: entry.confidence };
  });
}

/** Stores a successful classification result, pruning expired/invalid entries and bounding total size. */
export function setCacheEntry(key, { class: cls, confidence }, { stateDir = defaultStateDir(), fsImpl = fs, now = Date.now, ttlSeconds, maxEntries } = {}) {
  ensureStateDir(stateDir, fsImpl);
  const file = cachePath(stateDir);
  withLock(stateDir, fsImpl, () => {
    const data = readCacheFile(file, fsImpl);
    const nowMs = now();
    for (const [k, v] of Object.entries(data.entries)) {
      if (!isValidCacheEntry(v) || v.expiresAt <= nowMs) delete data.entries[k];
    }
    data.entries[key] = { class: cls, confidence, expiresAt: nowMs + ttlSeconds * 1000 };
    const keys = Object.keys(data.entries);
    if (keys.length > maxEntries) {
      keys
        .sort((a, b) => data.entries[a].expiresAt - data.entries[b].expiresAt)
        .slice(0, keys.length - maxEntries)
        .forEach((k) => delete data.entries[k]);
    }
    writeCacheFile(file, fsImpl, data);
  });
}

// ---------------------------------------------------------------------------
// Classifier model + questions
// ---------------------------------------------------------------------------

export function jevModel(config = DEFAULT_CONFIG) {
  return {
    type: "classifier",
    id: config.model,
    name: "Jev",
    api: "typesafe-system-one",
    provider: "typesafe",
    baseUrl: "https://api.typesafe.ai/v1/",
    input: ["text"],
    cost: { input: config.costPerMillionInputUsd, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 64000,
  };
}

export function questionsFor(classes = CLASSES) {
  const criteria = {};
  for (const cls of classes) criteria[cls] = CLASS_DESCRIPTIONS[cls] || cls;
  return {
    task_class: {
      type: "choice",
      instructions: "Classify the software engineering task described in `task` using exactly one of the listed categories.",
      criteria,
    },
  };
}

/**
 * Resolves Pi's own installed TypeSafe System One `classify()` function.
 * Resolution happens from this file's own location so Node's normal
 * node_modules walk-up finds config/pi/node_modules/@earendil-works/pi-ai
 * when this helper is used from inside the dotfiles tree; a
 * JEV_CLASSIFY_MODULE override is available for alternate installs. Never
 * reimplements the wire protocol. Returns null (not a throw) when the
 * package is unavailable, so callers can abstain quietly.
 */
export async function resolveClassifyFn(env = process.env) {
  const override = env.JEV_CLASSIFY_MODULE;
  const specifiers = override ? [override] : ["@earendil-works/pi-ai/api/typesafe-system-one"];
  for (const spec of specifiers) {
    try {
      const mod = await import(spec);
      if (typeof mod.classify === "function") return mod.classify;
    } catch {
      /* try next candidate */
    }
  }
  return null;
}

/**
 * Dispatches one classify call with a hard, enforced timeout. Passes our own
 * AbortController signal to `fn` (the verified real client cancels its
 * `fetch()` on this, see module header); also races against a slightly
 * longer backstop timer so a `classifyFn` that ignores the signal, or that
 * rejects instead of resolving, cannot hang this call past
 * `timeoutMs + grace`. The abandoned original promise always gets a no-op
 * `.catch()` so it can never surface as an unhandled rejection even if it
 * settles after we've already moved on.
 */
async function dispatchWithTimeout(fn, model, context, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const callPromise = Promise.resolve().then(() => fn(model, context, { ...options, signal: controller.signal }));
  callPromise.catch(() => {}); // prevent unhandled rejection if the backstop wins the race
  let backstopTimer;
  const backstop = new Promise((_resolve, reject) => {
    backstopTimer = setTimeout(() => {
      const err = new Error("jev_hard_timeout");
      err.code = "JEV_HARD_TIMEOUT";
      reject(err);
    }, timeoutMs + HARD_TIMEOUT_GRACE_MS);
  });
  try {
    return await Promise.race([callPromise, backstop]);
  } finally {
    clearTimeout(timer);
    clearTimeout(backstopTimer);
  }
}

// ---------------------------------------------------------------------------
// Status (read-only)
// ---------------------------------------------------------------------------

export function getStatus({ env = process.env, fsImpl = fs, configPath = defaultConfigPath(), now = Date.now } = {}) {
  const loaded = loadConfigValidated(configPath, fsImpl);
  const config = loaded.ok ? loaded.config : DEFAULT_CONFIG;
  const modeResult = resolveModeStrict({ env, config });
  const stateDir = defaultStateDir(env);
  const budget = readBudgetSnapshot({ stateDir, fsImpl, now });
  const keyConfigured = resolveApiKey({ env, fsImpl }) != null;
  let cacheEntries = 0;
  try {
    const data = readCacheFile(cachePath(stateDir), fsImpl);
    cacheEntries = Object.keys(data.entries).length;
  } catch {
    cacheEntries = 0;
  }
  const counts = { ok: 0, abstained: 0, error: 0, skipped: 0, cache_hit: 0 };
  try {
    const lines = fsImpl.readFileSync(ledgerPath(stateDir), "utf8").split("\n").filter(Boolean);
    const today = todayUtc(now());
    for (const line of lines) {
      let evt;
      try {
        evt = JSON.parse(line);
      } catch {
        continue;
      }
      if (typeof evt.timestamp === "string" && evt.timestamp.slice(0, 10) === today && counts[evt.status] !== undefined) {
        counts[evt.status] += 1;
      }
    }
  } catch {
    /* no ledger yet */
  }
  return {
    mode: modeResult.mode,
    configValid: loaded.ok,
    configError: loaded.ok ? null : loaded.reason,
    model: config.model,
    rubricVersion: config.rubricVersion,
    keyConfigured,
    budget: {
      date: budget.date,
      calls: budget.calls,
      costUsd: budget.costUsd,
      corrupt: budget.corrupt,
      maxCallsPerDay: config.budget.maxCallsPerDay,
      maxCostPerDayUsd: config.budget.maxCostPerDayUsd,
    },
    today: counts,
    cacheEntries,
  };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Classifies one short task description. Always returns
 * `{ status, applied: false, ... }` and never throws for ordinary
 * failure/skip conditions (missing key, timeout, low confidence, classifier
 * error, budget exceeded, invalid config/mode); callers must not change
 * behavior based on this result beyond optional display/logging.
 */
export async function classifyTask(params = {}) {
  const {
    task,
    source = "delegate",
    env = process.env,
    fsImpl = fs,
    configPath = defaultConfigPath(),
    config: configOverride,
    classifyFn,
    now = Date.now,
    stateDir = defaultStateDir(env),
  } = params;

  const startedAt = now();

  function finish(metaConfig, partial) {
    // Pre-dispatch skips and cache hits never touch the network: their zero
    // usage/cost is genuinely known, not merely absent, so default them to
    // the local "cache" cost_source bucket (reused here for any zero-cost,
    // never-dispatched event per the published ledger-reader contract) and
    // zero token counts. A dispatched request's error/timeout path must keep
    // null/"unknown" -- see the call sites below, which never set a status
    // of "skipped"/"cache_hit" after dispatch, only "error"/"ok"/"abstained".
    const isLocalZero = partial.status === "skipped" || partial.status === "cache_hit";
    const event = {
      schema: SCHEMA_VERSION,
      timestamp: new Date(startedAt).toISOString(),
      source,
      status: partial.status,
      class: partial.class ?? null,
      confidence: typeof partial.confidence === "number" ? partial.confidence : null,
      model: metaConfig.model,
      rubric_version: metaConfig.rubricVersion,
      latency_ms: now() - startedAt,
      input_tokens: partial.input_tokens ?? (isLocalZero ? 0 : null),
      output_tokens: partial.output_tokens ?? (isLocalZero ? 0 : null),
      estimated_cost_usd: typeof partial.estimated_cost_usd === "number" ? partial.estimated_cost_usd : (isLocalZero ? 0 : null),
      cost_source: partial.cost_source ?? (isLocalZero ? "cache" : "unknown"),
      applied: false,
    };
    try {
      appendLedgerEvent(event, { stateDir, fsImpl });
    } catch {
      /* ledger write failures must never block the caller's launch */
    }
    const result = { status: partial.status, applied: false };
    if (partial.reason) result.reason = partial.reason;
    if (partial.class) result.suggestion = partial.class;
    if (typeof partial.confidence === "number") result.confidence = partial.confidence;
    return result;
  }

  // Explicit off always wins, independent of config file validity: an
  // opt-out must work even when the config on disk is broken.
  if (typeof env.PI_JEV_MODE === "string" && env.PI_JEV_MODE.trim().toLowerCase() === "off") {
    return finish(DEFAULT_CONFIG, { status: "skipped", reason: "mode_off" });
  }

  let config;
  if (configOverride) {
    // Tests and other direct callers may inject a config object; it still
    // must pass the same validation a file-loaded config would, so a broken
    // injected config abstains instead of silently running.
    if (!validateConfig(configOverride)) return finish(DEFAULT_CONFIG, { status: "skipped", reason: "config_invalid" });
    config = configOverride;
  } else {
    const loaded = loadConfigValidated(configPath, fsImpl);
    if (!loaded.ok) return finish(DEFAULT_CONFIG, { status: "skipped", reason: loaded.reason });
    config = loaded.config;
  }

  const modeResult = resolveModeStrict({ env, config });
  if (modeResult.mode === "off") return finish(config, { status: "skipped", reason: "mode_off" });
  if (modeResult.mode === "invalid") return finish(config, { status: "skipped", reason: "invalid_mode" });

  if (typeof task !== "string" || task.length === 0) return finish(config, { status: "skipped", reason: "empty_task" });
  if (task.length > MAX_TASK_CHARS) return finish(config, { status: "skipped", reason: "task_too_long" });

  const apiKey = resolveApiKey({ env, fsImpl });
  if (!apiKey) return finish(config, { status: "skipped", reason: "missing_key" });

  const cacheKey = hashCacheKey({ task, rubricVersion: config.rubricVersion, model: config.model, minConfidence: config.minConfidence, classes: config.classes });
  let cacheHit = null;
  try {
    cacheHit = getCacheEntry(cacheKey, { stateDir, fsImpl, now });
  } catch {
    cacheHit = null;
  }
  if (cacheHit) {
    return finish(config, { status: "cache_hit", class: cacheHit.class, confidence: cacheHit.confidence, cost_source: "cache", estimated_cost_usd: 0 });
  }

  const reservedCostUsd = reservedCostForConfig(config);
  let reservation;
  try {
    reservation = reserveBudget({ stateDir, fsImpl, now, caps: config.budget, reservedCostUsd });
  } catch {
    return finish(config, { status: "skipped", reason: "budget_unavailable" });
  }
  if (!reservation.allowed) return finish(config, { status: "skipped", reason: reservation.reason });

  const fn = classifyFn || (await resolveClassifyFn(env));
  if (!fn) {
    // No request was ever dispatched: safe to release the reservation in full.
    reservation.release();
    return finish(config, { status: "skipped", reason: "classifier_unavailable" });
  }

  let result;
  try {
    result = await dispatchWithTimeout(
      fn,
      jevModel(config),
      { state: { task }, questions: questionsFor(config.classes) },
      { apiKey, maxRetries: 0 },
      config.timeoutMs,
    );
  } catch (err) {
    // A request may have been dispatched and possibly billed even though we
    // never saw a response (timeout) or the call rejected unexpectedly: keep
    // the reservation as the final conservative cost, do not refund it.
    const timedOut = err && err.code === "JEV_HARD_TIMEOUT";
    return finish(config, { status: "error", reason: timedOut ? "timeout" : "classifier_error" });
  }

  if (result?.stopReason !== "stop") {
    // The request was dispatched; an error/aborted stopReason does not prove
    // zero cost, so usage is deliberately not trusted here even if present.
    // Reservation is left in place (no release, no settle).
    const reason = result?.stopReason === "aborted" ? "timeout" : "classifier_error";
    return finish(config, { status: "error", reason });
  }

  const answer = result.answers?.task_class;
  const validClass = typeof answer?.choice === "string" && config.classes.includes(answer.choice);
  const validConfidence = typeof answer?.confidence === "number" && Number.isFinite(answer.confidence) && answer.confidence >= 0 && answer.confidence <= 1;
  if (!answer || answer.type !== "choice" || !validClass || !validConfidence) {
    // Malformed/unexpected answer shape from an otherwise "successful" call:
    // still don't trust any usage figure attached to it. Leave reservation.
    return finish(config, { status: "error", reason: "unexpected_answer" });
  }

  // From here the call genuinely succeeded with a validated answer: usage
  // (if reported) is trustworthy and can be settled against the reservation.
  const usage = result.usage;
  const actualCost = typeof usage?.input === "number" && Number.isFinite(usage.input) ? (usage.input / 1_000_000) * config.costPerMillionInputUsd : null;
  try {
    reservation.settle(actualCost ?? reservedCostUsd);
  } catch {
    /* accounting drift here never blocks the result */
  }
  const usageFields = {
    input_tokens: typeof usage?.input === "number" ? usage.input : null,
    output_tokens: typeof usage?.output === "number" ? usage.output : null,
    estimated_cost_usd: actualCost,
    cost_source: actualCost != null ? "published-rate" : "unknown",
  };

  if (!(answer.confidence >= config.minConfidence)) {
    return finish(config, { status: "abstained", reason: "low_confidence", confidence: answer.confidence, ...usageFields });
  }

  try {
    setCacheEntry(cacheKey, { class: answer.choice, confidence: answer.confidence }, { stateDir, fsImpl, now, ttlSeconds: config.cache.ttlSeconds, maxEntries: config.cache.maxEntries });
  } catch {
    /* cache write failures must never block the result */
  }

  return finish(config, { status: "ok", class: answer.choice, confidence: answer.confidence, ...usageFields });
}
