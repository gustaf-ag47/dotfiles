# Jev shadow classifier: shared helper implementation

Status: implemented, shadow/observe-only, no live network calls made while
building or testing this. Branch `feat/jev-helper`, worktree
`/home/gustaf/.cache/jev-implementation/helper`. Implements the first
milestone of `docs/handover/implement-jev-helper.md`: a shared Jev classifier
helper, a CLI the delegate shell wrapper calls, and a Pi `/jev` command —
**observation only, nothing is ever applied to a launch decision.**

## Files owned by this implementation

- `config/pi/lib/jev.mjs` — the one shared implementation. Both callers below
  import this; no logic is duplicated between them.
- `bin/jev-classify` — CLI: `--task-stdin --source delegate|pi` (classify) and
  `--status` (read-only). Called once per delegate dispatch by the parent's
  delegate shell hook, after the dry-run/probe, output discarded, with its
  own ~3s internal bound comfortably inside the parent's 5s outer timeout.
- `config/pi/extensions/jev.ts` — Pi `/jev status|off|observe|classify <text>`
  command. `classify` is the **only** way this extension ever calls the
  classifier; there is no automatic turn_start/session_start hook. `off`/
  `observe` only set an in-memory override for the running Pi session; they
  never touch `config/llm-proxy/jev.json`, never set `PI_JEV_MODE` for any
  other process, and have no effect on `bin/jev-classify` invocations made by
  the delegate shell wrapper in its own process.
- `config/llm-proxy/jev.json` — config: mode, model, rubric version, classes,
  confidence threshold, timeout, daily budget caps, published price. A
  present-but-invalid file makes every call abstain (see below); a missing
  file falls back to the same defaults baked into `jev.mjs`.
- `tests/unit/test_jev.mjs` — 36 offline tests, synthetic classifier
  injection, temp state dirs, no real credentials, no network.

## Interface contract actually implemented

```
bin/jev-classify --task-stdin --source delegate|pi
  stdin: raw task text (trimmed; >2000 chars -> {status:"skipped",reason:"task_too_long"};
         >8192 raw bytes on the wire is rejected outright as an overflow, never
         classified from a silently truncated prefix)
  stdout: exactly one JSON object:
    {"status":"ok","applied":false,"suggestion":"<interactive|build|research|mechanical>","confidence":<0..1>}
    {"status":"abstained","applied":false,"reason":"low_confidence","confidence":<0..1>}
    {"status":"cache_hit","applied":false,"suggestion":"<class>","confidence":<0..1>}
    {"status":"skipped","applied":false,"reason":"mode_off|invalid_mode|config_malformed|config_invalid|
      config_unreadable|empty_task|task_too_long|missing_key|budget_exceeded|budget_corrupt|
      budget_unavailable|classifier_unavailable"}
    {"status":"error","applied":false,"reason":"timeout|classifier_error|unexpected_answer"}
  exit code: 0 for all of the above. Non-zero (2) only for CLI usage mistakes
  (unknown flag, invalid --source value, --status with --task-stdin together).
  Unknown args and invalid flag values are rejected without being echoed back.

bin/jev-classify --status
  no stdin read, no classification performed
  stdout: {"mode":"off|observe|invalid","configValid":bool,"configError":string|null,
           "model":"jev-1.13.0","rubricVersion":"task-class.v1","keyConfigured":bool,
           "budget":{"date":"YYYY-MM-DD","calls":N,"costUsd":X,"corrupt":bool,
                      "maxCallsPerDay":N,"maxCostPerDayUsd":X},
           "today":{"ok":N,"abstained":N,"error":N,"skipped":N,"cache_hit":N},
           "cacheEntries":N}
```

Mode is controlled only via `PI_JEV_MODE=off|observe` (env) or `mode` in
`jev.json`; there is no CLI flag to toggle it, and there is no "apply" mode —
`applied` is hardcoded `false` in every single return value and ledger event.

## Ledger (shared contract with the accounting side)

`${XDG_STATE_HOME:-$HOME/.local/state}/jev/events.jsonl`, directory `0700`,
file `0600`, rotated to `.1` past 5 MiB. One line per attempt:

```json
{"schema":"jev-event.v1","timestamp":"<UTC ISO>","source":"delegate|pi",
 "status":"ok|abstained|error|skipped|cache_hit","class":"<label>|null",
 "confidence":<number>|null,"model":"jev-1.13.0","rubric_version":"task-class.v1",
 "latency_ms":<number>,"input_tokens":<number>|null,"output_tokens":<number>|null,
 "estimated_cost_usd":<number>|null,"cost_source":"published-rate|unknown|cache",
 "applied":false}
```

Per the accounting side's confirmed reading convention:

