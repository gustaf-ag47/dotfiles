// Pure, dependency-injectable cache/state helpers for the Jev context extension
// (config/pi/extensions/jev-context.ts). No Pi API imports here, no network, no
// classifier calls -- only hashing, bookkeeping, and formatting so this module
// is unit-testable without a running Pi session.
//
// Retention contract this module exists to enforce (full writeup in
// operator notes: jev-context-extension-implementation.md):
//
//   - A cache entry is only eligible for a dedup hit once a `context` event
//     has shown its owning toolCallId is still present in the model-visible
//     transcript (`recomputeVisibility`). Entries start `visible: false` the
//     moment a full read is recorded and are only promoted (or demoted again,
//     e.g. after compaction) by the next `recomputeVisibility` call.
//   - A cache entry also requires the freshly computed content hash to match
//     the hash stored at record time (`lookupCache`): changed bytes -- even
//     with an unchanged mtime/size -- always re-read.
//   - `clearRetention` drops every entry (used on compaction, session switch,
//     fork, reload, and on/off transitions) without touching the cumulative
//     stats counters, which report lifetime totals for `/jev-context status`.
//
// Nothing in this module ever stores raw file content; cache entries keep a
// content hash and a character count, never the text itself.

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const MAX_CACHE_ENTRIES = 300;
/**
 * Files larger than this are never hashed/cached; read_context always falls through to a plain
 * read. Deliberately well under the built-in read tool's own 50KB/2000-line output cap: anything
 * this large is already far past what a model would ever see in full, so there is no plausible
 * caching benefit, only wasted CPU on every call. Kept small on purpose per implementation review.
 */
export const MAX_HASHABLE_BYTES = 5 * 1024 * 1024;

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]);

// ---------------------------------------------------------------------------
// Path / content helpers
// ---------------------------------------------------------------------------

export function resolvePath(cwd, inputPath) {
  return path.resolve(cwd, inputPath);
}

/**
 * Canonical form of a cwd for binding scouting consent. Resolves symlinks via
 * `realpathSync` when possible so `/repo` and a symlinked alias of it compare
 * equal; falls back to a plain `path.resolve` when the path doesn't exist yet
 * or `realpathSync` is unavailable/fails for any other reason.
 */
export function canonicalizeCwd(fsImpl, cwd) {
  const resolved = path.resolve(cwd);
  try {
    return fsImpl.realpathSync(resolved);
  } catch {
    return resolved;
  }
}

export function isImagePath(absPath) {
  return IMAGE_EXTENSIONS.has(path.extname(absPath).toLowerCase());
}

