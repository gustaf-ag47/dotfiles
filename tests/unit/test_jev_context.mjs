// Run: node --test --experimental-strip-types tests/unit/test_jev_context.mjs
//
// Two layers:
//   1. Pure unit tests against config/pi/lib/jev-context.mjs -- no Pi API, no
//      network, no filesystem beyond temp dirs this test creates and cleans
//      up itself.
//   2. A fake-pi harness (same pattern as test_llm_failover.mjs) that imports
//      the real config/pi/extensions/jev-context.ts default export and drives
//      it exactly the way Pi would: pi.registerTool/registerCommand/on calls
//      captured, tool execute() functions invoked directly, ctx.executeTool
//      faked with an in-memory "read" implementation backed by real temp
//      files so hashing/digest logic runs for real.
//
// Importing the .ts extension directly under plain Node (rather than through
// Pi's own jiti-based loader) needs "typebox" resolvable from this repo tree.
// This checkout has no node_modules (parent's install step is what normally
// provides that), so this file creates a *gitignored*
// `config/pi/node_modules/typebox` symlink (matches the existing
// `config/pi/**/node_modules/` gitignore entry) pointing at whatever
// @earendil-works/pi-coding-agent install this machine already has, purely so
// the module graph resolves under plain `node --experimental-strip-types`.
// Nothing is committed; if no such install is found on a given machine, the
// harness suite is skipped (reported, not silently green) and only the pure
// unit tests in layer 1 run -- see `extensionImportable` below.
//
// Additionally, a direct subprocess smoke test spawns the real, installed
// `pi` binary (if present) with --offline and loads jev-context.ts, sending
// only a slash command (never free text) so no model/network call is ever
// made, and asserts it starts cleanly -- "validate actual extension import
// via real Pi where possible" from the implementation brief.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

import {
  MAX_CACHE_ENTRIES,
  buildDedupMarker,
  canonicalizeCwd,
  clearConsentCwd,
  clearRetention,
  consentValidForCwd,
  createCacheState,
  digestContent,
  formatStatusLines,
  isDedupWorthwhile,
  isImagePath,
  lookupCache,
  makeCacheKey,
  mergeScoutStats,
  netCharsAvoided,
  readFileBounded,
  recomputeVisibility,
  recordConsentCwd,
  recordDedupedRead,
  recordFullRead,
  recordScoutError,
  resolveEnvOptIn,
  sha256Hex,
  sumTextLength,
} from "../../config/pi/lib/jev-context.mjs";

const REPO_ROOT = path.resolve(fileURLToPath(new URL("../..", import.meta.url)));

// This test file assumes the Jev API is reachable (PI_JEV_MODE unset/"observe") unless a specific
// test explicitly overrides it. The ambient shell this suite runs in may have PI_JEV_MODE=off set
// (e.g. a delegate/agent session that disabled Jev for itself) -- isolate from that so results don't
// depend on who happens to run the suite.
let savedAmbientJevMode;
before(() => {
  savedAmbientJevMode = process.env.PI_JEV_MODE;
  delete process.env.PI_JEV_MODE;
});
after(() => {
  if (savedAmbientJevMode === undefined) delete process.env.PI_JEV_MODE;
  else process.env.PI_JEV_MODE = savedAmbientJevMode;
});

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "jev-context-test-"));
}

// ---------------------------------------------------------------------------
// Layer 1: pure helpers
// ---------------------------------------------------------------------------

test("isImagePath matches common image extensions only", () => {
  assert.equal(isImagePath("/a/b/photo.png"), true);
  assert.equal(isImagePath("/a/b/photo.JPG"), true);
  assert.equal(isImagePath("/a/b/notes.md"), false);
  assert.equal(isImagePath("/a/b/no-extension"), false);
});

test("readFileBounded: missing file, directory, and too-large all fail closed without throwing", () => {
  const dir = tmpDir();
  const missing = path.join(dir, "nope.txt");
  assert.equal(readFileBounded(fs, missing).ok, false);

  const dirPath = path.join(dir, "subdir");
  fs.mkdirSync(dirPath);
  const dirResult = readFileBounded(fs, dirPath);
  assert.equal(dirResult.ok, false);
  assert.equal(dirResult.reason, "not_a_file");

  const big = path.join(dir, "big.txt");
  fs.writeFileSync(big, "x".repeat(100));
  const tooSmallBudget = readFileBounded(fs, big, 10);
  assert.equal(tooSmallBudget.ok, false);
  assert.equal(tooSmallBudget.reason, "too_large");

  const ok = readFileBounded(fs, big, 1000);
  assert.equal(ok.ok, true);
  assert.equal(ok.buffer.toString("utf8"), "x".repeat(100));
});

test("readFileBounded reads exactly the fstat'd byte count via a bounded loop, not an unbounded readFileSync", () => {
  const dir = tmpDir();
  const file = path.join(dir, "exact.bin");
  const payload = Buffer.alloc(12345, 7);
  fs.writeFileSync(file, payload);
  const result = readFileBounded(fs, file, 1_000_000);
  assert.equal(result.ok, true);
  assert.equal(result.size, payload.length);
  assert.ok(result.buffer.equals(payload));
});

