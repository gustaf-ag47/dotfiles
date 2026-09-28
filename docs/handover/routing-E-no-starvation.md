# Brief E — P1 "no starvation": `llm-wait`, DeepSeek spend cap, starvation counter

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-e-no-starvation` (worktree off
`feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh.
**Date:** 2026-09-28.

## Context

Read first, in this order: `docs/research/routing-10-of-10-plan.md` (§0 metrics, §3 Phase 1 —
you are E1, E2-cap, E4), then `docs/handover/routing-A-cross-provider-edf-report.md`,
`routing-C-deepseek-backstop-report.md`, `routing-D-observability-report.md` (all merged on
your base branch; A–D are done). `bin/claude-token-proxy` is a ~2000-line stdlib Python
proxy; `scripts/llm_usage.py` renders `llm-usage`; `/_usage`, `/_route?model=&current=`,
`POST /_event` exist.

P1 says: no request may fail for quota while any capable provider has headroom. Today's
gaps: (a) batch loops (`ralph/*/loop.sh` in other repos, `delegate.sh` children) die on the
proxy's `no OAuth account can serve` 503 instead of waiting for the next reset — only
interactive pi waits (`llm-failover.ts`, decision 4); (b) DeepSeek, once funded, has no
spend ceiling, so it cannot be left routable with confidence; (c) nobody counts P1
violations, so we cannot prove P1 = 0.

## Your job

1. **E1 `bin/llm-wait`** (Python or bash calling `python3`, stdlib only). Blocks until a
   predicate over `/_usage` holds, polling every `--poll` (default 60 s), giving up after
   `--max` (default 6h, exit 2). Predicate mini-language over these terms:
   `anthropic.base.left`, `anthropic.oi.left`, `anthropic.5h.left` (best account, percent),
   `anthropic.routable` (bool = `/_route` anthropic candidate routable for `--model`),
   `codex.left`, `codex.routable`, `deepseek.routable`, `any.routable`; operators
   `>= <= > < == and or not ( )`. Examples in `--help`:
   `llm-wait --until 'any.routable' --model claude-sonnet-5`,
   `llm-wait --until 'anthropic.base.left>=20 or codex.left>=20'`. Prints one line when it
   starts waiting (with the earliest known reset from the oracle) and one when it returns.
   Exit 0 = predicate true, 2 = timeout, 3 = proxy unreachable (after `--max`? no: after 3
   consecutive failures, so a dead proxy does not block for 6h silently). Never parses
   with `eval`; write a tiny tokenizer + recursive-descent evaluator and unit-test it
   (`tests/unit/test_llm_wait.py`, drive it against a fake `/_usage`/`/_route` HTTP server
   like `tests/unit/test_pi_wait_for_reset.py` does).
2. **E1b Wire it into the launchers we own.** `config/pi/skills/delegate/scripts/delegate.sh`
   **and** the live copy `~/.pi/agent/skills/delegate/scripts/delegate.sh` (they have
   diverged; apply the same minimal hunk to both): before the model probe, if the chosen
   provider is not routable, run `llm-wait --until '<provider>.routable' --max
   ${PI_DELEGATE_WAIT_MAX:-2h}` instead of failing over immediately; keep the existing
   Codex→Claude fallback as the step *after* a timed-out wait. Document the knob in
   `config/pi/skills/delegate/SKILL.md`. Add a paragraph to `config/pi/skills/ralph-loop/SKILL.md`
   telling generated loops to call `llm-wait` before each iteration and on a 503.
3. **E2-cap DeepSeek monthly spend ceiling.** In the proxy: `CC_PROXY_DEEPSEEK_MONTHLY_CAP`
   (USD, default 20). Track spend from the balance readings the proxy already polls
   (`refresh_providers()` → deepseek state): persist `{"month": "YYYY-MM", "start_balance":
   x, "min_balance": y}` in `usage.json` under `_deepseek_spend`; spend = start − current
   (top-ups raise current, so recompute `start_balance` when balance *increases*). When
   spend ≥ cap, `deepseek_candidate()` returns `routable=False, reason="monthly cap"`,
   `fallback_target()` refuses, and `llm-usage` shows `cap $X/$Y`. Unit tests with synthetic
   balance sequences including a top-up mid-month and a month rollover.
