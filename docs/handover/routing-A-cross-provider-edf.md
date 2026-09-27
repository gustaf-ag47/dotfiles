# Brief A — Proactive cross-provider EDF routing (oracle `preferred` + pi extension)

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-a-cross-provider` (worktree, off
`feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh (see the launch prompt).
**Date:** 2026-09-27.

## Context

`bin/claude-token-proxy` pools three Anthropic OAuth accounts and picks per request by
*pressure* = `headroom / seconds_to_reset` (EDF weighted by headroom, `pressure()` ≈ line
1010) with a ×1.5 sticky band (`PICK_TOLERANCE`). That is only applied **inside** the
Anthropic pool. Across providers the system is **reactive fill-first**: `GET /_route?model=`
(`route_payload()`, ~line 1330) lists candidates `anthropic → openai-codex → deepseek` from
`config/llm-proxy/routes.json`, and `config/pi/extensions/llm-failover.ts` only calls
`pi.setModel()` after a request has already failed with the proxy's
`no OAuth account can serve` 503, switching back after two clean polls 60 s apart.

Consequence (measured 2026-09-27 13:40 UTC via `llm-usage`): Codex 7d at **100 % left,
resets in 6 days**, while Anthropic `gs@` is at 14 % (fable 2 %). Codex's weekly quota is
perishable too; fill-first lets it expire unused in any week where Anthropic just
suffices, and hits the cliff late in a week where it doesn't. The operator's goal is
"never run out of tokens" = spend every perishable window before it resets.

Design decisions that still stand (`docs/research/generic-llm-proxy.md`, decisions 1–5):
the proxy **never translates wire formats**; pi talks Codex/DeepSeek natively; the proxy is
the oracle, the extension does the switching; switching is notify-only (one line, never
ask). DeepSeek is money, not a window: it stays last and is **not** part of the EDF.

Parent commit to build on: `0072ad0 fix(proxy): expire stale readings, persist quota`
(read its message; `bucket_util(t, key, now)` and `rank_pool()` changed today).
Read `docs/handover/llm-proxy-implementation.md` and `docs/research/generic-llm-proxy.md`
§3(c) before touching code.

## Your job