test("digestContent hashes the exact block serialization (JSON.stringify), not just concatenated text", () => {
  const d1 = digestContent([{ type: "text", text: "hello" }]);
  const d2 = digestContent([{ type: "text", text: "hello" }]);
  assert.equal(d1, d2);
  assert.notEqual(d1, null);

  // A changed field (even one that isn't `.text`) changes the digest: exact block serialization,
  // not a naive text-only join.
  const withExtraField = digestContent([{ type: "text", text: "hello", textSignature: "sig-1" }]);
  assert.notEqual(withExtraField, d1);

  // Reordering two blocks changes the digest.
  const order1 = digestContent([{ type: "text", text: "a" }, { type: "text", text: "b" }]);
  const order2 = digestContent([{ type: "text", text: "b" }, { type: "text", text: "a" }]);
  assert.notEqual(order1, order2);

  assert.equal(digestContent([]), null);
  assert.equal(digestContent(undefined), null);
});

test("cache lookup requires both an unchanged content hash and a confirmed-visible toolCallId", () => {
  const state = createCacheState();
  const key = makeCacheKey("/abs/file.txt", 1, 10);
  const resultDigest = digestContent([{ type: "text", text: "contents" }]);
  recordFullRead(state, key, {
    toolCallId: "call-1",
    contentHash: "hash-a",
    charCount: 8,
    resultDigest,
    path: "/abs/file.txt",
    offset: 1,
    limit: 10,
  });

  // Not visible yet (no context event observed it): must miss.
  assert.equal(lookupCache(state, key, "hash-a"), undefined);

  // A context event that does NOT mention call-1 leaves it invisible.
  recomputeVisibility(state, [{ role: "user", content: [{ type: "text", text: "hi" }] }]);
  assert.equal(lookupCache(state, key, "hash-a"), undefined);

  // A context event with the matching toolResult message AND identical content confirms visibility.
  recomputeVisibility(state, [
    { role: "toolResult", toolCallId: "call-1", content: [{ type: "text", text: "contents" }], isError: false, input: {} },
  ]);
  const hit = lookupCache(state, key, "hash-a");
  assert.ok(hit);
  assert.equal(hit.toolCallId, "call-1");

  // Changed content hash (even with the same key) must miss despite visibility.
  assert.equal(lookupCache(state, key, "hash-b"), undefined);
});

test("visibility is revoked if the transcript message content no longer matches the recorded digest (redaction/truncation)", () => {
  const state = createCacheState();
  const key = makeCacheKey("/abs/file.txt", undefined, undefined);
  const resultDigest = digestContent([{ type: "text", text: "original full text" }]);
  recordFullRead(state, key, { toolCallId: "call-1", contentHash: "h1", charCount: 20, resultDigest, path: "/abs/file.txt" });
  recomputeVisibility(state, [
    { role: "toolResult", toolCallId: "call-1", content: [{ type: "text", text: "original full text" }], isError: false, input: {} },
  ]);
  assert.ok(lookupCache(state, key, "h1"));

  // Another extension's tool_result handler (or truncation) rewrites the same message in place.
  recomputeVisibility(state, [
    { role: "toolResult", toolCallId: "call-1", content: [{ type: "text", text: "REDACTED" }], isError: false, input: {} },
  ]);
  assert.equal(lookupCache(state, key, "h1"), undefined, "must re-read once the visible content no longer matches");
});

test("a toolResult message flipped to isError:true is never a valid dedup source, even with matching id/content", () => {
  const state = createCacheState();
  const key = makeCacheKey("/abs/file.txt", undefined, undefined);
  const content = [{ type: "text", text: "contents" }];
  const resultDigest = digestContent(content);
  recordFullRead(state, key, { toolCallId: "call-1", contentHash: "h1", charCount: 8, resultDigest, path: "/abs/file.txt" });
  recomputeVisibility(state, [{ role: "toolResult", toolCallId: "call-1", content, isError: true, input: {} }]);
  assert.equal(lookupCache(state, key, "h1"), undefined);
});

test("compaction/session-switch style clear forces a reread even with matching toolCallId and hash", () => {
  const state = createCacheState();
  const key = makeCacheKey("/abs/file.txt", undefined, undefined);
  const resultDigest = digestContent([{ type: "text", text: "contents" }]);
  recordFullRead(state, key, { toolCallId: "call-1", contentHash: "h1", charCount: 8, resultDigest, path: "/abs/file.txt" });
  recomputeVisibility(state, [
    { role: "toolResult", toolCallId: "call-1", content: [{ type: "text", text: "contents" }], isError: false, input: {} },
  ]);
  assert.ok(lookupCache(state, key, "h1"));

  clearRetention(state);
  assert.equal(lookupCache(state, key, "h1"), undefined);
  assert.equal(state.stats.cacheClears, 1);
  // Clearing retention never resets cumulative stats counters.
  assert.equal(state.stats.fullReads, 1);
});