4. **E4 Starvation counter.** In `_proxy()`, when the proxy is about to return the
   "no OAuth account can serve" 503 (or a DeepSeek refusal), call `route_payload(model)`;
   if it has a `first_routable`, increment `routing.starved` (persisted in `usage.json`,
   with `last` = `{ts, model, first_routable.provider}`), and `append_route()` an event
   `{"kind": "starved", ...}`. Expose `routing.starved` in `/_usage`; `llm-usage` prints
   `starved this week: N` under `routing` (red when > 0). Unit test via the existing
   `DeepseekPassthroughTests` fixture pattern (force cooldowns, codex routable → 503 →
   counter 1).
5. **Live check** on a second instance (`CC_PROXY_PORT=8790`, separate `XDG_CACHE_HOME`
   under `$(pi-scratch dir routing-e)`, `CCTOKEN_FILE=$HOME/cctoken`): put all fingerprints
   in that instance's `force_cooldown`, run `llm-wait --until anthropic.routable --max 90s`
   → expect exit 2 with a sensible wait line; remove the file → expect exit 0 within one
   poll. Paste both.
6. **Report** `docs/handover/routing-E-no-starvation-report.md`.

Done = gates green, live output pasted, pushed, handshake.

## Scope fence

- **You own:** `bin/llm-wait`, `tests/unit/test_llm_wait.py`; in the proxy: `deepseek_candidate()`,
  `fallback_target()`, the deepseek part of `refresh_providers()`, a new `_deepseek_spend`
  key in save/restore, the 503 branch of `_proxy()` (counter only — do not restructure the
  loop), `routing.starved` in `usage_payload()`; `scripts/llm_usage.py` lines for cap and
  starved; delegate.sh (both copies) minimal hunk; the two SKILL.md paragraphs; your report;
  new tests in `tests/unit/test_proxy_no_starvation.py`.
- **Do NOT touch:** `pick()`, `rank_pool()`, `pressure()`, `spread_choice()`, `LAST_PICK`
  (wave 2 siblings F/G); `route_payload()` ranking logic, `codex_candidate()`, `classes`
  (sibling **H** is adding `?class=` to `/_route` and `config/llm-proxy/classes.json`);
  `config/pi/extensions/*` (H owns the class header; llm-failover.ts is frozen);
  `config/claude-code/env.sh`, waybar, `tests/unit/test_proxy_observability.py` (sibling **I**).
- Siblings in parallel: H (`feat/routing-h-task-classes`), I (`feat/routing-i-hygiene`).

## Constraints

- `CLAUDE.md`; stdlib only; `#!/bin/bash` + `set -euo pipefail` + shellcheck for bash;
  never log token values. Tests must patch `CONTROL_DIR`/`USAGE_STATE_FILE`/`ROUTING_LOG`
  to a temp dir — never write to the real `~/.cache/cc-proxy` (a previous test leaked).
- Gates (report by name): `python3 -m unittest tests.unit.test_llm_wait tests.unit.test_proxy_no_starvation tests.unit.test_claude_token_proxy tests.unit.test_llm_usage`; `make test-unit`; `shellcheck` on every touched .sh.
- Conventional commits (≤ 50-char subject); `GIT_EDITOR=true`; parent owns merges — push only.
- Scratch: `pi-scratch dir routing-e`. Never touch port 8788 or the live cache.

## Parent handshake (mandatory)

```
PARENT: task E <done|blocked>. branch feat/routing-e-no-starvation @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-E-no-starvation-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance — ≤ ~$15.