1. **Oracle: Codex pressure + `preferred`.** In `codex_candidate()` add
   `pressure` computed exactly like the pool's (`(1 - used/100) / max(60, reset_at - now)`,
   unknown reset ⇒ 7 days, unknown usage ⇒ full headroom) from the cached `wham/usage`
   windows (use the *worst* window, same as `quota_left_percent`). Add `pressure` to the
   anthropic candidate (the chosen token's). Add a top-level `preferred` to the
   `/_route` payload: the routable candidate with the highest pressure, subject to
   (a) DeepSeek never preferred on pressure (only `first_routable` fallback),
   (b) a sticky band: a `current` query param (`/_route?model=…&current=<provider>`) keeps
   the current provider unless another's pressure is > `PICK_TOLERANCE` × better,
   (c) Codex model-level blocks (`models[model].available == false`) and
   `on_credits` exclude it from *preference* (credits are money).
   `first_routable` semantics must not change (tests in `RouteRankingTests` and
   `tests/unit/test_llm_failover.mjs` depend on it).
2. **Extension: proactive switching.** In `llm-failover.ts`, on `turn_start` (rate-limited
   to `RECOVERY_POLL_MS`, reuse the existing poll cadence) fetch `/_route` with `current=`,
   and if `preferred.provider` differs from the current provider, `setModel()` to it and
   print one line (`↪ …: codex week expiring unused (pressure 1.7 vs 1.5)` style — say
   *why*). Switch-back to Anthropic follows the same rule (it replaces the current
   two-confirmed-polls recovery path only when the switch was pressure-driven; keep the
   existing exhaustion→recovery path intact). Manual `/model` selection pins the provider
   (existing `onManualModelSelect`); add `/failover pin|unpin` to make that explicit and
   show it in `/failover status`. Switching happens only at turn boundaries — never
   mid-turn — to protect the prompt cache. Quality gate: never prefer a Codex target that
   is lower in the routes table than the first Codex entry for that model (e.g. fable →
   astra ok, fable → sol only as exhaustion fallback).
3. **Tests.** Python: put new proxy tests in a **new file**
   `tests/unit/test_proxy_cross_provider.py` (sibling B is adding tests to
   `test_claude_token_proxy.py`; avoid that file to prevent merge conflicts — you may
   *read* its fixtures and copy the small `OracleFixture` pattern). Cover: pressure
   arithmetic, `preferred` selection, sticky band, DeepSeek exclusion, on_credits
   exclusion, model block. TS: extend `tests/unit/test_llm_failover.mjs` with the
   proactive path (fake `/_route` returning `preferred`), the pin, and "no switch inside
   the band".
4. **Live verification** against the real proxy on `127.0.0.1:8788` (restart it with
   `systemctl --user restart claude-token-proxy.service`; it symlinks to the *parent*
   checkout `bin/claude-token-proxy`, so for a live run copy your file over temporarily
   or run a second instance on `CC_PROXY_PORT=8790` from your worktree — prefer the second
   instance; never leave the service pointing at a broken file). Show
   `curl -s 'localhost:8790/_route?model=claude-opus-5-5&current=anthropic' | jq .preferred`.
   Do **not** spend real quota beyond one or two tiny probe requests.
5. **Report** at `docs/handover/routing-A-cross-provider-edf-report.md`.

Done = all four gates green, report committed and pushed, parent handshake sent (below).

## Scope fence

- **You own:** `codex_candidate()`, `anthropic_candidate()`, `route_payload()`, the
  `/_route` handler and its query parsing in `bin/claude-token-proxy`;
  `config/pi/extensions/llm-failover.ts`; `tests/unit/test_llm_failover.mjs`;
  `tests/unit/test_proxy_cross_provider.py`; your report.
- **Do NOT touch:** `pick()`, `rank_pool()`, `pressure()`, `LAST_PICK`, `bucket_util()`,
  the request handler `_proxy()` / header parsing (sibling **B**); `fallback_target()`,
  `deepseek_*`, `_deepseek_fallback()` (sibling **C**); `usage_payload`/`/_usage` builder
  and `scripts/llm_usage.py` (sibling **D**); `tests/unit/test_claude_token_proxy.py`,
  `tests/unit/test_llm_usage.py`. If you need `pressure()` for Codex, **call it or
  factor a tiny pure helper next to `codex_candidate()`** — do not edit it.
- Siblings running in parallel: B (`feat/routing-b-affinity-5h`), C
  (`feat/routing-c-deepseek-backstop`), D (`feat/routing-d-observability`).

## Constraints

- Read `CLAUDE.md` fully. Python stdlib only in the proxy. `#!/usr/bin/env python3` stays.
- Gates (run and report **by name**, paste the summary lines):
  ```bash
  python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider tests.unit.test_llm_usage
  node --test --experimental-strip-types tests/unit/test_llm_failover.mjs
  make test-unit
  ```
- Git: conventional commits (hook enforces `type(scope): subject` ≤ 50 chars, lowercase).
  `GIT_EDITOR=true` for any rebase/merge continuation. **Parent owns merges** — push your
  branch, never merge to `master` or to `feat/pi-wait-for-quota-reset`.
- Scratch/logs: `scratch="$(pi-scratch dir routing-a)"`, never `/tmp`.
- Never log or print token values; fingerprints only (existing convention).

## Where to record findings

`docs/handover/routing-A-cross-provider-edf-report.md`: what changed, gates by name with
output, live `/_route` output, open questions, anything out of scope you noticed.

## When blocked

Record the blocker in the report, leave the branch reviewable, push, then do the handshake.

## Parent handshake (mandatory — do not just go idle)

When done **or** blocked, after pushing, print exactly one final message in this shape and
then wait for the parent's reply (stay in the session; do not exit):

```
PARENT: task A <done|blocked>. branch feat/routing-a-cross-provider @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-A-cross-provider-edf-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance

Target ≤ ~$15 of Codex/Anthropic usage. If you exceed it without a green gate, write up
and handshake as blocked.