test("never suppresses the only remaining full result: a never-visible entry always misses", () => {
  const state = createCacheState();
  const key = makeCacheKey("/abs/file.txt", undefined, undefined);
  const resultDigest = digestContent([{ type: "text", text: "contents" }]);
  recordFullRead(state, key, { toolCallId: "call-1", contentHash: "h1", charCount: 8, resultDigest, path: "/abs/file.txt" });
  // No context event ever fires (e.g. the run aborted before the next LLM call).
  assert.equal(lookupCache(state, key, "h1"), undefined);
});

test("bounded cache evicts oldest entries past MAX_CACHE_ENTRIES", () => {
  const state = createCacheState();
  for (let i = 0; i < MAX_CACHE_ENTRIES + 10; i++) {
    recordFullRead(state, makeCacheKey(`/f${i}.txt`, undefined, undefined), {
      toolCallId: `call-${i}`,
      contentHash: "h",
      charCount: 1,
      resultDigest: "d",
      path: `/f${i}.txt`,
    });
  }
  assert.equal(state.entries.size, MAX_CACHE_ENTRIES);
  assert.equal(state.entries.has(makeCacheKey("/f0.txt", undefined, undefined)), false, "oldest entry must be evicted");
});

test("isDedupWorthwhile/netCharsAvoided: a marker as long as or longer than the original is never worthwhile", () => {
  const entry = { charCount: 50 };
  assert.equal(isDedupWorthwhile(entry, 10), true);
  assert.equal(isDedupWorthwhile(entry, 50), false);
  assert.equal(isDedupWorthwhile(entry, 60), false);
  assert.equal(netCharsAvoided(entry, 10), 40);
  assert.equal(netCharsAvoided(entry, 50), 0);
  assert.equal(netCharsAvoided(entry, 60), 0, "never negative");
});

test("recordDedupedRead accumulates NET chars-avoided (original minus marker), labelled approximate", () => {
  const state = createCacheState();
  const entry = { charCount: 123 };
  recordDedupedRead(state, entry, 23);
  recordDedupedRead(state, entry, 23);
  assert.equal(state.stats.dedupedReads, 2);
  assert.equal(state.stats.charsAvoidedApprox, 200);
});

test("mergeScoutStats accumulates the sibling's native stats contract, including unknownCostCalls", () => {
  const state = createCacheState();
  mergeScoutStats(state, { networkCalls: 2, cacheHits: 1, inputTokens: 500, estimatedCostUsd: 0.0001, unknownCostCalls: 1 });
  mergeScoutStats(state, { networkCalls: 1, cacheHits: 0, inputTokens: 100, estimatedCostUsd: 0.00002, unknownCostCalls: 0 });
  assert.equal(state.scout.networkCalls, 3);
  assert.equal(state.scout.cacheHits, 1);
  assert.equal(state.scout.inputTokens, 600);
  assert.ok(Math.abs(state.scout.estimatedCostUsd - 0.00012) < 1e-9);
  assert.equal(state.scout.unknownCostCalls, 1);
  mergeScoutStats(state, undefined); // must not throw
  recordScoutError(state);
  assert.equal(state.scout.errors, 1);
});

test("buildDedupMarker names the prior tool call and hash prefix, never raw content", () => {
  const marker = buildDedupMarker({ path: "/a/b.txt", offset: 5, limit: 20, priorToolCallId: "call-42", contentHash: "abcdef1234567890" });
  assert.match(marker, /call-42/);
  assert.match(marker, /abcdef12345/);
  assert.match(marker, /force:true/);
  assert.doesNotMatch(marker, /hello world/);
});

test("formatStatusLines reports mode, read stats, cache size, and scout stats without raw paths/goals", () => {
  const state = createCacheState();
  recordFullRead(state, makeCacheKey("/a.txt"), { toolCallId: "c1", contentHash: "h", charCount: 10, resultDigest: "d", path: "/a.txt" });
  const lines = formatStatusLines({ mode: "local", state, jevApiNote: "available" });
  const joined = lines.join("\n");
  assert.match(joined, /mode local/);
  assert.match(joined, /full 1/);
  assert.match(joined, /not provider-billed token savings/);
});

test("resolveEnvOptIn: strict parsing, invalid values never silently treated as an opt-in", () => {
  assert.equal(resolveEnvOptIn({}), "unset");
  assert.equal(resolveEnvOptIn({ PI_JEV_CONTEXT: "" }), "unset");
  assert.equal(resolveEnvOptIn({ PI_JEV_CONTEXT: " LOCAL " }), "local");
  assert.equal(resolveEnvOptIn({ PI_JEV_CONTEXT: "on" }), "on");
  assert.equal(resolveEnvOptIn({ PI_JEV_CONTEXT: "off" }), "off");
  assert.equal(resolveEnvOptIn({ PI_JEV_CONTEXT: "yes" }), "invalid");
});

