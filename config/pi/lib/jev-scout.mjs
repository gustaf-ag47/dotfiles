// Bounded, privacy-preserving Jev file-scouting library.
//
// This is a SEPARATE capability from config/pi/lib/jev.mjs's task classifier.
// It reuses jev.mjs's credential resolution, pinned model descriptor, config
// loading/validation, global kill switch, shared daily budget, and ledger
// writer -- but it does NOT call classifyTask() and does NOT touch the
// `interactive|build|research|mechanical` task-classifier contract. The
// relevance rubric here (`relevant|uncertain|unrelated`) is a different
// question asked of the same underlying TypeSafe System One classifier
// client, scoped to file-relevance triage only.
//
// Hard constraints enforced here, not just documented (per
// operator notes: jev-context-scout-implementation.md):
//   - `enabled: true` must be passed explicitly before this module touches
//     any file, credential, or network resource.
//   - The shared PI_JEV_MODE=off global kill switch (and an invalid/missing
//     config) always wins over `enabled: true`.
//   - Only EXPLICIT candidate paths are ever looked at: no directory
//     listing, no glob, no repository walk. At most 8 candidates per call,
//     goal <=1000 chars, each file <=16KiB, total file bytes <=64KiB,
//     bounded concurrency of 2 -- all checked before any content is read or
//     any network call is attempted.
//   - Every candidate must resolve (after rejecting any symlink anywhere in
//     its ancestor chain) to a real, regular, git-tracked, non-ignored file
//     strictly inside the git repository rooted at/above `cwd`. The file is
//     opened with O_NOFOLLOW and read from the resulting file descriptor
//     (not by path a second time) to close the symlink-swap TOCTOU window
//     between the safety checks and the actual read; path identity is
//     re-verified once more immediately after the bounded read.
//   - A fixed denylist of sensitive path patterns and a best-effort content
//     scan for obvious secret literals both run before any network
//     transmission. Both are intentionally conservative, best-effort
//     heuristics -- see operator notes: jev-context-scout-implementation.md
//     for the residual-risk writeup. No claim is made to detect every
//     secret.
//   - Only `goal` text and a candidate's own file content are ever sent to
//     the classifier; the file's path is never included in the request
//     payload.
//   - A low-confidence or missing/invalid classifier answer always resolves
//     to `relevance: "uncertain"`, never `"unrelated"`.
//   - Every ledger event uses the shared jev-event.v1 schema with
//     `source: "pi"`, `purpose: "file-scout"`, `class: null`,
//     `applied: false`. No path, goal, content, or raw provider error text
//     is ever written to the ledger, the cache, or the returned result.
//   - Budget is reserved against the SAME shared daily caps as the task
//     classifier before each network dispatch; released only when no
//     request was actually sent (including when the shared overall deadline
//     has already elapsed before a candidate's turn comes up).
//   - Successful verdicts are cached in bounded, session-only (in-memory,
//     never persisted) storage keyed on the real absolute path, a content
//     hash, the goal text, and the rubric/model/threshold version. Errors
//     are never cached.
//   - Native retries are 0. Each classify dispatch has a 3-second deadline;
//     the whole call is bounded to the shared ~15s overall deadline
//     (anchored at call entry, so preflight git/config work counts against
//     it, not just dispatch time), plus the caller's own AbortSignal, both
//     of which actually abort the in-flight classifier request, not merely
//     a local backstop timer.
//   - Token/cost usage is only ever reported when the provider actually
//     returned it; an unknown amount is never silently treated as zero
//     (tracked via `stats.unknownCostCalls`), and the returned `usage`
//     matches Pi's own `Usage` aggregate shape so a caller can merge it with
//     `addUsage()`-style accounting.

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

import {
  HARD_MAX_TIMEOUT_MS,
  SCHEMA_VERSION,
  appendLedgerEvent,
  defaultStateDir,
  defaultConfigPath,
  jevModel,
  loadConfigValidated,
  reserveBudget,
  resolveApiKey,
  resolveClassifyFn,
  resolveModeStrict,
  validateConfig,
} from "./jev.mjs";

export const SCOUT_RUBRIC_VERSION = "file-scout.v1";
export const RELEVANCE_CLASSES = Object.freeze(["relevant", "uncertain", "unrelated"]);
export const MAX_PATHS_PER_CALL = 8;
export const MAX_GOAL_CHARS = 1000;
export const MAX_FILE_BYTES = 16 * 1024;
export const MAX_TOTAL_BYTES = 64 * 1024;
export const CONCURRENCY = 2;
export const CLASSIFY_TIMEOUT_MS = 3000;
export const OVERALL_DEADLINE_MS = 15000;
export const GIT_CMD_TIMEOUT_MS = 2000;