- **`cache_hit`** and every **pre-dispatch `skipped`** reason (mode off,
  invalid mode, invalid/malformed config, empty/too-long task, missing key,
  budget exceeded/corrupt/unavailable, classifier unavailable) record
  `input_tokens: 0`, `output_tokens: 0`, `estimated_cost_usd: 0`,
  `cost_source: "cache"` — these are genuinely, locally known to cost
  nothing because no request was ever sent (or the answer came from the
  local cache), not merely "we don't know".
- Every **dispatched** request that ends in `error` (timeout, classifier
  error, or an answer that failed whitelist/range validation) keeps
  `input_tokens`/`output_tokens`/`estimated_cost_usd` as `null` and
  `cost_source: "unknown"` — a request that reached the network may have
  been billed even though we never got a trustworthy answer back, so "zero"
  would be a false claim. See "Budget: no refund after dispatch" below for
  why the same asymmetry applies to the daily cost cap.
- `ok` and `abstained` (both only reachable *after* a successful, validated
  response) report real `usage`-derived cost at `cost_source: "published-rate"`
  when the provider reported token counts, else `null`/`"unknown"` — never a
  fabricated number.
- No prompt, task text, file path, auth material, or raw provider error text
  is ever written to this file. A test (`no result object from classifyTask
  ever contains the raw task text`) asserts this for the CLI/extension
  result objects too.

## Pricing: Pi's catalog is wrong for this route, use the official rate

Pi's bundled model catalog (`@earendil-works/pi-ai`'s
`providers/data/typesafe.json`) lists `typesafe/jev-latest` at
`cost.input: 0`. TypeSafe's own published pricing
(`https://docs.typesafe.ai/models.md`, confirmed in prior research,
`docs/research/jev-pi-routing.md` §5a) is **$0.042 per million input tokens,
output free**, charged on every account including direct API access — there
is no free tier. This implementation always computes `estimated_cost_usd`
from the official $0.042/Mtok rate (`config.costPerMillionInputUsd` in
`jev.json`), never from Pi's own catalog object, specifically to avoid
under-reporting real spend the way `/session`'s own dollar figure would for
this provider route.

## Safety mechanisms, and why each exists

### Config validation: invalid config abstains, it does not silently fall back

A **missing** `jev.json` is fine (falls back to the same built-in defaults).
A **present but broken** `jev.json` — malformed JSON, `minConfidence` outside
`[0,1]`, `timeoutMs` non-finite/≤0/above the hard 5000ms ceiling, an unknown
or duplicate class name, non-finite/negative budget caps — makes every call
return `status:"skipped"` with `reason` one of `config_malformed` /
`config_invalid` / `config_unreadable`. It never merges a broken file onto
defaults and runs anyway: a config editing mistake must produce visible
abstention, not a silently different (possibly looser) threshold or timeout.
`PI_JEV_MODE=off` is checked **before** config is even loaded, so an explicit
opt-out always works even if the config file on disk is garbage.

### Budget: conservative worst-case reservation, no refund after dispatch

Each call reserves its estimated cost against the daily cap **before**
dispatching, computed from a deliberately worst-case UTF-8 byte bound
(`worstCaseRequestBytes()`): `MAX_TASK_CHARS` (2000) × 6 bytes/char — double
the worst realistic UTF-8 expansion of a JS string-length unit (3 bytes/char
for non-ASCII BMP characters), to absorb JSON-escaping overhead without
having to model it precisely — plus the exact measured byte size of the
fixed rubric (`questionsFor()`) plus a small fixed overhead. That byte count
is priced as if every byte were a billed input token, which over-reserves
relative to any real tokenizer (real tokenizers never produce more tokens
than input bytes), giving a safely conservative, non-configurable budget
hold rather than a guessed token count.

**The reservation is never refunded once a request is actually dispatched.**
A timeout or a non-`"stop"` classifier result does not prove the upstream
service billed nothing — the request may have reached TypeSafe's servers and
been processed before the response was lost or delayed. So:

- **Before dispatch** (classifier implementation could not be resolved —
  i.e. no request was ever sent): the reservation **is** released in full.
- **After dispatch** (timeout, thrown exception, non-`"stop"` result,
  malformed/out-of-range answer): the reservation **stays**, counting fully
  against both the daily call cap and the daily cost cap. This is
  deliberately conservative — a run of timeouts consumes real budget headroom
  — but it is the only way to avoid under-counting a budget that is supposed
  to be a hard spend ceiling.
- **After a genuinely successful, validated answer** (`ok` or `abstained` —
  both mean the call completed and returned a well-formed answer): the
  reservation is settled against the provider's own reported `usage.input`
  tokens at the published rate when available, else left at the conservative
  reservation.