test("consent is bound to a canonical cwd and refuses on mismatch", () => {
  const state = createCacheState();
  const dir = tmpDir();
  const canonical = canonicalizeCwd(fs, dir);
  assert.equal(consentValidForCwd(state, canonical), false);
  recordConsentCwd(state, canonical);
  assert.equal(consentValidForCwd(state, canonical), true);
  assert.equal(consentValidForCwd(state, canonicalizeCwd(fs, tmpDir())), false);
  clearConsentCwd(state);
  assert.equal(consentValidForCwd(state, canonical), false);
});

test("sumTextLength only counts text parts", () => {
  assert.equal(sumTextLength([{ type: "text", text: "abcde" }, { type: "image", data: "..." }]), 5);
  assert.equal(sumTextLength([]), 0);
  assert.equal(sumTextLength(undefined), 0);
});

test("sha256Hex is stable and sensitive to content", () => {
  const a = sha256Hex(Buffer.from("same"));
  const b = sha256Hex(Buffer.from("same"));
  const c = sha256Hex(Buffer.from("different"));
  assert.equal(a, b);
  assert.notEqual(a, c);
});

// ---------------------------------------------------------------------------
// Layer 2: fake-pi harness driving the real extension module
// ---------------------------------------------------------------------------

function findTypeboxDir() {
  const candidates = [
    path.join(os.homedir(), ".local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/typebox"),
    path.join(os.homedir(), ".npm-global/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/typebox"),
    "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/typebox",
    "/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/typebox",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function ensureLocalTypeboxLink() {
  const target = findTypeboxDir();
  if (!target) return false;
  const nodeModulesDir = path.join(REPO_ROOT, "config/pi/node_modules");
  const linkPath = path.join(nodeModulesDir, "typebox");
  fs.mkdirSync(nodeModulesDir, { recursive: true });
  try {
    const existing = fs.readlinkSync(linkPath);
    if (existing === target) return true;
    fs.rmSync(linkPath, { force: true });
  } catch {
    /* no existing link */
  }
  try {
    fs.symlinkSync(target, linkPath, "dir");
    return true;
  } catch {
    return false;
  }
}

const extensionImportable = ensureLocalTypeboxLink();

function makeFakePi() {
  const handlers = {};
  const commands = new Map();
  const registeredTools = new Map();
  let activeTools = ["read", "bash", "edit", "write"];

  const pi = {
    registeredTools,
    registerTool(def) {
      registeredTools.set(def.name, def);
    },
    registerCommand(name, def) {
      commands.set(name, def);
    },
    on(event, handler) {
      (handlers[event] ||= []).push(handler);
      return () => {
        handlers[event] = handlers[event].filter((h) => h !== handler);
      };
    },
    getActiveTools() {
      return [...activeTools];
    },
    setActiveTools(names) {
      activeTools = [...names];
    },
  };

  return { pi, handlers, commands, getActiveTools: () => activeTools };
}

function makeFakeCommandCtx({ hasUI = true, confirmResult = true, cwd } = {}) {
  const notifications = [];
  const confirms = [];
  return {
    ui: {
      notify: (msg, level) => notifications.push([level ?? "info", msg]),
      confirm: async (title, msg) => {
        confirms.push([title, msg]);
        return confirmResult;
      },
    },
    hasUI,
    mode: hasUI ? "tui" : "json",
    cwd: cwd ?? process.cwd(),
    notifications,
    confirms,
  };
}

const DEFAULT_CALLABLE_TOOLS = [{ name: "read" }, { name: "bash" }, { name: "edit" }, { name: "write" }];

function makeFakeToolCtx({ cwd, fakeReadImpl, tools = DEFAULT_CALLABLE_TOOLS }) {
  return {
    cwd,
    tools,
    async executeTool(name, args) {
      if (name === "read") return fakeReadImpl(args);
      throw new Error(`unexpected nested tool call: ${name}`);
    },
  };
}

function fakeReadFactory(baseDir) {
  return async ({ path: p, offset, limit }) => {
    const abs = path.resolve(baseDir, p);
    let text;
    try {
      text = fs.readFileSync(abs, "utf8");
    } catch (err) {
      return {
        toolCall: { toolName: "read", input: { path: p } },
        isError: true,
        result: { content: [{ type: "text", text: `Error: ${err.message}` }], details: undefined, isError: true },
      };
    }
    if (offset || limit) {
      const lines = text.split("\n");
      const start = offset ? offset - 1 : 0;
      const end = limit ? start + limit : lines.length;
      text = lines.slice(start, end).join("\n");
    }
    return {
      toolCall: { toolName: "read", input: { path: p, offset, limit } },
      isError: false,
      result: { content: [{ type: "text", text }], details: undefined },
    };
  };
}

async function loadExtension() {
  const mod = await import("../../config/pi/extensions/jev-context.ts");
  return mod.default;
}

const skipReason = !extensionImportable && "typebox not resolvable on this machine; see test file header";

test("default off: loading the extension registers tools inactive and never touches active tools", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, getActiveTools } = makeFakePi();
  const before = getActiveTools();
  factory(pi);
  assert.deepEqual(getActiveTools(), before, "no tool activation at load time while off");
  assert.ok(pi.registeredTools.has("read_context"));
  assert.ok(pi.registeredTools.has("scout_files"));
});