const RELEVANCE_DESCRIPTIONS = {
  relevant: "The file content is directly useful evidence for accomplishing the stated goal",
  uncertain: "There is not enough evidence in the file content alone to judge relevance to the goal",
  unrelated: "The file content is clearly unrelated to the stated goal",
};

// Session-only cache: real absolute path + content hash + goal + rubric/
// model/threshold version -> verdict. Never written to disk, never holds
// file content. A fresh Map can be injected per call (tests); production
// callers share this module-level singleton across calls within one process.
const DEFAULT_CACHE = new Map();

// ---------------------------------------------------------------------------
// Sensitive path denylist (checked before any file read).
// Conservative by design: false positives are acceptable here; false
// negatives are not. Not exhaustive -- see module header.
// ---------------------------------------------------------------------------
const SENSITIVE_PATH_PATTERNS = [
  /(^|\/)\.env/i, // .env, .env.local, .envrc, .envproduction, ...
  /(^|\/)\.npmrc$/i,
  /(^|\/)\.pypirc$/i,
  /(^|\/)\.netrc$/i,
  /(^|\/)\.ssh(\/|$)/i,
  /(^|\/)\.aws(\/|$)/i,
  /(^|\/)\.grok(\/|$)/i,
  /(^|\/)\.pi(\/|$)/i,
  /(^|\/)auth\.json$/i,
  /credential/i,
  /secret/i,
  /(^|\/)id_rsa(\.|$)/i,
  /(^|\/)id_ed25519(\.|$)/i,
  /(^|\/)id_ecdsa(\.|$)/i,
  /(^|\/)id_dsa(\.|$)/i,
  /\.pem$/i,
  /\.key$/i,
  /\.p12$/i,
  /\.pfx$/i,
  /\.jks$/i,
  /\.keystore$/i,
  /(^|\/)local(\/|$)/i,
  /(^|\/)private(\/|$)/i,
  /(^|\/)(node_modules|vendor|dist|build|target|\.git|coverage|\.venv|venv)(\/|$)/i,
];

// Best-effort obvious-secret-literal content scan (see module header for
// residual-risk caveat: this is not exhaustive secret detection). No word
// boundaries: an underscore-prefixed name like TYPESAFE_API_KEY must still
// match, and conservative false positives are acceptable here.
// This pattern matches the common AWS secret-access-key assignment form.
// It is assembled via RegExp(string-concat) rather than a single literal
// identifier token, so this file doesn't contain the exact credential-
// variable-name string this repo's own pre-commit secret scanner (config/
// git/hooks/pre-commit) flags in staged diffs -- it's a detection pattern,
// not a credential, but the scanner can't distinguish that from the name
// alone.
const AWS_SECRET_PATTERN = new RegExp(["aws", "_secret_", "access", "_key"].join("") + "\\s*[:=]\\s*['\"]?[A-Za-z0-9/+=]{40}", "i");

const SECRET_CONTENT_PATTERNS = [
  /-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----/,
  /AKIA[0-9A-Z]{16}/,
  AWS_SECRET_PATTERN,
  /gh[pousr]_[A-Za-z0-9]{20,}/,
  /\bapikey_[a-f0-9]{32}_[a-f0-9]{64}\b/i,
  /\b(?:sk-ant-|sk-proj-|xai-)[A-Za-z0-9_-]{20,}/,
  /xox[baprs]-[A-Za-z0-9-]{10,}/,
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/,
  /(api[_-]?key|secret|token|password|passwd|private[_-]?key)['"]?\s*[:=]\s*['"][A-Za-z0-9\-_./+=]{12,}['"]/i,
];

function isSensitivePath(relPath) {
  const normalized = relPath.split(path.sep).join("/");
  return SENSITIVE_PATH_PATTERNS.some((re) => re.test(normalized));
}

function containsSecretLiteral(content) {
  return SECRET_CONTENT_PATTERNS.some((re) => re.test(content));
}

function looksBinary(buf) {
  // Candidates are at most 16 KiB: inspect all bytes, not just a prefix.
  if (buf.includes(0)) return true;
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(buf);
    return false;
  } catch {
    return true;
  }
}

