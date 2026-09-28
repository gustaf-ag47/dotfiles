# Brief G — P3 "no self-inflicted 5h stalls": fleet sizing, 5h-pressure moves, burst ramp

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-g-no-5h-stalls` (worktree off
`feat/pi-wait-for-quota-reset` **after wave 1 (E, H, I) is merged**).
**Parent:** the tmux window recorded by delegate.sh. **Date:** 2026-09-28 (wave 2).

## Context

Read first: `docs/research/routing-10-of-10-plan.md` §0 P3, §3 Phase 3 (G1–G3). Then
`routing-B-affinity-5h-report.md` (session affinity: `LAST_PICK[(session,bucket)]`,
`spread_choice()`, `session_key_from()`, `pressure()=min(p7d,p5h)`),
`routing-D-observability-report.md` (`_samples`, `burn_per_hour`), `routing-I-hygiene-report.md`
(`llm-usage --week` P3 approximation), and `docs/research/claude-token-rotation-oss.md` §3
(hot-spotting; teamclaude's post-switch ramp).

P3: a session must never stop because *its* account's 5h window is spent while another
account has 5h headroom. B spreads *new* sessions; three gaps remain: (1) nothing tells the
operator how many heavy sessions the pool can carry right now, so fleets are sized blind;
(2) an existing session stays glued to its account until a 429, even when its 5h pressure
has collapsed and a natural boundary would allow a cheap move; (3) after any move the new
account can get a burst of concurrent requests and 429 on the per-minute limit.

## Your job

1. **G1 `llm-usage --capacity`.** From `/_usage`: per account, 5h headroom (fraction) and
   D's 5h `burn_per_hour`; estimate `sessions_supported = Σ_accounts floor(headroom_5h /
   (per_session_burn × hours_horizon))` for `--horizon` (default 2 h), where
   `per_session_burn` = median 5h burn per active session over the last hour (active
   sessions = distinct affinity keys touched in the last 15 min — expose
   `routing.active_sessions` from `LAST_PICK` in `usage_payload()`, count only). Print:
   `capacity: N more heavy sessions are safe for the next 2h (accounts: a 3, b 1, c 0)`.
   `--json` too. `delegate.sh` (both copies, minimal hunk): before spawning, query it and
   print a **warning** (not a block) when N ≤ 0. Unit tests with synthetic `/_usage`.
2. **G2 5h-pressure session moves at natural boundaries.** In `pick()`: when a session's
   affinity account has `pressure_5h` below the pool's best by more than the tolerance band
   **and** the request looks like a boundary — define: the request's `messages` length ≤ 2
   (fresh context after compaction / new task), or the header `x-cc-proxy-boundary: 1`
   (pi's compaction hook can set it later; not in this task) — move the session to the
   spread choice and log `reason=5h` via `append_route()`. Otherwise stay (cache wins).
   `rank_pool()` mirrors it given `messages_len`. Tests: move at boundary; no move mid-
   conversation; parity.
3. **G3 Burst ramp.** After a move (any `append_route` reason) into account X, cap X's
   concurrent in-flight requests to `CC_PROXY_RAMP_CONCURRENCY` (default 2) for
   `CC_PROXY_RAMP_SECONDS` (default 60): further requests for X wait on a per-token
   `threading.Semaphore` **outside `LOCK`** (never block the picker), with a 5 s cap on the
   wait after which they proceed anyway. Track in-flight counts in `_proxy()` around
   `upstream()` (existing `record_request`/`_stream` sites — a `try/finally` decrement).
   Keep it under ~40 lines. Tests: third concurrent request is delayed during the ramp;
   no delay after `RAMP_SECONDS`; the picker is never blocked (assert `LOCK` not held while
   waiting).
4. **Live check** on a second instance (isolated cache, real `cctoken`): six concurrent
   haiku `max_tokens:1` requests with six distinct `x-cc-proxy-session` values; paste the
   proxy log showing spread across accounts and no 429; then `llm-usage --capacity`
   against that instance. (~6 tiny requests; allowed.)
5. **Report** `docs/handover/routing-G-no-5h-stalls-report.md`.

## Scope fence

- **You own:** in the proxy: `spread_choice()`, the affinity/5h-move logic in `pick()` and
  `rank_pool()`, ramp semaphore + in-flight counters in `_proxy()`, `routing.active_sessions`
  in `usage_payload()`; `scripts/llm_usage.py` `--capacity`; delegate.sh warning hunk (both
  copies); tests in `tests/unit/test_proxy_5h.py`; your report.
- **Do NOT touch:** `pressure()` internals and the sweep boost, `codex_candidate()`,
  `llm-schedule` (sibling **F**); classes; `llm-failover.ts`; `anthropic-pool.ts`.
- Sibling in parallel: F (`feat/routing-f-no-waste`). You both edit `pick()`: F changes one
  line (threshold lift); keep your edits inside clearly delimited helper calls so the merge
  is trivial.

## Constraints — as briefs A–E: `CLAUDE.md`, stdlib only, shellcheck, tests isolated via
`tests/unit/proxy_fixture.py`, never touch port 8788 or the live cache.
Gates (by name): `python3 -m unittest tests.unit.test_proxy_5h tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`; `make test-unit`; `shellcheck` on touched .sh.
Conventional commits (≤ 50 chars); `GIT_EDITOR=true`; parent owns merges. Scratch `pi-scratch dir routing-g`.

## Parent handshake (mandatory)

```
PARENT: task G <done|blocked>. branch feat/routing-g-no-5h-stalls @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-G-no-5h-stalls-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance — ≤ ~$15.