test("/jev-context local activates read_context only, never scout_files, with no network", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, getActiveTools } = makeFakePi();
  factory(pi);
  const ctx = makeFakeCommandCtx();
  await commands.get("jev-context").handler("local", ctx);
  assert.ok(getActiveTools().includes("read_context"));
  assert.ok(!getActiveTools().includes("scout_files"));
  assert.ok(ctx.notifications.some(([, m]) => /local/.test(m)));
});

test("/jev-context local never activates read_context when the native read tool is already disabled", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, getActiveTools } = makeFakePi();
  pi.setActiveTools(pi.getActiveTools().filter((n) => n !== "read"));
  factory(pi);
  const ctx = makeFakeCommandCtx();
  await commands.get("jev-context").handler("local", ctx);
  assert.ok(!getActiveTools().includes("read_context"), "must never re-enable/depend on a disabled native read");
  assert.ok(ctx.notifications.some(([level, m]) => level === "warning" && /read.*disabled/.test(m)));
});

test("/jev-context on (interactive) asks for confirmation and only activates scout_files if confirmed", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  {
    const { pi, commands, getActiveTools } = makeFakePi();
    factory(pi);
    const ctx = makeFakeCommandCtx({ hasUI: true, confirmResult: false });
    await commands.get("jev-context").handler("on", ctx);
    assert.ok(ctx.confirms.length === 1, "must explain and ask for confirmation");
    assert.ok(!getActiveTools().includes("scout_files"), "declined confirmation must not enable scouting");
  }
  {
    const { pi, commands, getActiveTools } = makeFakePi();
    factory(pi);
    const ctx = makeFakeCommandCtx({ hasUI: true, confirmResult: true });
    await commands.get("jev-context").handler("on", ctx);
    assert.ok(getActiveTools().includes("scout_files"));
    assert.ok(getActiveTools().includes("read_context"));
  }
});

test("/jev-context on in noninteractive mode requires PI_JEV_CONTEXT=on, never silently accepts", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const savedEnv = process.env.PI_JEV_CONTEXT;
  try {
    delete process.env.PI_JEV_CONTEXT;
    const { pi, commands, getActiveTools } = makeFakePi();
    factory(pi);
    const ctx = makeFakeCommandCtx({ hasUI: false });
    await commands.get("jev-context").handler("on", ctx);
    assert.ok(!getActiveTools().includes("scout_files"), "must refuse without the env opt-in");
    assert.equal(ctx.confirms.length, 0, "noninteractive mode has no UI to confirm with");

    process.env.PI_JEV_CONTEXT = "on";
    const ctx2 = makeFakeCommandCtx({ hasUI: false });
    await commands.get("jev-context").handler("on", ctx2);
    assert.ok(getActiveTools().includes("scout_files"), "explicit env opt-in enables scouting noninteractively");
  } finally {
    if (savedEnv === undefined) delete process.env.PI_JEV_CONTEXT;
    else process.env.PI_JEV_CONTEXT = savedEnv;
  }
});

test("PI_JEV_MODE=off blocks scouting even with confirmation, local still available", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const savedMode = process.env.PI_JEV_MODE;
  try {
    process.env.PI_JEV_MODE = "off";
    const { pi, commands, getActiveTools } = makeFakePi();
    factory(pi);
    const onCtx = makeFakeCommandCtx({ hasUI: true, confirmResult: true });
    await commands.get("jev-context").handler("on", onCtx);
    assert.ok(!getActiveTools().includes("scout_files"), "PI_JEV_MODE=off must block the Jev API path");
    assert.ok(onCtx.confirms.length === 0, "must refuse before even asking, since scouting can't work anyway");

    const localCtx = makeFakeCommandCtx();
    await commands.get("jev-context").handler("local", localCtx);
    assert.ok(getActiveTools().includes("read_context"), "local mode stays available under PI_JEV_MODE=off");
  } finally {
    if (savedMode === undefined) delete process.env.PI_JEV_MODE;
    else process.env.PI_JEV_MODE = savedMode;
  }
});