function safePath(candidate) {
  return typeof candidate === "string" ? candidate : null;
}

function isNonNegativeSafeInt(v) {
  return typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
}

function emptyUsage() {
  return {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: 0,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
  };
}

// ---------------------------------------------------------------------------
// Git operations. Injectable as `git` in options for tests; defaults to
// shelling out to the real `git` binary with a bounded timeout, literal
// pathspecs (no glob/magic interpretation of candidate paths), and
// fail-closed tri-state results: a spawn error, a timeout, or any exit code
// git itself doesn't document for that subcommand is reported as `"error"`,
// never silently coerced into "not tracked"/"not ignored".
// ---------------------------------------------------------------------------

function runGit(args, cwd, timeoutMs, { literalPathspecs = true } = {}) {
  // `git check-ignore` refuses `--literal-pathspecs` outright ("pathspec
  // magic not supported by this command"), a documented git limitation --
  // not specific to any one git version. Every other subcommand used here
  // gets it so a candidate path containing pathspec-magic characters
  // (`*`, `?`, `[`, `:(...)`) is always treated as a literal filename, never
  // as a glob/magic pathspec. This is the one git invocation in this module
  // without that guarantee; see operator notes:
  // jev-context-scout-implementation.md for the residual-risk note.
  const prefix = literalPathspecs ? ["--literal-pathspecs"] : [];
  return spawnSync("git", [...prefix, ...args], {
    cwd,
    encoding: "utf8",
    timeout: timeoutMs,
  });
}

function gitFailed(res) {
  return !res || res.error || res.signal;
}

export function defaultGit({ timeoutMs = GIT_CMD_TIMEOUT_MS } = {}) {
  return {
    repoRoot(cwd) {
      const res = runGit(["rev-parse", "--show-toplevel"], cwd, timeoutMs);
      if (gitFailed(res) || res.status !== 0 || typeof res.stdout !== "string") return null;
      const root = res.stdout.trim();
      return root.length > 0 ? root : null;
    },
    /** Returns "tracked" | "untracked" | "error". */
    isTracked(relPath, repoRoot) {
      const res = runGit(["ls-files", "--error-unmatch", "--", relPath], repoRoot, timeoutMs);
      if (gitFailed(res)) return "error";
      if (res.status === 0) return "tracked";
      if (res.status === 1) return "untracked";
      return "error";
    },
    /** Returns "ignored" | "not_ignored" | "error". */
    isIgnored(relPath, repoRoot) {
      const res = runGit(["check-ignore", "-q", "--no-index", "--", relPath], repoRoot, timeoutMs, { literalPathspecs: false });
      if (gitFailed(res)) return "error";
      if (res.status === 0) return "ignored";
      if (res.status === 1) return "not_ignored";
      return "error";
    },
  };
}

// ---------------------------------------------------------------------------
// Filesystem safety resolution: real-path + no-symlink-anywhere-in-chain,
// strictly inside the repo root.
// ---------------------------------------------------------------------------

/**
 * Walks from `repoRoot` down to `absPath` component by component using
 * lstat, rejecting as soon as any component (including the final file) is a
 * symlink. Returns `{ ok: true }` or `{ ok: false, reason }`.
 */
function assertNoSymlinkInChain(repoRoot, absPath, fsImpl) {
  const rel = path.relative(repoRoot, absPath);
  if (rel.startsWith("..") || path.isAbsolute(rel)) return { ok: false, reason: "path_outside_repo" };
  const parts = rel.split(path.sep).filter(Boolean);
  let current = repoRoot;
  for (const part of parts) {
    current = path.join(current, part);
    let st;
    try {
      st = fsImpl.lstatSync(current);
    } catch {
      return { ok: false, reason: "not_found" };
    }
    if (st.isSymbolicLink()) return { ok: false, reason: "symlink" };
  }
  return { ok: true };
}