Budget state (`${state}/jev/budget.json`) is read-modified-written inside the
same cross-process advisory lock (`.lock`, atomic `mkdir`, stale-after-5s
takeover) used for the ledger and cache, so concurrent launches cannot both
slip under a near-exhausted cap by racing the read. A concurrency test
(`Promise.all` of three calls against a one-call daily cap) asserts exactly
one wins. All budget/cache file writes are atomic (`write-to-temp` +
`rename`), so a crash mid-write cannot leave a half-written file.

### Budget corruption fails closed, not to zero

If `budget.json` exists but cannot be parsed into a valid
`{date, calls, costUsd}` shape, every call is denied with
`reason: "budget_corrupt"` rather than treating the unreadable file as "no
spend yet" — the latter would let a corrupted or tampered counters file
silently reopen an already-exhausted budget. A genuinely missing file
(first run) and an ordinary UTC-day rollover are both legitimate zero states
and are *not* treated as corruption; tests cover all three cases distinctly.

### Answer validation: whitelist + range, never trust a surprising answer

A classifier response is only accepted as `ok`/`abstained` if
`answers.task_class.type === "choice"`, `choice` is one of the **currently
configured** class labels (not just "any string"), and `confidence` is a
finite number in `[0, 1]`. Anything else — an unknown class name, a
confidence outside range, a missing/malformed answer — is `status:"error"`,
`reason:"unexpected_answer"`, and (per the asymmetry above) does not touch
the cost reservation or the cache, even if the response happened to carry a
`usage` object: an unexpected answer shape is reason enough not to trust
whatever else came with it.

### Cache: keyed on the decision inputs that matter, not just the task text

The cache key hashes `rubricVersion`, `model`, **`minConfidence`**, and the
**sorted class set**, together with the task text. Changing the confidence
threshold or the class taxonomy therefore invalidates old entries
automatically — a cached `ok` decision made under a looser threshold can
never be replayed as if it had passed a stricter one, without needing a
separate re-validation pass at read time. (A read-time structural check still
exists as defense in depth: a cache entry with an out-of-whitelist class, an
out-of-range confidence, or a non-finite `expiresAt` is discarded as a miss
rather than trusted, covering the case where `cache.json` itself has been
corrupted or hand-edited.) Only `status:"ok"` results are ever cached — never
`abstained`, never `error`. TTL default 24h, bounded to 500 entries
(oldest-`expiresAt`-first eviction), atomic writes, same advisory lock.

### Timeout: our own hard bound, not a hope that the client honors AbortSignal

`classifyTask()` passes its own `AbortController` to `classifyFn` and starts
the dispatch via `dispatchWithTimeout()`, which races the call against a
`Promise` that rejects at `timeoutMs + 250ms` grace regardless of what the
underlying implementation does with the signal. The abandoned original
promise is always given a no-op `.catch()`, so if it eventually does settle
after we've moved on, it can never surface as an unhandled rejection. Default
`timeoutMs` is 3000ms; config can tighten it but never loosen it past a hard
`HARD_MAX_TIMEOUT_MS = 5000` ceiling (enforced in `validateConfig()`), so a
misconfigured large timeout cannot blow past a ~3–5s bound. No retries
(`maxRetries: 0` passed explicitly to the classifier call).

**What was actually verified by reading, not assumed**: Pi's installed
`@earendil-works/pi-ai` TypeSafe System One client
(`dist/api/system-one-shared.js`, read directly while building this, no
network call made) threads a caller-supplied `options.signal` straight into
its `fetch()` call, and it never rejects on its own — every path, including
abort, resolves with `stopReason: "aborted"|"error"` and an `errorMessage`
this module never reads. So for that specific, verified client, aborting our
own controller *does* cancel the in-flight HTTP request; the Promise.race
backstop in this module is a safety net for any other `classifyFn`
(a different provider, a future SDK version, a test double) that might not
honor `AbortSignal` the same way, or that rejects instead of resolving.

**What was not verified, and is not claimed**: whether the live TypeSafe API
ever issues an HTTP redirect, and if so, whether this environment's `fetch`
implementation forwards or strips the `Authorization` header on it. Neither
this module nor the installed client sets an explicit `redirect` option on
the `fetch()` call, so behavior is whatever the active `fetch` runtime
defaults to (Node's built-in `fetch`/undici follows redirects and applies the
WHATWG Fetch spec's own credential-handling rules for cross-origin
redirects). No live request was made while building or testing this —
per the brief, real credentials/network were explicitly out of scope for this
implementation task — so this is a description of the code path that exists,
not a measured guarantee about redirect behavior against the real service.

### Credentials

