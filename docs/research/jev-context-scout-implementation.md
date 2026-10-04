# Jev file scouting: bounded library implementation

Status: implemented, not wired into any extension or caller yet. Branch
`feat/jev-context-scout`, worktree `/home/gustaf/.cache/jev-context/scout`.
Implements the scout-library half of
`docs/research/jev-context-scout-implementation.md`: a bounded, privacy-preserving
file-relevance triage helper that a sibling implementation (opt-in extension
+ freshness-aware read-dedup) will call. **No extension, no scripts, no
credentials, and no changes to `config/pi/lib/jev.mjs` were made or are
needed by this piece** — this module only imports already-exported helpers
from it.

## Files owned by this implementation

- `config/pi/lib/jev-scout.mjs` — the library. `scoutFiles()` is the only
  entry point a caller needs; everything else exported (`relevanceQuestions`,
  `defaultGit`, the size/count/timeout constants) exists to support tests or
  a caller that wants its own git backend.
- `tests/unit/test_jev_scout.mjs` — 45 offline/real-temp-git-repo tests, no
  real credentials, no real network, no real TypeSafe key ever read (every
  test injects its own `classifyFn`).

## What this is NOT

- Not the task classifier (`interactive|build|research|mechanical`). That
  contract in `jev.mjs`/`classifyTask()` is untouched; this module never
  calls it and never changes its behavior.
- Not an extension, not a tool definition, not wired into any Pi command or
  turn hook. A caller (the sibling implementation) decides when and whether
  to invoke `scoutFiles()`, and must set `enabled: true` explicitly.
- Not a repository scanner. It only ever looks at paths the caller passes in
  (`paths: [...]`, max 8). It never lists a directory, never globs, never
  walks the tree.

## Interface actually implemented

```js
import { scoutFiles } from "config/pi/lib/jev-scout.mjs";

const result = await scoutFiles({
  cwd,                 // string, required: anchors path resolution + git root lookup
  goal,                 // string, 1..1000 chars, required
  paths,                // string[], 1..8 entries, required; explicit candidates only
  enabled: true,         // MUST be explicitly true, or nothing below runs at all
  signal,                // optional caller AbortSignal; really cancels in-flight requests
  env, fsImpl, configPath, config, classifyFn, git, cache, now, stateDir, // all optional, for tests/callers
});

// result shape:
{
  items: [
    { path, relevance: "relevant"|"uncertain"|"unrelated", confidence: number|null, reason?: "<safe_code>", cacheHit?: true },
  ],
  skipped: [
    { path, reason: "<safe_code>" },
  ],
  stats: {
    networkCalls, cacheHits, inputTokens, estimatedCostUsd, unknownCostCalls,
    candidates, disabledReason, elapsedMs,
  },
  usage: { input, output, cacheRead, cacheWrite, totalTokens, cost: { input, output, cacheRead, cacheWrite, total } },
  // ^ matches Pi's own `Usage` shape (@earendil-works/pi-ai), so a caller can
  //   fold it into its own accounting with the same `addUsage()`-style merge
  //   it already uses for model usage, instead of inventing a parallel shape.
}
```

`skipped[].reason` and `items[].reason` are always one of a small fixed set
of safe codes (`disabled`, `mode_off`, `invalid_mode`, `config_invalid`,
`missing_key`, `classifier_unavailable`, `not_git_repo`, `git_error`,
`path_outside_repo`, `symlink`, `path_swapped`, `not_found`,
`not_git_tracked`, `gitignored`, `sensitive_path`, `sensitive_content`,
`binary_file`, `not_regular_file`, `oversized_file`, `total_bytes_exceeded`,
`read_error`, `budget_exceeded`, `budget_unavailable`, `low_confidence`,
`timeout`, `classifier_error`, `unexpected_answer`, `aborted`,
`invalid_path`, `too_many_paths`, `goal_invalid`, `goal_too_long`,
`invalid_paths`, `no_paths`, `invalid_cwd`) — never a raw path fragment,
prompt, or provider error string.

## Why some candidates land in `items` (uncertain) and others in `skipped`

