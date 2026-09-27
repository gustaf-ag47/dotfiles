# Brief B — Session affinity and 5h-aware selection in the Anthropic pool

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-b-affinity-5h` (worktree, off
`feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh (see the launch prompt).
**Date:** 2026-09-27.

## Context

`bin/claude-token-proxy` picks an OAuth token per request in `pick()` (~line 1020):
eligible tokens → below `ROTATE_THRESHOLD` on the weekly bucket → highest
`pressure()` (= 7d headroom / seconds to reset) → sticky to `LAST_PICK[bucket]` within
`PICK_TOLERANCE` (×1.5). `rank_pool()` is the read-only dry run and **must stay
identical in outcome to `pick()`** (parent commit `0072ad0` made them agree; there is a
test `test_preview_matches_picker_for_threshold_fallback_and_legacy_mode`).

Two gaps hurt "never run out of tokens" **within a day**:

1. **`LAST_PICK` is global per bucket.** Every concurrent session (pi delegate
   sub-agents, ralph loops, several `claude` windows) is glued to the same account and
   burns its 5h window while the two others idle: 1× the 5h burst capacity instead of 3×.
   Research (`docs/research/claude-token-rotation-oss.md` §4, "Sticky sessions /
   prompt-cache affinity") recommends per-session affinity; never implemented.
2. **The 5h window is ignored by selection.** `pressure()` reads only 7d; `u5` is used
   only as a tie-break in the legacy `headroom` mode. A token with `u5` at 0.99 is still
   picked, gets a 429, and only then cools down and rotates — a full failed round trip
   and a cooldown that could have been avoided.

Prompt cache is per account: switching accounts mid-conversation costs cache-hit
input tokens, which is why stickiness exists. Affinity must therefore be
**per conversation**, not global and not per request.

Known facts about identifying a session: Claude Code sends
`metadata.user_id` in the Messages body (a string containing the session id); pi's
requests carry no session marker today. The parent will let sibling A know if you need
an extension-side header — but design for **body/headers already available first**:
`x-cc-proxy-session` header if present, else `metadata.user_id`, else a stable hash of
the system prompt (`system` field), else the global bucket key (today's behaviour).

## Your job

1. **Session-keyed stickiness.** Replace the global `LAST_PICK[bucket]` with an
   affinity map keyed by `(session_key, bucket)` with an LRU/expiry (e.g. 1000 entries or
   6 h idle) so it cannot grow unbounded. A new session gets the max-pressure token
   **among the least-loaded** — i.e. spread: prefer the eligible token with the fewest
   active sessions in the last N minutes when pressures are within the tolerance band.
   `rank_pool()`/`/_usage` routing preview must accept an optional session key and
   still mirror `pick()` exactly; `last_pick` in the payload becomes the affinity for
   the queried session (or the most recent overall when none is given). Keep
   `CC_PROXY_PICK=headroom` legacy behaviour untouched.
2. **5h-aware eligibility and pressure.** Treat `five_hour_util(t, now) >= ROTATE_THRESHOLD`
   as an over-threshold preference exactly like the weekly check (skip when any
   below-threshold token exists; still pickable when nothing else is). Make the pressure
   score `min(pressure_7d, pressure_5h)` where `pressure_5h = headroom_5h / seconds_to_5h_reset`
   (unknown ⇒ full headroom / 5 h). Keep the sticky band so an in-flight session is not
   bounced by a slightly better token. Update `readings_expired()` callers if needed.
   Document the formula change in the module docstring's "Token selection" paragraph.
3. **Hot-spot ramp (small).** When a session is *moved* because its token went into
   cooldown, log it once with the reason; do not implement teamclaude's concurrency ramp
   unless it is < 30 lines — note it as future work otherwise.
4. **Tests** in `tests/unit/test_claude_token_proxy.py` (you own it; sibling A writes
   to a new file). Cover: two sessions get two different tokens when pressures are
   within band; same session stays on its token; session moves on cooldown; 5h
   over-threshold skipped when an alternative exists; 5h pressure dominates when the 5h
   window is nearly spent; preview/picker parity with a session key; expiry of the
   affinity map. Keep every existing test green (do not delete tests; adjust only where
   the behaviour change is intended and say so in the report).
5. **Live verification** on a second instance (`CC_PROXY_PORT=8790` from your worktree,
   `CCTOKEN_FILE=$HOME/cctoken`): two `curl` Messages requests with different
   `metadata.user_id` values (`max_tokens: 1`, model `claude-haiku-4-5`) land on
   different accounts; a third with the first id lands on the first account. Show the
   journal/log lines. Do not restart the user's `claude-token-proxy.service`.
6. **Report** at `docs/handover/routing-B-affinity-5h-report.md`.

Done = gates green, report pushed, parent handshake sent.

## Scope fence

- **You own:** `pick()`, `rank_pool()`, `pressure()`, `five_hour_util()`, `bucket_util()`,
  `LAST_PICK`/its replacement, `readings_expired()`, request-body/header parsing in
  `_proxy()` needed to derive the session key, the module docstring paragraph on
  selection; `tests/unit/test_claude_token_proxy.py`; your report.
- **Do NOT touch:** `codex_candidate()`, `anthropic_candidate()`, `route_payload()`, the
  `/_route` handler (sibling **A** — note A reads `rank_pool()["would_pick"]`; keep that
  key and its meaning); `fallback_target()`, `deepseek_*`, `_deepseek_fallback()`
  (sibling **C**); the `/_usage` payload builder beyond adding your affinity fields to
  `routing.buckets[*]`, and `scripts/llm_usage.py` (sibling **D**);
  `config/pi/extensions/*`; `tests/unit/test_llm_failover.mjs`, `tests/unit/test_llm_usage.py`.
- Siblings running in parallel: A (`feat/routing-a-cross-provider`), C
  (`feat/routing-c-deepseek-backstop`), D (`feat/routing-d-observability`).

## Constraints

- Read `CLAUDE.md` fully. Python stdlib only. Never log token values.
- Gates (report **by name** with the summary lines):
  ```bash
  python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_llm_usage
  make test-unit
  ```
- Conventional commits (hook: `type(scope): subject` ≤ 50 chars). `GIT_EDITOR=true` for
  rebase/merge continuation. **Parent owns merges** — push your branch only.
- Scratch: `scratch="$(pi-scratch dir routing-b)"`, never `/tmp`.

## Where to record findings

`docs/handover/routing-B-affinity-5h-report.md`: design (key derivation, map bounds,
formula), gates by name with output, the live two-session evidence, behaviour changes to
existing tests (if any) with justification, future work (ramp).

## When blocked

Record it in the report, leave the branch reviewable, push, handshake as blocked.

## Parent handshake (mandatory — do not just go idle)

When done **or** blocked, after pushing, print exactly one final message in this shape and
then wait for the parent's reply (stay in the session; do not exit):

```
PARENT: task B <done|blocked>. branch feat/routing-b-affinity-5h @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-B-affinity-5h-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance

Target ≤ ~$15. If exceeded without a green gate, write up and handshake as blocked.