`${XDG_CONFIG_HOME:-$HOME/.config}/jev/api-key` by default, overridable with
`PI_JEV_KEY_FILE`, or `TYPESAFE_API_KEY` env directly. Resolved once per call
inside `classifyTask`/`resolveApiKey`, passed only as the `apiKey` option to
the classify call, never logged, never written to any ledger/cache file,
never copied into Pi's own `auth.json`. A missing key produces
`status:"skipped", reason:"missing_key"` — quiet, not an error.

**Implementation-hygiene note**: while building this, an early ad-hoc smoke
test accidentally called `resolveApiKey`/`getStatus` with an environment
object that omitted `HOME`, so it fell back to the real `os.homedir()` and
read the real installed key file's *presence* (a boolean, never its
contents, never logged, never used in a network call). All 36 committed unit
tests and every CLI smoke check run after that point explicitly set
`HOME`/`XDG_CONFIG_HOME`/`PI_JEV_KEY_FILE` to temp directories so the real
key is never touched again. No live classify call was made against the real
TypeSafe API by this implementation at any point — all test/smoke
classifications use an injected synthetic `classifyFn`.

## What this explicitly does NOT do

- No routing, model selection, or launch-decision change of any kind.
  `applied` is hardcoded `false` everywhere.
- No automatic classification. The extension only classifies when a user
  runs `/jev classify <text>`; there is no `turn_start`/`session_start`
  hook. The CLI only classifies when explicitly invoked by the parent's
  delegate shell hook with `--task-stdin`.
- No file reading, no arbitrary command execution, no task content beyond a
  short stdin/typed string (≤2000 chars; the CLI's stdin reader hard-rejects
  anything exceeding 8192 raw bytes rather than classifying a silently
  truncated prefix).
- No codemode enablement, no new MCP server, no change to
  `claude-token-proxy`, `classes.json`, `routes.json`, or any other routing
  component owned elsewhere.
- No reimplementation of the TypeSafe wire protocol: `resolveClassifyFn()`
  imports Pi's own installed `@earendil-works/pi-ai` client via the package's
  public `./api/*` export map entry; this module never does its own `fetch`.

## Testing

`node --test tests/unit/test_jev.mjs` — 36 tests, all offline:
classification contract (ok/abstain/unexpected-answer), mode resolution
(`off` short-circuits even over a broken config; invalid mode values abstain
rather than defaulting to observe), config validation (every rejected shape
from `validateConfig`, malformed JSON, structurally invalid JSON), budget
(reservation math, no-refund-after-dispatch for both thrown exceptions and
non-`"stop"` results, release-only-before-dispatch, day rollover, corruption
fails closed, concurrency), cache (hit/miss, threshold/rubric sensitivity via
the cache key, never caching errors/abstains, cross-state-dir isolation),
status reporting, and a leak check that no result object ever contains
injected "secret" task text. No real credentials, no
`config/pi/node_modules` import, no network access in any test — every test
injects a synthetic `classifyFn`.

A local-only symlink `config/pi/node_modules -> ../../../../sync/src/dotfiles/config/pi/node_modules`
was created in this worktree (excluded via `.git/info/exclude`, not tracked)
solely to confirm `resolveClassifyFn()` resolves the real installed
`@earendil-works/pi-ai` `classify` export via Node's normal `node_modules`
walk-up; importing that module does not itself make a network call, and no
`fetch` was ever triggered through it during this implementation.

## Known limitations / handoff notes

- `resolveClassifyFn()`'s default specifier
  (`@earendil-works/pi-ai/api/typesafe-system-one`) only resolves when this
  module is used from inside a tree that has `config/pi/node_modules`
  populated (true for the real dotfiles checkout, not for this worktree
  without the local symlink). `JEV_CLASSIFY_MODULE` is available as an
  override for other layouts.
- The worst-case byte-to-cost reservation is intentionally pessimistic; a
  busy day of legitimately short tasks will reserve noticeably more than it
  ultimately spends per call. This trades reservation tightness for the
  simplicity of a single conservative, non-configurable bound rather than a
  tunable "typical task size" that could be set wrong.
- Parent owns: delegate shell wiring (confirmed as `bin/jev-classify
  --task-stdin --source delegate` once per dispatch, after dry-run/probe, 5s
  outer timeout, output discarded, never changes class/model), real private
  key installation at the default path, documentation/install steps, and the
  ≤3 authorized live verification calls against the real TypeSafe API.
- Sibling owns: the ledger reader/accounting tool that consumes
  `events.jsonl`; this implementation's zero-cost-bucket convention for
  cache hits and pre-dispatch skips (`cost_source:"cache"`, zero tokens) was
  confirmed against that reader's expectations before this doc was written.
