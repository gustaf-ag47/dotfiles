# Jev context extension: file scouting + safe read dedup implementation

Status: implemented and unit-tested in isolation, **not installed/wired into
any live Pi config** (parent owns installation/docs/live tests per the brief).
Branch `feat/jev-context-extension`, worktree
`/home/gustaf/.cache/jev-context/extension`. Implements
`docs/research/jev-context-extension-implementation.md`: an opt-in Pi extension
adding `read_context` (freshness-aware duplicate-read suppression) and
`scout_files` (explicit-consent file-relevance triage via the sibling's
TypeSafe scouting module), gated by `/jev-context status|local|on|off`.

No live inference/classifier/scout calls were made while building or testing
this. The sibling scouting module (`config/pi/lib/jev-scout.mjs`) does not
exist yet in this checkout; `scout_files` imports it dynamically at call time
and fails closed with a clean, bounded error when it's missing (exercised
directly by a test in this suite).

## Files owned by this implementation

- `config/pi/lib/jev-context.mjs` — pure, dependency-injectable cache/state
  helpers: content hashing, cache-entry lifecycle, visibility recomputation,
  consent-cwd binding, stats bookkeeping, status/marker formatting, env
  opt-in parsing. No Pi API, no network, importable and testable standalone.
- `config/pi/extensions/jev-context.ts` — the Pi extension: registers
  `read_context` and `scout_files` (both inactive by default,
  `defaultActive: false`), the `/jev-context` command, and the lifecycle
  hooks that drive retention/consent.
- `tests/unit/test_jev_context.mjs` — 39 tests: pure-helper unit tests, a
  fake-`pi` harness driving the real extension module end-to-end, and a
  real-`pi`-subprocess smoke test (slash command only, `--offline`, no model
  call).
- This file.

## Pi API verified before coding

Read in full: `docs/extensions.md` (installed Pi 0.99.1,
`@earendil-works/pi-coding-agent`), the exported declarations in
`dist/core/extensions/types.d.ts` (the package ships compiled `.d.ts`, not
the TypeScript source linked from the public repo — this checkout has no
network access to GitHub, so the installed declarations are the verified
source of truth here), and the examples `dynamic-tools.ts`,
`truncated-tool.ts`, and `tool-override.ts`.

Confirmed from the declarations/examples, not assumed:

- `ToolDefinition.exposure`/`defaultActive`/`prepareLoadout` — a `direct` tool
  with `defaultActive: false` is registered but **not** added to the active
  (model-declared) set at registration time; activation is a separate
  `pi.setActiveTools()` call. `prepareLoadout` returns
  `{ hiddenDeclarations }` for tools that should stay active+callable but
  not be *declared* to the model while another tool (here, `read_context`)
  is active.
- `ExtensionToolContext.executeTool(name, args, { signal, onUpdate })` and
  `ctx.tools: readonly AgentTool[]` — nested calls go through the same
  `tool_call`/`tool_result` hooks and validation as a model-issued call, are
  never added to the transcript themselves, and `ctx.tools` lists exactly
  what `executeTool` can reach (used to detect a user-disabled `read`).
- `ContextEvent { messages: AgentMessage[] }` fires before every LLM call
  with the already-restored, system-prompt-stripped transcript. `Message`
  (from `@earendil-works/pi-ai`) includes `ToolResultMessage: { role:
  "toolResult", toolCallId, content, isError }` — confirmed in
  `pi-ai/dist/types.d.ts`, not guessed.
- `AgentToolResult<T>` (`pi-agent-core/dist/types.d.ts`) and
  `AgentToolCallOutcome { toolCall, result, isError }` — the outer
  `isError` is a **separate field** from whatever `result` itself carries;
  dropping it by returning `outcome.result` alone silently turns a failed
  nested read into an apparently-successful tool result. Fixed in review
  (see "Parent review round" below).
- `ExtensionCommandContext`/`ExtensionContext.hasUI` — `"true in TUI and RPC
  modes"`; used as the interactive/noninteractive split for the `on`
  confirmation gate.
- `pi --help` and a live `pi --offline -e <file> --mode json --print
  "/jev status"` run (existing `jev.ts`) confirmed that a slash command is
  processed without any model/provider call even when a model is otherwise
  configured — this is what makes the real-Pi smoke test and the manual
  verification in this doc safe to run with no network and no spend. A
  separate manual check with a **non-slash** prompt against
  `examples/extensions/truncated-tool.ts` was a genuine mistake during
  exploration: `--offline` only disables *startup* network operations, not
  provider calls triggered by an actual prompt, and that one `"hello"` test
  run made one real billed provider call. No test or script in this
  deliverable sends a non-slash-command prompt; the real-Pi test here only
  ever sends `/jev-context status`.