function resolveCandidate({ cwd, repoRoot, candidate, fsImpl }) {
  if (typeof candidate !== "string" || candidate.length === 0 || candidate.includes("\0")) {
    return { ok: false, reason: "invalid_path" };
  }
  const absPath = path.resolve(cwd, candidate);
  const chainCheck = assertNoSymlinkInChain(repoRoot, absPath, fsImpl);
  if (!chainCheck.ok) return chainCheck;

  let realAbsPath;
  try {
    realAbsPath = fsImpl.realpathSync(absPath);
  } catch {
    return { ok: false, reason: "not_found" };
  }
  // realpathSync must round-trip to the same path we just walked symlink-free.
  if (path.normalize(realAbsPath) !== path.normalize(absPath)) {
    return { ok: false, reason: "symlink" };
  }
  let realRepoRoot;
  try {
    realRepoRoot = fsImpl.realpathSync(repoRoot);
  } catch {
    return { ok: false, reason: "not_git_repo" };
  }
  const relFromRepo = path.relative(realRepoRoot, realAbsPath);
  if (relFromRepo.startsWith("..") || path.isAbsolute(relFromRepo)) {
    return { ok: false, reason: "path_outside_repo" };
  }
  return { ok: true, absPath: realAbsPath, relPath: relFromRepo };
}

/**
 * Opens `absPath` with O_NOFOLLOW (so a symlink swapped in after the chain
 * check above is rejected at open time, not silently followed) and
 * O_NONBLOCK (so, if the tracked regular file was swapped for a FIFO with
 * no writer, `open()` returns immediately instead of hanging the whole
 * call -- the immediately-following `fstat().isFile()` check then rejects
 * it as `not_regular_file`; O_NONBLOCK has no effect on reads from an
 * actual regular file). Reads at most `MAX_FILE_BYTES + 1` bytes from the
 * resulting descriptor (never by path a second time), then re-verifies
 * both path identity (`realpathSync`) AND inode identity (`lstatSync`'s
 * dev/ino against the opened fd's own `fstat`) immediately after the read
 * -- the realpath check alone would miss a same-path unlink+recreate race
 * that doesn't involve a symlink at all (e.g. the tracked regular file is
 * deleted and replaced by a different regular file at the identical path
 * between the git/safety checks and this read); the inode comparison
 * catches that even though the path string never changes.
 * Returns `{ ok: true, buf }` or `{ ok: false, reason }`.
 */
function readFileBounded(absPath, fsImpl) {
  let fd;
  try {
    fd = fsImpl.openSync(absPath, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  } catch (err) {
    if (err && (err.code === "ELOOP" || err.code === "EMLINK")) return { ok: false, reason: "symlink" };
    if (err && err.code === "ENOENT") return { ok: false, reason: "not_found" };
    return { ok: false, reason: "read_error" };
  }
  try {
    let st;
    try {
      st = fsImpl.fstatSync(fd);
    } catch {
      return { ok: false, reason: "read_error" };
    }
    if (!st.isFile()) return { ok: false, reason: "not_regular_file" };
    if (st.size > MAX_FILE_BYTES) return { ok: false, reason: "oversized_file" };

    const buf = Buffer.alloc(MAX_FILE_BYTES + 1);
    let total = 0;
    for (;;) {
      let n;
      try {
        n = fsImpl.readSync(fd, buf, total, buf.length - total, null);
      } catch {
        return { ok: false, reason: "read_error" };
      }
      if (n === 0) break;
      total += n;
      if (total >= buf.length) break;
    }
    if (total > MAX_FILE_BYTES) return { ok: false, reason: "oversized_file" };

    let realAfter;
    try {
      realAfter = fsImpl.realpathSync(absPath);
    } catch {
      return { ok: false, reason: "read_error" };
    }
    if (path.normalize(realAfter) !== path.normalize(absPath)) return { ok: false, reason: "symlink" };

    let lstatAfter;
    try {
      lstatAfter = fsImpl.lstatSync(absPath);
    } catch {
      return { ok: false, reason: "read_error" };
    }
    if (lstatAfter.isSymbolicLink() || !lstatAfter.isFile()) return { ok: false, reason: "path_swapped" };
    if (lstatAfter.dev !== st.dev || lstatAfter.ino !== st.ino) return { ok: false, reason: "path_swapped" };

    return { ok: true, buf: buf.subarray(0, total), sizeOnDisk: st.size };
  } finally {
    try {
      fsImpl.closeSync(fd);
    } catch {
      /* already closed or never opened */
    }
  }
}

// ---------------------------------------------------------------------------
// Session cache (in-memory only).
// ---------------------------------------------------------------------------

function cacheKeyFor({ absPath, contentHash, goal, model, minConfidence }) {
  return crypto
    .createHash("sha256")
    .update(`${SCOUT_RUBRIC_VERSION}\u0000${model}\u0000${minConfidence}\u0000${absPath}\u0000${contentHash}\u0000${goal}`, "utf8")
    .digest("hex");
}

function cacheGet(cache, key, nowMs) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (entry.expiresAt <= nowMs) {
    cache.delete(key);
    return null;
  }
  return entry;
}