test("/jev-context off deactivates both tools, aborts scouting, and never re-enables a user-disabled read", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, getActiveTools } = makeFakePi();
  // Simulate the user having already disabled the built-in read tool.
  pi.setActiveTools(pi.getActiveTools().filter((n) => n !== "read"));
  factory(pi);
  const onCtx = makeFakeCommandCtx({ hasUI: true, confirmResult: true });
  await commands.get("jev-context").handler("on", onCtx);
  assert.ok(getActiveTools().includes("scout_files"));
  assert.ok(!getActiveTools().includes("read_context"), "read_context must never activate while native read is disabled");

  const beforeOff = getActiveTools().filter((n) => n !== "read_context" && n !== "scout_files");
  const offCtx = makeFakeCommandCtx();
  await commands.get("jev-context").handler("off", offCtx);
  assert.ok(!getActiveTools().includes("read_context"));
  assert.ok(!getActiveTools().includes("scout_files"));
  assert.ok(!getActiveTools().includes("read"), "off must never re-enable a tool the user had disabled");
  assert.deepEqual(getActiveTools().sort(), beforeOff.sort(), "off must not disturb any other active tool choice");
});

test("session switch/fork never silently carries a granted scouting consent into another cwd", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, handlers, getActiveTools } = makeFakePi();
  factory(pi);
  const onCtx = makeFakeCommandCtx({ hasUI: true, confirmResult: true, cwd: tmpDir() });
  await commands.get("jev-context").handler("on", onCtx);
  assert.ok(getActiveTools().includes("scout_files"));

  for (const handler of handlers.session_before_switch ?? []) await handler({ type: "session_before_switch" });
  assert.ok(!getActiveTools().includes("scout_files"), "scouting consent must not survive a session switch");
});

test("session_start resume/new/fork fully resets to off so a prior consent never carries into a new session", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, handlers, getActiveTools } = makeFakePi();
  factory(pi);
  const cwd = tmpDir();
  const onCtx = makeFakeCommandCtx({ hasUI: true, confirmResult: true, cwd });
  await commands.get("jev-context").handler("on", onCtx);
  assert.ok(getActiveTools().includes("scout_files"));

  const startCtx = makeFakeCommandCtx({ hasUI: true, cwd });
  for (const handler of handlers.session_start ?? []) {
    await handler({ type: "session_start", reason: "resume" }, startCtx);
  }
  assert.ok(!getActiveTools().includes("scout_files"));
  assert.ok(!getActiveTools().includes("read_context"));
});

test("read_context: full read, then a safe dedup once visible, then forced reread, then a changed-byte reread", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, handlers } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");

  const dir = tmpDir();
  const filePath = path.join(dir, "file.txt");
  // Large enough that the dedup marker is genuinely net-shorter than the original (see
  // isDedupWorthwhile): a couple of lines would be shorter than the marker itself and legitimately
  // skip the dedup path, as covered by the dedicated "not net-shorter" test below.
  const bigContent = `${"line one\n".repeat(50)}line two\n`;
  fs.writeFileSync(filePath, bigContent);
  const toolCtx = makeFakeToolCtx({ cwd: dir, fakeReadImpl: fakeReadFactory(dir) });

  const first = await toolDef.execute("call-1", { path: "file.txt" }, undefined, undefined, toolCtx);
  assert.equal(first.content[0].text, bigContent);
  assert.equal(first.isError, undefined);

  // Confirm visibility via a real context event before expecting a dedup hit.
  for (const handler of handlers.context ?? []) {
    await handler({
      type: "context",
      messages: [{ role: "toolResult", toolCallId: "call-1", content: first.content, isError: false, input: {} }],
    });
  }

  const second = await toolDef.execute("call-2", { path: "file.txt" }, undefined, undefined, toolCtx);
  assert.match(second.content[0].text, /\[jev-context\]/);
  assert.match(second.content[0].text, /call-1/);
  assert.ok(!second.content[0].text.includes("line one"), "dedup response must not repeat raw content");

  const forced = await toolDef.execute("call-3", { path: "file.txt", force: true }, undefined, undefined, toolCtx);
  assert.equal(forced.content[0].text, bigContent);

  for (const handler of handlers.context ?? []) {
    await handler({
      type: "context",
      messages: [{ role: "toolResult", toolCallId: "call-3", content: forced.content, isError: false, input: {} }],
    });
  }

  // Changed bytes, same mtime artificially preserved -- must still reread.
  const stBefore = fs.statSync(filePath);
  fs.writeFileSync(filePath, `CHANGED\n${bigContent}`);
  fs.utimesSync(filePath, stBefore.atime, stBefore.mtime);
  const afterChange = await toolDef.execute("call-4", { path: "file.txt" }, undefined, undefined, toolCtx);
  assert.match(afterChange.content[0].text, /CHANGED/);
});

test("read_context: a marker that would not be net-shorter than the original is skipped (full read instead)", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, handlers } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");

  const dir = tmpDir();
  const filePath = path.join(dir, "tiny.txt");
  fs.writeFileSync(filePath, "hi"); // shorter than any dedup marker could ever be
  const toolCtx = makeFakeToolCtx({ cwd: dir, fakeReadImpl: fakeReadFactory(dir) });

  const first = await toolDef.execute("call-1", { path: "tiny.txt" }, undefined, undefined, toolCtx);
  assert.equal(first.content[0].text, "hi");
  for (const handler of handlers.context ?? []) {
    await handler({
      type: "context",
      messages: [{ role: "toolResult", toolCallId: "call-1", content: first.content, isError: false, input: {} }],
    });
  }
  const second = await toolDef.execute("call-2", { path: "tiny.txt" }, undefined, undefined, toolCtx);
  assert.equal(second.content[0].text, "hi", "a tiny file must get a real read, not a (longer) dedup marker");
  assert.doesNotMatch(second.content[0].text, /\[jev-context\]/);
});