export function sha256Hex(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

/**
 * Reads a bounded file for hashing. Never throws: every failure (missing file,
 * directory, too large, unreadable, short read) comes back as
 * `{ ok: false, reason }` so the caller can fall through to a plain, uncached
 * read and let the real `read` tool report its own native error.
 *
 * Uses an explicit open/fstat/read(loop)/close sequence rather than
 * `statSync(path)` followed by `readFileSync(path)`: stat-by-path then
 * read-by-path is two separate syscalls against the *path*, so the file can
 * change (or be swapped/grow) between them (TOCTOU); `fstatSync` on an
 * already-open fd reports the size of the actual file descriptor we then
 * read from, and the explicit bounded read loop reads exactly that many
 * bytes (never more, never an unbounded single `readFileSync` call) so a
 * file that grows after our fstat still can't make us read past `maxBytes`.
 * Callers that need true end-to-end freshness (not just a bounded read)
 * should additionally re-run this after the dependent operation and compare
 * hashes, which is what read_context's post-read verification does.
 */
export function readFileBounded(fsImpl, absPath, maxBytes = MAX_HASHABLE_BYTES) {
  let fd;
  try {
    fd = fsImpl.openSync(absPath, fs.constants.O_RDONLY | fs.constants.O_NONBLOCK);
  } catch {
    return { ok: false, reason: "open_failed" };
  }
  try {
    const stat = fsImpl.fstatSync(fd);
    if (!stat.isFile()) return { ok: false, reason: "not_a_file" };
    if (stat.size > maxBytes) return { ok: false, reason: "too_large" };
    const buffer = Buffer.alloc(stat.size);
    let readTotal = 0;
    while (readTotal < stat.size) {
      const bytesRead = fsImpl.readSync(fd, buffer, readTotal, stat.size - readTotal, readTotal);
      if (bytesRead <= 0) break;
      readTotal += bytesRead;
    }
    if (readTotal !== stat.size) return { ok: false, reason: "short_read" };
    return { ok: true, buffer, size: stat.size };
  } catch {
    return { ok: false, reason: "read_failed" };
  } finally {
    try {
      fsImpl.closeSync(fd);
    } catch {
      /* best effort */
    }
  }
}

export function makeCacheKey(absPath, offset, limit) {
  return `${absPath}\u0000${offset ?? ""}\u0000${limit ?? ""}`;
}

export function sumTextLength(content) {
  let total = 0;
  for (const item of content ?? []) {
    if (item && item.type === "text" && typeof item.text === "string") total += item.text.length;
  }
  return total;
}

/**
 * Digest of the exact model-facing content we recorded, so visibility can be
 * confirmed against what the transcript *actually* still holds rather than
 * trusting a matching toolCallId alone. Hashes the full, exact block
 * serialization (`JSON.stringify` of the whole content array, not just
 * concatenated text) so a reordering, a changed field, or a different block
 * type all change the digest, not only a change to `.text`. Empty/missing
 * content makes the digest `null`, which can never equal a later digest and
 * so always forces a reread.
 */
export function digestContent(content) {
  if (!Array.isArray(content) || content.length === 0) return null;
  return sha256Hex(Buffer.from(JSON.stringify(content), "utf8"));
}

// ---------------------------------------------------------------------------
// Cache / retention state
// ---------------------------------------------------------------------------

export function createCacheState() {
  return {
    entries: new Map(),
    // Canonical cwd that a granted "on" consent applies to; see consentValidForCwd below.
    consentCwd: undefined,
    stats: { fullReads: 0, dedupedReads: 0, charsAvoidedApprox: 0, cacheClears: 0 },
    // Mirrors the sibling scoutFiles() stats contract (operator notes: jev-context-extension-implementation.md):
    // networkCalls/cacheHits/inputTokens/estimatedCostUsd/unknownCostCalls are the sibling's own
    // bounded counters, accumulated here across calls in this session. `usage`, when the sibling
    // returns one, is a native Pi Usage aggregate ({input, output, cacheRead, cacheWrite,
    // totalTokens, cost}) and is passed straight through on the tool result -- never remapped or
    // reconstructed from these stats.
    scout: { networkCalls: 0, cacheHits: 0, inputTokens: 0, estimatedCostUsd: 0, unknownCostCalls: 0, errors: 0 },
  };
}

/** Extracts the set of toolCallIds for tool-result messages currently visible in `messages`. */
export function toolResultIds(messages) {
  const ids = new Set();
  for (const message of messages ?? []) {
    if (message && message.role === "toolResult" && typeof message.toolCallId === "string") {
      ids.add(message.toolCallId);
    }
  }
  return ids;
}

/**
 * Indexes toolResult messages by toolCallId -> content digest, so visibility
 * can require the transcript still holds the *same* content, not merely a
 * message with a matching id (a `tool_result` handler from another extension
 * could redact or truncate the body in place without removing the message).
 */
function toolResultDigestsById(messages) {
  const byId = new Map();
  for (const message of messages ?? []) {
    if (message && message.role === "toolResult" && typeof message.toolCallId === "string") {
      // A transcript entry currently marked as an error is never a valid source for a dedup hit,
      // even if its toolCallId and content happen to match what we recorded (e.g. a later handler
      // flipped an originally-successful result to an error, or replayed a different outcome).
      if (message.isError === true) continue;
      byId.set(message.toolCallId, digestContent(message.content));
    }
  }
  return byId;
}

/**
 * Recomputes `visible` for every cache entry from an actual `context` event's
 * messages. An entry is visible only when its toolCallId is still present AND
 * the live message's content digest still matches the digest recorded at
 * full-read time -- not on toolCallId presence alone. Entries whose owning
 * toolCallId is gone (compacted away, branch switch, etc.) or whose content
 * changed underneath them (redacted/truncated by another handler, or an
 * error/image swapped in) are demoted back to invisible; this is what lets
 * the cache heal/forget conservatively without an explicit clear in every
 * case. Returns the visible id set for callers/tests that want it.
 */
export function recomputeVisibility(state, messages) {
  const digestsById = toolResultDigestsById(messages);
  const visibleIds = new Set();
  for (const entry of state.entries.values()) {
    const liveDigest = digestsById.get(entry.toolCallId);
    const visible = liveDigest !== undefined && liveDigest !== null && liveDigest === entry.resultDigest;
    entry.visible = visible;
    if (visible) visibleIds.add(entry.toolCallId);
  }
  return visibleIds;
}

/** Drops all retained entries. Never resets the cumulative stats counters. */
export function clearRetention(state) {
  state.entries.clear();
  state.stats.cacheClears += 1;
}

/**
 * Returns the cache entry usable for a dedup hit, or undefined. A hit requires
 * both an unchanged content hash AND a toolCallId confirmed visible by the
 * most recent `recomputeVisibility` call -- never based on key/hash alone.
 */
export function lookupCache(state, key, contentHash) {
  const entry = state.entries.get(key);
  if (!entry) return undefined;
  if (entry.contentHash !== contentHash) return undefined;
  if (entry.visible !== true) return undefined;
  return entry;
}

/**
 * Records a freshly completed full read. The entry starts `visible: false`;
 * it is only promoted by a later `recomputeVisibility` once the owning
 * toolCallId is actually confirmed present in model-visible context. This is
 * what keeps parallel first reads (same batch, no context event yet) from
 * suppressing each other.
 */
export function recordFullRead(
  state,
  key,
  { toolCallId, contentHash, charCount, resultDigest, path: filePath, offset, limit },
) {
  state.entries.set(key, {
    toolCallId,
    contentHash,
    charCount,
    // Digest of the returned text only -- never the raw text itself -- so the
    // cache never duplicates source content and still lets recomputeVisibility
    // detect redaction/truncation of the transcript message.
    resultDigest,
    path: filePath,
    offset,
    limit,
    visible: false,
  });
  state.stats.fullReads += 1;
  while (state.entries.size > MAX_CACHE_ENTRIES) {
    const oldestKey = state.entries.keys().next().value;
    state.entries.delete(oldestKey);
  }
}

/**
 * Net characters avoided by returning the short marker instead of the original full result
 * (original charCount minus the marker's own length). Never negative: a marker that is as long as
 * or longer than the original payload avoids nothing and should not even be used as a dedup hit
 * (see `isDedupWorthwhile`) -- this still clamps to zero defensively if a caller records one anyway.
 */
export function netCharsAvoided(entry, markerLength) {
  return Math.max(0, (entry.charCount ?? 0) - (markerLength ?? 0));
}

/**
 * A dedup marker is only worth returning when it is strictly shorter than the original payload it
 * replaces; otherwise the "optimization" would bloat small reads instead of shrinking them, and the
 * caller should do a normal full read instead.
 */
export function isDedupWorthwhile(entry, markerLength) {
  return markerLength < (entry.charCount ?? 0);
}

export function recordDedupedRead(state, entry, markerLength) {
  state.stats.dedupedReads += 1;
  state.stats.charsAvoidedApprox += netCharsAvoided(entry, markerLength);
}

export function mergeScoutStats(state, stats) {
  if (!stats || typeof stats !== "object") return;
  state.scout.networkCalls += Number(stats.networkCalls) || 0;
  state.scout.cacheHits += Number(stats.cacheHits) || 0;
  state.scout.inputTokens += Number(stats.inputTokens) || 0;
  state.scout.estimatedCostUsd += Number(stats.estimatedCostUsd) || 0;
  state.scout.unknownCostCalls += Number(stats.unknownCostCalls) || 0;
}

export function recordScoutError(state) {
  state.scout.errors += 1;
}

// ---------------------------------------------------------------------------
// Scouting consent binding
//
// A user's `/jev-context on` (or PI_JEV_CONTEXT=on) grants file-upload consent
// for the session as it exists *right now*, in *this* cwd/repo. Session
// switch, fork, and reload can silently move the same running extension state
// into a different project; without this check that would carry an existing
// file-upload consent into a repo the user never approved sending anywhere.
// The extension additionally resets `mode` to "off" on those lifecycle events
// as a first line of defense -- this binding is the second, independent of
// whether that reset path is hit for every future Pi version.
// ---------------------------------------------------------------------------

/** Records the canonical cwd that a scouting consent grant applies to. */
export function recordConsentCwd(state, canonicalCwd) {
  state.consentCwd = canonicalCwd;
}

export function clearConsentCwd(state) {
  state.consentCwd = undefined;
}

/** True only when consent was granted and the current canonical cwd matches exactly. */
export function consentValidForCwd(state, canonicalCwd) {
  return typeof state.consentCwd === "string" && state.consentCwd === canonicalCwd;
}

// ---------------------------------------------------------------------------
// Presentation (pure formatting, no I/O)
// ---------------------------------------------------------------------------

export function buildDedupMarker({ path: filePath, offset, limit, priorToolCallId, contentHash }) {
  const rangeBits = [];
  if (offset !== undefined) rangeBits.push(`offset ${offset}`);
  if (limit !== undefined) rangeBits.push(`limit ${limit}`);
  const range = rangeBits.length ? ` (${rangeBits.join(", ")})` : "";
  return [
    "[jev-context] Unchanged since an earlier full read still visible in this conversation.",
    `path: ${filePath}${range}`,
    `previous result: tool call ${priorToolCallId}, content hash ${contentHash.slice(0, 12)}\u2026`,
    "Call read_context again with force:true to force a fresh full read.",
  ].join("\n");
}

export function formatStatusLines({ mode, state, jevApiNote }) {
  const s = state.stats;
  const scout = state.scout;
  return [
    `jev-context: mode ${mode}`,
    `reads: full ${s.fullReads}, safely deduped ${s.dedupedReads}, ~chars avoided ${s.charsAvoidedApprox} (approximate, not provider-billed token savings)`,
    `cache: ${state.entries.size} entries retained, cleared ${s.cacheClears} time(s)`,
    `scout: network_calls ${scout.networkCalls}, cache_hits ${scout.cacheHits}, errors ${scout.errors}, unknown_cost_calls ${scout.unknownCostCalls}, est_cost_usd ${scout.estimatedCostUsd.toFixed(6)}`,
    `jev api: ${jevApiNote}`,
  ];
}

// ---------------------------------------------------------------------------
// Env opt-in parsing
// ---------------------------------------------------------------------------

/**
 * Parses PI_JEV_CONTEXT strictly: "local"/"on"/"off" are recognized, anything
 * else non-empty is "invalid" (never silently treated as an opt-in), and an
 * unset/empty var is "unset".
 */
export function resolveEnvOptIn(env = process.env) {
  const raw = env.PI_JEV_CONTEXT;
  if (typeof raw !== "string" || raw.trim().length === 0) return "unset";
  const v = raw.trim().toLowerCase();
  if (v === "local" || v === "on" || v === "off") return v;
  return "invalid";
}

// Re-exported for convenience so callers needing a plain fs-backed bounded
// read don't have to import node:fs themselves.
export { fs as defaultFs };