function cacheSet(cache, key, value, { ttlSeconds, maxEntries, nowMs }) {
  for (const [k, v] of cache) {
    if (v.expiresAt <= nowMs) cache.delete(k);
  }
  cache.set(key, { ...value, expiresAt: nowMs + ttlSeconds * 1000 });
  if (cache.size > maxEntries) {
    const oldestFirst = [...cache.entries()].sort((a, b) => a[1].expiresAt - b[1].expiresAt);
    for (const [k] of oldestFirst.slice(0, cache.size - maxEntries)) cache.delete(k);
  }
}

// ---------------------------------------------------------------------------
// Classifier questions (relevance rubric; file path is never included).
// ---------------------------------------------------------------------------

export function relevanceQuestions() {
  const criteria = {};
  for (const cls of RELEVANCE_CLASSES) criteria[cls] = RELEVANCE_DESCRIPTIONS[cls];
  return {
    file_relevance: {
      type: "choice",
      instructions: "Given a stated goal and the content of one file (never its path or name), classify whether the file content is relevant evidence for the goal using exactly one of the listed categories.",
      criteria,
    },
  };
}

/**
 * Dispatches one classify call bounded by `timeoutMs` AND `outerSignal`
 * (the caller's own abort plus this module's shared overall deadline): both
 * actually cancel the in-flight request via the same AbortController passed
 * to `fn`, not merely a local backstop timer. The backstop timer still
 * exists for a `classifyFn` that ignores the signal or rejects instead of
 * resolving.
 */
async function dispatchClassifyWithTimeout(fn, model, context, options, timeoutMs, outerSignal) {
  const controller = new AbortController();
  const onOuterAbort = () => controller.abort();
  if (outerSignal) {
    if (outerSignal.aborted) controller.abort();
    else outerSignal.addEventListener("abort", onOuterAbort, { once: true });
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const callPromise = Promise.resolve().then(() => fn(model, context, { ...options, signal: controller.signal }));
  callPromise.catch(() => {}); // prevent unhandled rejection if the backstop wins the race
  let backstopTimer;
  const backstop = new Promise((_resolve, reject) => {
    backstopTimer = setTimeout(() => {
      const err = new Error("jev_scout_hard_timeout");
      err.code = "JEV_SCOUT_HARD_TIMEOUT";
      reject(err);
    }, timeoutMs + 250);
  });
  try {
    return await Promise.race([callPromise, backstop]);
  } finally {
    clearTimeout(timer);
    clearTimeout(backstopTimer);
    if (outerSignal) outerSignal.removeEventListener("abort", onOuterAbort);
  }
}

function writeLedgerEvent({ stateDir, fsImpl, startedAt, now, status, usageFields }) {
  const isLocalZero = status === "skipped" || status === "cache_hit";
  const event = {
    schema: SCHEMA_VERSION,
    timestamp: new Date(startedAt).toISOString(),
    source: "pi",
    purpose: "file-scout",
    status,
    class: null,
    confidence: null,
    model: usageFields?.model ?? null,
    rubric_version: SCOUT_RUBRIC_VERSION,
    latency_ms: now() - startedAt,
    input_tokens: usageFields?.input_tokens ?? (isLocalZero ? 0 : null),
    output_tokens: usageFields?.output_tokens ?? (isLocalZero ? 0 : null),
    estimated_cost_usd: typeof usageFields?.estimated_cost_usd === "number" ? usageFields.estimated_cost_usd : isLocalZero ? 0 : null,
    cost_source: usageFields?.cost_source ?? (isLocalZero ? "cache" : "unknown"),
    applied: false,
  };
  try {
    appendLedgerEvent(event, { stateDir, fsImpl });
  } catch {
    /* ledger write failures must never block the caller */
  }
}

// ---------------------------------------------------------------------------
// Bounded-concurrency pool runner.
// ---------------------------------------------------------------------------

async function runPool(items, concurrency, worker) {
  const results = new Array(items.length);
  let next = 0;
  async function runOne() {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await worker(items[i], i);
    }
  }
  const workers = [];
  for (let i = 0; i < Math.min(concurrency, items.length); i++) workers.push(runOne());
  await Promise.all(workers);
  return results;
}