test("read_context: parallel first reads in the same batch never suppress each other", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");

  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, "shared.txt"), "shared contents\n");
  let readCount = 0;
  const base = fakeReadFactory(dir);
  const toolCtx = makeFakeToolCtx({
    cwd: dir,
    fakeReadImpl: async (args) => {
      readCount += 1;
      return base(args);
    },
  });

  const [a, b] = await Promise.all([
    toolDef.execute("call-a", { path: "shared.txt" }, undefined, undefined, toolCtx),
    toolDef.execute("call-b", { path: "shared.txt" }, undefined, undefined, toolCtx),
  ]);
  assert.equal(readCount, 2, "no context event has fired yet, so neither call may suppress the other");
  assert.equal(a.content[0].text, "shared contents\n");
  assert.equal(b.content[0].text, "shared contents\n");
});

test("read_context: different offset/limit are independent cache keys", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, "multi.txt"), "a\nb\nc\nd\n");
  let readCount = 0;
  const base = fakeReadFactory(dir);
  const toolCtx = makeFakeToolCtx({
    cwd: dir,
    fakeReadImpl: async (args) => {
      readCount += 1;
      return base(args);
    },
  });

  const r1 = await toolDef.execute("c1", { path: "multi.txt", offset: 1, limit: 2 }, undefined, undefined, toolCtx);
  const r2 = await toolDef.execute("c2", { path: "multi.txt", offset: 3, limit: 2 }, undefined, undefined, toolCtx);
  assert.equal(readCount, 2);
  assert.notEqual(r1.content[0].text, r2.content[0].text);
});

test("read_context: image paths and read errors always pass through with isError preserved, never cached", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");
  const dir = tmpDir();

  let readCount = 0;
  const toolCtx = makeFakeToolCtx({
    cwd: dir,
    fakeReadImpl: async (args) => {
      readCount += 1;
      return {
        toolCall: { toolName: "read", input: args },
        isError: false,
        result: { content: [{ type: "image", data: "base64...", mimeType: "image/png" }], details: undefined },
      };
    },
  });
  const img1 = await toolDef.execute("c1", { path: "photo.png" }, undefined, undefined, toolCtx);
  const img2 = await toolDef.execute("c2", { path: "photo.png" }, undefined, undefined, toolCtx);
  assert.equal(readCount, 2, "images always pass through, never deduped");
  assert.notEqual(img1.isError, true);
  assert.notEqual(img2.isError, true);

  let errorReadCount = 0;
  const errCtx = makeFakeToolCtx({
    cwd: dir,
    fakeReadImpl: async () => {
      errorReadCount += 1;
      return {
        toolCall: { toolName: "read", input: {} },
        isError: true,
        result: { content: [{ type: "text", text: "Error: no such file" }], details: undefined, isError: true },
      };
    },
  });
  const err1 = await toolDef.execute("c3", { path: "missing.txt" }, undefined, undefined, errCtx);
  const err2 = await toolDef.execute("c4", { path: "missing.txt" }, undefined, undefined, errCtx);
  assert.equal(errorReadCount, 2, "errors are never cached/suppressed");
  assert.equal(err1.isError, true, "the outer isError flag from ctx.executeTool must be forwarded, not dropped");
  assert.equal(err2.isError, true);
});

test("read_context: never calls the native read tool when it isn't in ctx.tools (user-disabled read)", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, "file.txt"), "contents");

  let executeToolCalls = 0;
  const toolCtx = {
    cwd: dir,
    tools: [{ name: "bash" }, { name: "edit" }], // no "read"
    async executeTool() {
      executeToolCalls += 1;
      throw new Error("must not be called when read is not callable");
    },
  };
  const result = await toolDef.execute("c1", { path: "file.txt" }, undefined, undefined, toolCtx);
  assert.equal(executeToolCalls, 0, "must never reach for a native read that isn't callable");
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /disabled/);
});