A candidate only reaches `items` once this module has decided it's safe to
send to the classifier (tracked, not ignored, not sensitive, within size
bounds, not a symlink, not obviously secret content) — everything after that
point that still doesn't produce a confident verdict (budget exhausted,
timeout, malformed answer, low confidence) becomes `relevance: "uncertain"`
in `items`, never `"unrelated"` and never silently dropped. Anything that
fails a *safety* check before that point never reaches the classifier at
all, so it goes to `skipped` instead — it was never assessed, so it would be
actively misleading to report it as "uncertain" alongside genuinely-assessed
files.

## Security/safety mechanisms, and their honestly-documented limits

### Path safety

- Only candidate paths explicitly passed by the caller are touched.
- Each candidate is resolved relative to `cwd`, then every path component
  from the git repo root down to the file (inclusive) is `lstat`'d and
  rejected if any of them is a symlink — not just the final leaf. A plain
  `realpathSync` round-trip check backs this up.
- The file is then opened with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` and read
  from the resulting file descriptor (never re-opened by path), closing the
  symlink-swap TOCTOU window between the ancestor-chain check and the
  actual read. `O_NONBLOCK` specifically defends against a tracked regular
  file being replaced by a writer-less FIFO at the same path: without it,
  opening a FIFO for read-only blocks until something opens it for write,
  which would otherwise hang the whole `scoutFiles()` call; `O_NONBLOCK` has
  no effect on reads from an actual regular file, and the immediately-
  following `fstat().isFile()` check rejects the FIFO as `not_regular_file`
  either way. After the bounded read, BOTH `realpathSync` (path identity)
  AND a fresh `lstatSync`'s `dev`/`ino` compared against the opened fd's own
  `fstat` (inode identity) are re-checked; a mismatch on either discards the
  content and reports `symlink` or `path_swapped` respectively. The inode
  check specifically catches a same-path unlink+recreate race that never
  involves a symlink at all (verified with a synthetic `fsImpl` in tests,
  since winning a real race deterministically isn't possible).
- The read is hard-bounded to `MAX_FILE_BYTES + 1` bytes regardless of what
  `stat`/`fstat` claims the size is.
- Git truth (tracked, not ignored) is established by shelling out to the
  real `git` binary (`ls-files --error-unmatch`, `check-ignore --no-index`)
  with a bounded timeout and (where git supports it) `--literal-pathspecs`
  so a filename containing pathspec-magic characters (`*`, `?`, `[`,
  `:(...)`) is never reinterpreted as a glob by git. **Limitation, verified
  against the installed git 2.55.0 on this host**: `git check-ignore`
  itself refuses `--literal-pathspecs` outright ("pathspec magic not
  supported by this command") — a documented git limitation, not a choice
  made here. `isIgnored()` is therefore the one git call in this module
  without that specific guarantee; a candidate filename containing literal
  pathspec-magic characters could in principle be misinterpreted by that one
  subcommand. This is a narrow, specific, documented residual risk, not a
  general weakness of the tracked/path checks.
- Any git command that times out, fails to spawn, or exits with a code
  neither "yes" nor "no" documents for that subcommand is treated as
  `"error"` and the candidate is rejected (`git_error`) — a git failure
  never silently becomes "fine to proceed."

### Sensitive path/content filtering (best-effort, not exhaustive)

- A fixed regex denylist rejects common credential/key/dotfile locations
  (`.env*`, `.npmrc`, `.pypirc`, `.netrc`, `.ssh/`, `.aws/`, `.grok/`,
  `.pi/`, `auth.json`, anything with `credential`/`secret` in the path,
  private-key filenames and extensions, `local/`, `private/`, and common
  generated-dependency directories) before any file is opened.
- A fixed regex scan of file content rejects obvious secret literals
  (PEM private-key headers, AWS access keys, GitHub/Slack tokens, JWTs, and
  a generic `key/secret/token/password = "..."` assignment pattern — not
  anchored to word boundaries, so an identifier like `TYPESAFE_API_KEY`
  still matches) before the content is ever sent anywhere.
- **Neither list is a secret scanner.** They catch the obvious, common
  cases and are intentionally tuned toward false positives (skip something
  that was actually fine) over false negatives. A secret in an unusual
  format, a custom key name, or an unlisted directory convention will not
  be caught. Treat `sensitive_path`/`sensitive_content` skips as "this
  module refused to risk it," not as a guarantee that everything it *did*
  send is clean.

### Privacy of the classifier payload

- The classify request body is exactly `{ goal, file_content }` plus the
  fixed relevance rubric questions. The file's path/name is never included,
  so the model literally cannot see, reason about, or invent a path — it
  can only describe the content it was given.
- Ledger events never contain a path, the goal text, file content, or any
  raw provider error string — only the fixed `jev-event.v1` schema fields
  (status, model, rubric version, token counts, cost, timing), with
  `purpose: "file-scout"`, `class: null`, `applied: false`.

### Budget, caching, timeouts

- Reuses `config/pi/lib/jev.mjs`'s `reserveBudget`/`DEFAULT_CONFIG`/config
  loading unchanged — scout calls draw from the **same** daily call/cost
  caps as the task classifier, not a separate pool. A reservation is only
  released when no request was ever dispatched (classifier unavailable,
  budget already exhausted, or the shared overall deadline already elapsed
  before that candidate's turn); a dispatched-but-failed/timed-out request
  keeps its reservation, exactly like `classifyTask()`.
- The reserved cost per candidate is computed from the actual bytes about to
  be sent (goal + this file's real content + the fixed rubric), not a
  worst-case guess — tighter and still conservative, since it's the real
  request size.
- Successful verdicts are cached in a bounded in-memory `Map` (never written
  to disk, no file content retained after the call returns), keyed on the
  real absolute path, a SHA-256 of the file's current content, the goal
  text, the model id, and the confidence threshold — so an edited file or a
  changed goal always reclassifies, and a config change invalidates the
  whole cache. Errors are never cached.
- Each classify dispatch is bounded to 3 seconds; the whole call is bounded
  to a shared ~15-second overall deadline anchored at call entry (so
  preflight git/config work counts against it, not just dispatch time), plus
  the caller's own `AbortSignal` — both abort the in-flight classifier
  request itself (a shared `AbortController` threaded through), not merely a
  local backstop timer. `maxRetries: 0` is passed to the classifier on every
  call. The deadline is re-checked (not just computed once) at the start of
  each candidate's processing AND again immediately after that candidate's
  own (synchronous, subprocess-spawning) git preflight calls, so a slow
  filesystem/git cannot let several candidates' worth of blocking preflight
  work silently run past the shared bound before any per-call remaining-time
  check ever executes.
- Reported token usage is only ever trusted when it is a non-negative safe
  integer; a negative, fractional, or otherwise malformed value from a
  misbehaving classifier implementation is treated as unknown (counted in
  `stats.unknownCostCalls`) rather than producing a negative number in the
  returned `usage` aggregate or under-settling the budget reservation.

## Verification performed on this host

- `node --test tests/unit/test_jev_scout.mjs`: 45/45 passing, using real
  temporary git repositories (via the actual installed `git` binary against
  throwaway `git init` repos) and synthetic injected `classifyFn`s — no real
  TypeSafe key was read, no real network call was made.
- `node --test tests/unit/test_jev.mjs`: 36/36 still passing, confirming
  this module's imports from `jev.mjs` didn't require or trigger any change
  to that file or its own test suite.
- `git diff --check` on the owned files: clean.
- Confirmed directly against this host's installed `git 2.55.0` that
  `check-ignore --literal-pathspecs` fails with "pathspec magic not
  supported by this command" (hence the documented, scoped exception above)
  while `ls-files`/`rev-parse` accept it normally.

## Known gaps / follow-ups for the integrating caller

- This module does not decide *when* to scout, does not read any session or
  conversation state, and does not suppress duplicate reads — that is
  explicitly the sibling implementation's responsibility per the handover
  brief's task split.
- `usage` is only populated for calls that actually dispatched and returned
  a usable `usage.input`; `stats.unknownCostCalls` counts every dispatched
  call (success or failure) where token usage was not reported, so a caller
  doing its own accounting can see "N calls happened whose real cost is
  unknown" rather than it silently reading as zero.
- The in-memory cache (`DEFAULT_CACHE`) is a module-level singleton shared
  by all callers in one process by default; a caller that wants isolation
  (e.g., per-session) should pass its own `cache: new Map()`.