## Behavior implemented

### Modes: off (default) / local / on

- **off** (default): `read_context`/`scout_files` are registered (so
  `pi.getActiveTools()`/active-set manipulation has stable names to work
  with) but never added to the active set, so the model never sees them
  declared. No lifecycle hook performs any filesystem or network work beyond
  clearing an already-empty retention map.
- **local**: activates `read_context` only. Never calls the sibling
  scouting module (not even a dynamic import). No network, ever.
- **on**: activates `read_context` **and** `scout_files`. Interactive
  (`ctx.hasUI`): always shows a privacy explanation and asks
  `ctx.ui.confirm()`, regardless of any env var — an env opt-in is not
  treated as silently pre-answering the dialog. Noninteractive
  (`!ctx.hasUI`, e.g. `--mode json --print`): there is no dialog to show, so
  enabling requires `PI_JEV_CONTEXT=on` set in the environment; anything
  else refuses with a warning and stays local/off. `PI_JEV_MODE=off` (the
  pre-existing shared Jev helper's own kill switch) blocks the `on` path
  entirely — checked *before* even asking for confirmation — while leaving
  `local` fully available, satisfying "environment PI_JEV_MODE=off still
  disables Jev API, local mode can work" without conflating the two
  extensions' consent models.
- `PI_JEV_CONTEXT=local` at `session_start` enables local mode the same way
  the `local` command does (env opt-in for local, documented separately from
  the stricter `on` env gate per the brief).

### Never re-enables a user-disabled `read`

Two independent checks, not one:

1. **Activation-level** (`nativeReadAvailable()` in the `.ts` file): before
   adding `read_context` to the active set, checks
   `pi.getActiveTools().includes("read")`. If the user has `read` disabled,
   `read_context` stays inactive and a warning is shown — scouting
   (`scout_files`) is unaffected since it doesn't depend on `read`.
2. **Execution-level** (defensive, inside `read_context`'s own `execute()`):
   checks `ctx.tools.some(t => t.name === "read")` *before* any filesystem
   hashing or a nested `executeTool("read", ...)` call, in case activation
   state and callable-tool state ever disagree. Returns a clean `isError`
   result naming the reason, never attempts the nested call.

`prepareLoadout` only ever returns `hiddenDeclarations: ["read"]`, and only
when `read` is already in `loadout.declared` — it never adds `read` to
anything.

### Retention: when a dedup hit is allowed

A cache entry (keyed by resolved path + offset + limit) is eligible for a
dedup hit only when **all** of these hold at lookup time:

1. A fresh bounded hash of the file on disk right now matches the hash
   recorded when the entry was written (`lookupCache`'s `contentHash`
   check) — catches changed bytes even with an unchanged mtime/size.
2. The entry has been marked `visible` by `recomputeVisibility`, which runs
   on every real `context` event (not assumed/derived any other way) and
   requires **both**:
   - the entry's owning `toolCallId` is present on a `role: "toolResult"`
     message in `event.messages`, **and**
   - `message.isError !== true`, and
   - `digestContent(message.content)` — a hash of the exact
     `JSON.stringify` of the live message's content blocks — still equals
     the `resultDigest` recorded when the entry was written.

   That last check is the one added in the parent review round: a matching
   `toolCallId` alone is not sufficient, because another extension's
   `tool_result` handler (or a future Pi feature) could redact, truncate, or
   otherwise rewrite the message body in place without changing its id.
   `digestContent` hashes the full serialized block array, not merely
   concatenated `.text`, so a reordering or a changed non-text field (e.g. a
   `textSignature`) also invalidates the entry — not just a changed `.text`
   string.

An entry starts `visible: false` the instant it's recorded and is **only**
promoted by a subsequent `context` event. This is what keeps two parallel
`read_context` calls for the same path in the same tool batch from
suppressing each other (neither has had a chance to be confirmed visible
yet) and keeps a result that is aborted before the next LLM call from being
treated as "safely visible" — directly implementing "never suppress the only
remaining full result" and "no dedup parallel first reads" from the brief.

Retention is force-cleared (not just naturally demoted) on
`session_before_compact`, `session_compact`, `session_shutdown`, and every
`session_start`, independent of the visibility recompute, so the cache can
never reference stale history even if a future Pi version changes what
`context` events contain across one of those boundaries.

### TOCTOU: pre/post-read hash verification

`readFileBounded` now opens the file once (`openSync` → `fstatSync` on the
**descriptor**, not the path → a bounded `readSync` loop reading exactly
`fstat.size` bytes, capped at `MAX_HASHABLE_BYTES` = 5 MiB, lowered from an
initial 20 MiB per review) instead of a separate `statSync(path)` followed by
an unbounded `readFileSync(path)`. That earlier shape had two problems the
parent review caught: `stat`-by-path then `read`-by-path are two syscalls
against the *path*, so the file can change or grow between them, and
`readFileSync` has no bound of its own.

`read_context`'s `execute()` additionally hashes the file **again** after
the nested `read` call returns, and only records a cache entry when the
pre-call and post-call hashes are identical. If they differ (the file
changed while the nested read was in flight — exercised directly by a test
that mutates the file mid-call), the successful read result is still
returned to the caller, but nothing is cached against a hash that no longer
describes the file.

### Dedup must actually be net-shorter

`buildDedupMarker()`'s fixed boilerplate text (~250–300 bytes) is longer
than many small files. Before using a cache hit, `read_context` builds the
marker text and checks `isDedupWorthwhile(entry, marker.length)` — if the
marker would be the same size or larger than the original result, it falls
through to a real read instead. `recordDedupedRead` only credits the *net*
characters avoided (`netCharsAvoided` = original minus marker length, never
negative) toward the `/jev-context status` stats, not the gross original
size — otherwise the reported savings would overstate (or for small files,
invert the sign of) the actual effect.

### Consent scope: scoping "on" to one cwd/session

A command-granted (or env-granted) `on` consent is bound to the **canonical
cwd** (`canonicalizeCwd`: `realpathSync`, falling back to `path.resolve` if
that fails) at the moment it's granted (`recordConsentCwd`). `scout_files`
refuses to run — a clean `isError`, not a crash — if the live canonical cwd
at call time doesn't match (`consentValidForCwd`). Independently, as a first
line of defense, `session_before_switch`, `session_before_fork`, and every
non-`"startup"` `session_start` (`resume`/`new`/`fork`/`reload`) reset mode
to `off` and abort any in-flight scouting outright, so a file-upload consent
granted in one project is never silently carried across a session boundary
even before the cwd check would catch a mismatch. Both mechanisms are kept
intentionally redundant per the review note ("reset ... or bind consent ...")
rather than relying on either alone.

`scoutController.abort()` is called at the start of `off`, at the start of
every `activateOn()` (so a second activation can never leak an earlier
controller), and on the lifecycle resets above — `/jev-context off` aborts
any in-flight scouting request so a queued candidate request cannot proceed
after consent is revoked, per the parent's explicit requirement.

### Usage/stats contract with the scouting sibling

Per the parent's contract correction mid-implementation: `scoutFiles()`'s
`usage`, when present, is a **native Pi `Usage` aggregate**
(`{ input, output, cacheRead, cacheWrite, totalTokens, cost }`), passed
through on the `scout_files` tool result's own `usage` field completely
unmodified — never remapped, summed, or reconstructed from the `stats`
counters. `stats` (`networkCalls`, `cacheHits`, `inputTokens`,
`estimatedCostUsd`, `unknownCostCalls`) is the sibling's own bounded
per-call counters; `mergeScoutStats` only accumulates them session-locally
for `/jev-context status`. No file paths or goal text are written to any
ledger by this module (there is no ledger here); the model-facing
`scout_files` result text does include the paths the caller itself passed
in (explicitly already known to the caller) and each item's path/confidence,
per "returned requested path strings okay."

### Sanitized errors

A thrown error from the sibling `scoutFiles()` call (or its own dynamic
import) is caught, counted (`recordScoutError`), and replaced with a short,
fixed, non-secret message (`"scout_files: scouting request failed"`) before
re-throwing — consistent with the existing shared Jev helper's "no raw
provider error text" policy (`config/pi/lib/jev.mjs`). The model-facing
`scout_files` success text includes each item's `relevance` bucket, `path`,
and a formatted `confidence` (e.g. `src/foo.ts (0.82)`) when the sibling
provides one — no model-generated rationale, per the brief.

### Stats surfaced by `/jev-context status`

UI notification only (`ctx.ui.notify`), never an extra model message:
mode, full vs. safely-deduped read counts, approximate **net** characters
avoided (explicitly labeled "not provider-billed token savings"), retained
cache entry count and clear count, and scout `network_calls`/`cache_hits`/
`errors`/`unknown_cost_calls`/`est_cost_usd`.

## Parent review round: what changed and why

The parent reviewed the first draft of this `.ts`/`.mjs` pair mid-task and
flagged seven concrete issues, all addressed and covered by new tests before
commit:

1. **Dropped `isError` on passthrough.** `return outcome.result` discarded
   the outer `AgentToolCallOutcome.isError` flag, turning a failed nested
   read into an apparently-successful result. Fixed: every passthrough path
   now explicitly carries `isError: outcome.isError` (or `true` on the
   full-read error branch), and `signal`/`onUpdate` are forwarded into the
   nested `executeTool` call instead of being silently dropped.
2. **TOCTOU in bounded hashing.** See "TOCTOU" above:
   `fstatSync(fd)`/bounded `readSync` loop replacing `statSync(path)` +
   `readFileSync(path)`, plus a post-read re-hash before caching, plus
   lowering `MAX_HASHABLE_BYTES` from 20 MiB to 5 MiB.
3. **Dedup marker could bloat small reads.** See "Dedup must actually be
   net-shorter" above: `isDedupWorthwhile`/`netCharsAvoided`.
4. **Visibility needed exact-content verification, not just an id match,
   and had to exclude error-flagged messages.** See "Retention" above:
   `digestContent` now hashes the full serialized block array, and
   `toolResultDigestsById` skips any message with `isError === true`.
5. **`read_context` could call a disabled `read`.** See "Never re-enables a
   user-disabled read" above: the `ctx.tools` check added before any
   hashing/network-adjacent work, plus the activation-time
   `nativeReadAvailable()` gate.
6. **`activateOn` controller leak risk; `session_start` racing
   `attemptEnableOn`.** `activateOn()` now calls `abortScouting()` before
   creating its own controller (so a second activation can't leak the
   first), and the `session_start` handler is `async` and `await`s
   `attemptEnableOn()` instead of firing it with `void` — a dangling promise
   there could otherwise race the first turn's tool declarations or produce
   a silent unhandled rejection.
7. **Scout result needed confidence; thrown errors needed sanitizing.** See
   "Sanitized errors" above.

All seven are covered by dedicated tests in `test_jev_context.mjs` (TOCTOU:
"skips caching ... when the file changes mid-call"; net-shorter: "a marker
that would not be net-shorter ... is skipped"; isError propagation: "image
paths and read errors always pass through with isError preserved"; disabled
read: "never calls the native read tool when it isn't in ctx.tools"; error
sanitizing: "a sibling module error is sanitized before reaching the model";
etc.) before this doc was written.

## Known limitations / out of scope

- **`config/pi/lib/jev-scout.mjs` does not exist in this checkout.**
  `scout_files` dynamically imports it at call time and fails closed with a
  clean `isError` result when the import fails (exercised directly — the
  module genuinely isn't there yet). No assumption about its internals
  beyond the interface contract in the brief (`scoutFiles({cwd, goal, paths,
  enabled, signal}) => {items, skipped, stats, usage?}`) and the two
  contract corrections relayed mid-task (native `Usage` aggregate;
  `unknownCostCalls` in `stats`).
- **Typebox resolution for plain-Node tests.** This checkout has no
  `node_modules` (the real Pi process resolves `typebox` for extension
  tools through its own bundling/`jiti` loader, confirmed working via the
  real-Pi smoke test and the earlier manual `truncated-tool.ts` check); to
  drive the `.ts` extension's logic directly under plain
  `node --experimental-strip-types` for the fake-`pi` harness tests, the
  test file creates a **gitignored** `config/pi/node_modules/typebox`
  symlink (matches the pre-existing `config/pi/**/node_modules/` gitignore
  entry) pointing at whatever `@earendil-works/pi-coding-agent` install is
  already on the machine, and skips (reports, not silently passes) that
  layer of tests if none is found. Nothing is committed. The pure-helper
  tests and the real-Pi smoke test have no such dependency.
- **No installation wiring.** `bin/pi-link-extensions`'s `ALLOWLIST`
  (`tests/unit/test_pi_link_extensions.py`), any docs under `docs/` other
  than this file, and `scripts/llm_usage.py`/`config/llm-proxy/jev.json`
  were not touched, per the brief ("parent coordinates
  installation/docs/live tests").
- **`canonicalizeCwd` symlink edge case.** Falls back to `path.resolve`
  when `realpathSync` fails (e.g. the directory doesn't exist yet, or a
  permissions issue) rather than throwing; this means two *different* paths
  that both fail to resolve could compare equal only if they're textually
  identical after `path.resolve` — not a meaningfully different bound than
  comparing plain cwds, just not symlink-aware in that one failure case.
- **`MAX_CACHE_ENTRIES` (300) and `MAX_HASHABLE_BYTES` (5 MiB)** are fixed
  constants, not configurable from `/jev-context`; reasonable per the
  brief's "bounded" requirement, not tuned against a real workload.

## Commands to reproduce

```sh
cd /home/gustaf/.cache/jev-context/extension
node --test --experimental-strip-types tests/unit/test_jev_context.mjs
node --test tests/unit/test_jev.mjs   # pre-existing Jev helper suite, unaffected
git diff --check
```

Both test commands pass (39/39 and 36/36) and `git diff --check` is clean as
of this writing. Only the three owned files plus this doc are staged; the
Jev scouting sibling's file, the shared Jev helper, and all parent-owned
files are untouched.