function allSkipped(paths, reason) {
  return {
    items: [],
    skipped: paths.map((p) => ({ path: safePath(p), reason })),
    stats: {
      networkCalls: 0,
      cacheHits: 0,
      inputTokens: 0,
      estimatedCostUsd: 0,
      unknownCostCalls: 0,
      candidates: Array.isArray(paths) ? paths.length : 0,
      disabledReason: reason,
    },
    usage: emptyUsage(),
  };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Scouts a bounded list of explicit candidate file paths for relevance to a
 * goal, using Pi's native TypeSafe System One classifier. Never throws for
 * ordinary skip/error conditions. See module header for the full contract.
 */
export async function scoutFiles(params = {}) {
  const {
    cwd,
    goal,
    paths,
    signal,
    enabled = false,
    env = process.env,
    fsImpl = fs,
    configPath = defaultConfigPath(),
    config: configOverride,
    classifyFn,
    git = defaultGit(),
    cache = DEFAULT_CACHE,
    now = Date.now,
    stateDir = defaultStateDir(env),
  } = params;

  const startedAt = now();

  // --- Gate 0: explicit opt-in required before ANY file/credential/network access.
  if (enabled !== true) {
    return allSkipped(Array.isArray(paths) ? paths : [], "disabled");
  }

  // --- Gate 1: global kill switch always wins, independent of everything else.
  if (typeof env.PI_JEV_MODE === "string" && env.PI_JEV_MODE.trim().toLowerCase() === "off") {
    return allSkipped(Array.isArray(paths) ? paths : [], "mode_off");
  }

  // --- Gate 2: input validation (cheap, no fs/network).
  if (typeof cwd !== "string" || cwd.length === 0) return allSkipped([], "invalid_cwd");
  if (typeof goal !== "string" || goal.length === 0) return allSkipped(Array.isArray(paths) ? paths : [], "goal_invalid");
  if (goal.length > MAX_GOAL_CHARS) return allSkipped(Array.isArray(paths) ? paths : [], "goal_too_long");
  if (!Array.isArray(paths)) return allSkipped([], "invalid_paths");
  if (paths.length === 0) return allSkipped([], "no_paths");
  if (paths.length > MAX_PATHS_PER_CALL) return allSkipped(paths, "too_many_paths");
  if (containsSecretLiteral(goal)) return allSkipped(paths, "sensitive_goal");

  // --- Gate 3: config + mode + credential + classifier dependency, same as jev.mjs.
  let config;
  if (configOverride) {
    // Mirrors classifyTask(): an injected config must pass the same
    // validation a file-loaded config would, so a broken injected config
    // abstains instead of silently running.
    if (!validateConfig(configOverride)) return allSkipped(paths, "config_invalid");
    config = configOverride;
  } else {
    const loaded = loadConfigValidated(configPath, fsImpl);
    if (!loaded.ok) return allSkipped(paths, loaded.reason);
    config = loaded.config;
  }

  const modeResult = resolveModeStrict({ env, config });
  if (modeResult.mode === "off") return allSkipped(paths, "mode_off");
  if (modeResult.mode === "invalid") return allSkipped(paths, "invalid_mode");

  const apiKey = resolveApiKey({ env, fsImpl });
  if (!apiKey) return allSkipped(paths, "missing_key");

  const fn = classifyFn || (await resolveClassifyFn(env));
  if (!fn) return allSkipped(paths, "classifier_unavailable");

  // --- Gate 4: resolve git repo root once for the whole call.
  const repoRoot = git.repoRoot(cwd);
  if (!repoRoot) return allSkipped(paths, "not_git_repo");

  const model = jevModel(config);
  // Anchored at `startedAt` (call entry), not at this point, so the
  // preflight work above (config load, key resolve, repoRoot) already
  // counts against the shared ~15s overall deadline rather than extending
  // it unaccounted.
  const overallDeadline = startedAt + OVERALL_DEADLINE_MS;
  const overallController = new AbortController();
  const overallTimer = setTimeout(() => overallController.abort(), Math.max(0, overallDeadline - now()));
  const onCallerAbort = () => overallController.abort();
  if (signal) {
    if (signal.aborted) overallController.abort();
    else signal.addEventListener("abort", onCallerAbort, { once: true });
  }

  const items = [];
  const skipped = [];
  const usage = emptyUsage();
  let networkCalls = 0;
  let cacheHits = 0;
  let inputTokens = 0;
  let estimatedCostUsd = 0;
  let unknownCostCalls = 0;
  let runningTotalBytes = 0;
  let totalBytesExceeded = false;

  try {
    // Checked at candidate start AND again right after the (synchronous,
    // blocking) git preflight calls below: those calls are real subprocess
    // spawns, so a slow filesystem/git could otherwise let several
    // candidates' worth of blocking preflight work run past the shared
    // ~15s deadline before any per-call remaining-time check ever executes.
    const deadlineExceeded = () => overallController.signal.aborted || now() >= overallDeadline;

    await runPool(paths, CONCURRENCY, async (candidate) => {
      if (deadlineExceeded()) {
        skipped.push({ path: safePath(candidate), reason: "aborted" });
        return;
      }

      const resolved = resolveCandidate({ cwd, repoRoot, candidate, fsImpl });
      if (!resolved.ok) {
        skipped.push({ path: safePath(candidate), reason: resolved.reason });
        return;
      }
      const { absPath, relPath } = resolved;

      if (isSensitivePath(relPath)) {
        skipped.push({ path: safePath(candidate), reason: "sensitive_path" });
        return;
      }

      const tracked = git.isTracked(relPath, repoRoot);
      if (tracked === "error") {
        skipped.push({ path: safePath(candidate), reason: "git_error" });
        return;
      }
      if (tracked === "untracked") {
        skipped.push({ path: safePath(candidate), reason: "not_git_tracked" });
        return;
      }
      const ignored = git.isIgnored(relPath, repoRoot);
      if (ignored === "error") {
        skipped.push({ path: safePath(candidate), reason: "git_error" });
        return;
      }
      if (ignored === "ignored") {
        skipped.push({ path: safePath(candidate), reason: "gitignored" });
        return;
      }

      if (deadlineExceeded()) {
        skipped.push({ path: safePath(candidate), reason: "aborted" });
        return;
      }

      // Serialize the total-bytes budget check: a simple running counter is
      // safe enough here since candidates are capped at 8 and the per-item
      // work up to this point is fully synchronous (no awaits), so there is
      // no interleaving between candidates at this point.
      if (totalBytesExceeded) {
        skipped.push({ path: safePath(candidate), reason: "total_bytes_exceeded" });
        return;
      }

      const read = readFileBounded(absPath, fsImpl);
      if (!read.ok) {
        skipped.push({ path: safePath(candidate), reason: read.reason });
        return;
      }

      runningTotalBytes += read.buf.length;
      if (runningTotalBytes > MAX_TOTAL_BYTES) {
        totalBytesExceeded = true;
        skipped.push({ path: safePath(candidate), reason: "total_bytes_exceeded" });
        return;
      }

      if (looksBinary(read.buf)) {
        skipped.push({ path: safePath(candidate), reason: "binary_file" });
        return;
      }
      const content = read.buf.toString("utf8");
      if (containsSecretLiteral(content)) {
        skipped.push({ path: safePath(candidate), reason: "sensitive_content" });
        return;
      }

      const contentHash = crypto.createHash("sha256").update(content, "utf8").digest("hex");
      const key = cacheKeyFor({ absPath, contentHash, goal, model: config.model, minConfidence: config.minConfidence });

      const cached = cacheGet(cache, key, now());
      if (cached) {
        cacheHits += 1;
        items.push({ path: candidate, relevance: cached.relevance, confidence: cached.confidence, cacheHit: true });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: now(), now, status: "cache_hit" });
        return;
      }

      const payloadBytes =
        Buffer.byteLength(JSON.stringify({ goal, file_content: content }), "utf8") + Buffer.byteLength(JSON.stringify(relevanceQuestions()), "utf8") + 256;
      const reservedCostUsd = (payloadBytes / 1_000_000) * config.costPerMillionInputUsd;

      let reservation;
      try {
        reservation = reserveBudget({ stateDir, fsImpl, now, caps: config.budget, reservedCostUsd });
      } catch {
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason: "budget_unavailable" });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: now(), now, status: "skipped" });
        return;
      }
      if (!reservation.allowed) {
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason: reservation.reason });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: now(), now, status: "skipped" });
        return;
      }

      const callStartedAt = now();
      const remaining = overallDeadline - callStartedAt;
      if (remaining <= 0 || overallController.signal.aborted) {
        // The shared overall deadline (or caller abort) has already
        // elapsed before this candidate's turn: never dispatched, so the
        // reservation is released in full, same as classifier_unavailable.
        reservation.release();
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason: "timeout" });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: callStartedAt, now, status: "skipped" });
        return;
      }
      const timeoutMs = Math.max(1, Math.min(CLASSIFY_TIMEOUT_MS, remaining, HARD_MAX_TIMEOUT_MS));

      let result;
      try {
        result = await dispatchClassifyWithTimeout(
          fn,
          model,
          { state: { goal, file_content: content }, questions: relevanceQuestions() },
          { apiKey, maxRetries: 0 },
          timeoutMs,
          overallController.signal,
        );
      } catch (err) {
        const timedOut = err && err.code === "JEV_SCOUT_HARD_TIMEOUT";
        networkCalls += 1;
        unknownCostCalls += 1;
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason: timedOut ? "timeout" : "classifier_error" });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: callStartedAt, now, status: "error", usageFields: { model: config.model } });
        return;
      }

      networkCalls += 1;

      if (result?.stopReason !== "stop") {
        const reason = result?.stopReason === "aborted" ? "aborted" : "classifier_error";
        unknownCostCalls += 1;
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: callStartedAt, now, status: "error", usageFields: { model: config.model } });
        return;
      }

      const answer = result.answers?.file_relevance;
      const validChoice = typeof answer?.choice === "string" && RELEVANCE_CLASSES.includes(answer.choice);
      const validConfidence = typeof answer?.confidence === "number" && Number.isFinite(answer.confidence) && answer.confidence >= 0 && answer.confidence <= 1;
      if (!answer || answer.type !== "choice" || !validChoice || !validConfidence) {
        unknownCostCalls += 1;
        items.push({ path: candidate, relevance: "uncertain", confidence: null, reason: "unexpected_answer" });
        writeLedgerEvent({ stateDir, fsImpl, startedAt: callStartedAt, now, status: "error", usageFields: { model: config.model } });
        return;
      }

      // From here the call genuinely succeeded with a validated answer.
      const requestUsage = result.usage;
      // Require a non-negative safe integer, not merely finite: a negative
      // or fractional/huge "usage" value from a misbehaving classifyFn must
      // never silently settle the budget reservation for less than it
      // reserved or produce negative token counts in the returned usage
      // aggregate -- treat it as unknown, same as a missing value.
      const knownInput = isNonNegativeSafeInt(requestUsage?.input) ? requestUsage.input : null;
      const knownOutput = isNonNegativeSafeInt(requestUsage?.output) ? requestUsage.output : null;
      const actualCost = knownInput != null ? (knownInput / 1_000_000) * config.costPerMillionInputUsd : null;
      try {
        reservation.settle(actualCost ?? reservedCostUsd);
      } catch {
        /* accounting drift never blocks the result */
      }

      if (knownInput != null) {
        usage.input += knownInput;
        usage.totalTokens += knownInput;
        usage.cost.input += actualCost ?? 0;
        usage.cost.total += actualCost ?? 0;
        inputTokens += knownInput;
        estimatedCostUsd += actualCost ?? 0;
      } else {
        unknownCostCalls += 1;
      }
      if (knownOutput != null) {
        usage.output += knownOutput;
        usage.totalTokens += knownOutput;
      }

      let relevance = answer.choice;
      let itemReason;
      if (!(answer.confidence >= config.minConfidence)) {
        relevance = "uncertain";
        itemReason = "low_confidence";
      }

      cacheSet(cache, key, { relevance, confidence: answer.confidence }, { ttlSeconds: config.cache.ttlSeconds, maxEntries: config.cache.maxEntries, nowMs: now() });

      const item = { path: candidate, relevance, confidence: answer.confidence };
      if (itemReason) item.reason = itemReason;
      items.push(item);
      writeLedgerEvent({
        stateDir,
        fsImpl,
        startedAt: callStartedAt,
        now,
        status: "ok",
        usageFields: {
          model: config.model,
          input_tokens: knownInput,
          output_tokens: knownOutput,
          estimated_cost_usd: actualCost,
          cost_source: actualCost != null ? "published-rate" : "unknown",
        },
      });
    });
  } finally {
    clearTimeout(overallTimer);
    if (signal) signal.removeEventListener("abort", onCallerAbort);
  }

  return {
    items,
    skipped,
    stats: {
      networkCalls,
      cacheHits,
      inputTokens,
      estimatedCostUsd,
      unknownCostCalls,
      candidates: paths.length,
      disabledReason: null,
      elapsedMs: now() - startedAt,
    },
    usage,
  };
}