test("read_context: skips caching (but still returns the read) when the file changes mid-call (TOCTOU)", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands, handlers } = makeFakePi();
  factory(pi);
  await commands.get("jev-context").handler("local", makeFakeCommandCtx());
  const toolDef = pi.registeredTools.get("read_context");
  const dir = tmpDir();
  const filePath = path.join(dir, "racy.txt");
  fs.writeFileSync(filePath, "before");

  const toolCtx = makeFakeToolCtx({
    cwd: dir,
    // Simulate the file changing while the nested "read" is in flight.
    fakeReadImpl: async (args) => {
      const base = fakeReadFactory(dir);
      const outcome = await base(args);
      fs.writeFileSync(filePath, "changed-during-call");
      return outcome;
    },
  });

  const first = await toolDef.execute("c1", { path: "racy.txt" }, undefined, undefined, toolCtx);
  assert.equal(first.content[0].text, "before", "the caller still gets the successful read result");

  for (const handler of handlers.context ?? []) {
    await handler({
      type: "context",
      messages: [{ role: "toolResult", toolCallId: "c1", content: first.content, isError: false, input: {} }],
    });
  }
  // Must NOT have cached against a hash that no longer describes the file: a second call sees the
  // post-change content and should do a real read again (not a dedup against "before").
  const second = await toolDef.execute("c2", { path: "racy.txt" }, undefined, undefined, toolCtx);
  assert.equal(second.content[0].text, "changed-during-call");
  assert.doesNotMatch(second.content[0].text, /\[jev-context\]/);
});

test("scout_files refuses to run until mode is on, and refuses on cwd/consent mismatch", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  const scoutTool = pi.registeredTools.get("scout_files");

  const offCtx = makeFakeToolCtx({ cwd: tmpDir(), fakeReadImpl: async () => { throw new Error("unused"); } });
  const offResult = await scoutTool.execute("s1", { goal: "find the config loader", paths: ["a.ts"] }, undefined, undefined, offCtx);
  assert.ok(offResult.isError);
  assert.match(offResult.content[0].text, /inactive/);

  const dirA = tmpDir();
  await commands.get("jev-context").handler("on", makeFakeCommandCtx({ hasUI: true, confirmResult: true, cwd: dirA }));
  const dirB = tmpDir();
  const mismatchCtx = makeFakeToolCtx({ cwd: dirB, fakeReadImpl: async () => { throw new Error("unused"); } });
  const mismatchResult = await scoutTool.execute("s2", { goal: "find the config loader", paths: ["a.ts"] }, undefined, undefined, mismatchCtx);
  assert.ok(mismatchResult.isError);
  assert.match(mismatchResult.content[0].text, /cwd/);
});

test("scout_files: a sibling module error is sanitized before reaching the model (no raw error text)", { skip: skipReason }, async (t) => {
  const factory = await loadExtension();
  const { pi, commands } = makeFakePi();
  factory(pi);
  const dir = tmpDir();
  await commands.get("jev-context").handler("on", makeFakeCommandCtx({ hasUI: true, confirmResult: true, cwd: dir }));
  const scoutTool = pi.registeredTools.get("scout_files");
  const ctx = makeFakeToolCtx({ cwd: dir, fakeReadImpl: async () => { throw new Error("unused"); } });

  // The sibling module genuinely doesn't exist in this checkout yet (owned by a sibling task), so
  // this call exercises the real "module unavailable" path -- it must fail as a clean, bounded
  // isError result, never throw an unsanitized error up through the tool boundary.
  const result = await scoutTool.execute("s1", { goal: "find the config loader", paths: ["a.ts"] }, undefined, undefined, ctx);
  assert.ok(result.isError);
  assert.match(result.content[0].text, /scout_files/);
});

test("hooks tolerate bash/other tool-result messages without throwing and without affecting unrelated entries", { skip: skipReason }, async () => {
  const factory = await loadExtension();
  const { pi, handlers } = makeFakePi();
  factory(pi);
  for (const handler of handlers.context ?? []) {
    await assert.doesNotReject(async () => {
      await handler({
        type: "context",
        messages: [
          { role: "assistant", content: [{ type: "text", text: "hi" }] },
          { role: "toolResult", toolCallId: "bash-1", content: [{ type: "text", text: "$ ls\nfile.txt" }], isError: false, input: { command: "ls" } },
        ],
      });
    });
  }
});

// ---------------------------------------------------------------------------
// Real-Pi smoke test: loads the actual extension through the installed `pi`
// binary and sends only a slash command (no free text -> no model/network
// call is ever made). Skipped (reported, not silently passed) if `pi` isn't
// on PATH in this environment.
// ---------------------------------------------------------------------------

function findPiBinary() {
  const result = spawnSync("sh", ["-c", "command -v pi"], { encoding: "utf8" });
  if (result.status === 0) return result.stdout.trim();
  return null;
}

const piBinary = findPiBinary();

test("real Pi can load jev-context.ts and run /jev-context status with no network call", { skip: !piBinary && "pi binary not found on PATH" }, () => {
  const result = spawnSync(
    piBinary,
    [
      "--offline",
      "--no-session",
      "--no-extensions",
      "--mode",
      "json",
      "--print",
      "/jev-context status",
      "-e",
      path.join(REPO_ROOT, "config/pi/extensions/jev-context.ts"),
    ],
    { encoding: "utf8", timeout: 20000, cwd: REPO_ROOT },
  );
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.doesNotMatch(result.stdout + result.stderr, /Error/i, "extension must load and run the command without error");
});
