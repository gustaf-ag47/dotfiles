# Brief H — P4 "cheapest adequate tier": task classes, per-entry-point defaults, escalation

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-h-task-classes` (worktree off
`feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh.
**Date:** 2026-09-28.

## Context

Read first: `docs/research/routing-10-of-10-plan.md` — §0 P4, §3 Phase 4 (H1–H3), **§4 the
class table** (your spec). Then `routing-A-cross-provider-edf-report.md` (how `/_route`,
`preferred`, `current=` and `llm-failover.ts` work now) and
`config/pi/extensions/anthropic-pool.ts` (how pi sends `x-cc-proxy-session`; you add a
class header the same way).

Today every entry point burns the same tier: interactive pi, `delegate.sh` children, ralph
loops all default to opus/fable-class on Anthropic or luna on Codex. The fable bucket
(`7d_oi`) is the one that actually runs out (gs@ hit 1 % this week). P4 target: < 10 % of
delegate/loop tokens billed to opus/fable buckets. The human's interactive session must
**never** be downgraded automatically.

`routes.json` maps Claude model → substitutes and stays as the *like-for-like* table for
failover. Classes are a layer above it.

## Your job

1. **H1 `config/llm-proxy/classes.json`** exactly per plan §4 (interactive, build,
   research, mechanical), each an ordered list of `[provider, model]` plus an optional
   `ceiling` object, e.g. `{"anthropic": {"oi_max_used": 0.7, "no_oi": true}}` meaning:
   this class may not be served from an account whose `7d_oi` utilization is above 0.7 /
   may not use fable models at all. Loaded like `routes.json` (mtime reload, invalid file
   keeps the previous table, `CC_PROXY_CLASSES` override).
2. **H1b Oracle.** `GET /_route?class=<name>[&current=]` returns the same shape as
   `?model=` but ranks the class's list: for each entry compute the candidate exactly as
   today (`anthropic_candidate` for anthropic entries with that model, `codex_candidate`,
   `deepseek_candidate`), apply the class ceiling (Anthropic account rows above the ceiling
   are ineligible with reason `"class ceiling"`), `preferred` = highest pressure among
   eligible non-DeepSeek entries **but** for class `mechanical` DeepSeek is first-choice
   when routable (plan §2 principle 1: money is chosen by class, not pressure). `?model=`
   behaviour is unchanged. Add `class` to the payload.
3. **H2 Enforcement header.** In the proxy `_proxy()`: read `x-cc-proxy-class`
   (default `interactive`); pass it to `pick(... class_name=)` **only** as an eligibility
   filter applied before the existing logic (accounts over the class's `oi_max_used` are
   excluded for `oi`-bucket requests; if `no_oi` and the model is a fable model, return the
   503 with a clear message `class <x> may not use <model>`). Keep the change to a small
   filter function `class_eligible(t, class_name, bucket, now)` called in one place in
   `pick()` and one in `rank_pool()`; do not restructure either.
4. **H2b Defaults per entry point.**
   - `anthropic-pool.ts`: send `x-cc-proxy-class` from `PI_LLM_CLASS` env (default
     `interactive`), Anthropic requests only, next to the session header. Test in
     `tests/unit/test_anthropic_pool.mjs`.
   - `delegate.sh` (repo copy `config/pi/skills/delegate/scripts/delegate.sh` **and** live
     `~/.pi/agent/skills/delegate/scripts/delegate.sh`, minimal identical hunk): `--class`
     (default `build`) → exports `PI_LLM_CLASS` to the child and, when no `--model` was
     given, picks the model from `/_route?class=` `preferred` instead of the hardcoded
     default. `--class interactive` restores today's behaviour.
   - `config/pi/skills/ralph-loop/SKILL.md`: generated loops set `RALPH_CLASS` (default
     `build`; `mechanical` for lint/format/bulk-edit loops) and export `PI_LLM_CLASS`.
   - `config/pi/skills/deepseek/SKILL.md`: point "cheap off-plan work" at `--class mechanical`.
5. **H3 Escalation.** In `llm-failover.ts`… **no** — that file is frozen this wave. Instead:
   `/failover` is not yours; implement escalation as a proxy-side allowance: a request may
   carry `x-cc-proxy-class-escalate: 1` (set by the caller — document that the goal
   extension's evaluator or the human sets `PI_LLM_CLASS_ESCALATE=1` for one run) which
   lifts the class one tier (`mechanical→research→build→interactive`) for that request
   and logs `{"kind":"escalate", class, to, session}` via `append_route()`. Test it.
6. **Live check** on a second instance (`CC_PROXY_PORT=8790`, isolated `XDG_CACHE_HOME`,
   `CCTOKEN_FILE=$HOME/cctoken`): `curl 'localhost:8790/_route?class=build'` and
   `?class=mechanical` — paste `preferred` and reasons; one haiku `max_tokens:1` request
   with `x-cc-proxy-class: mechanical` served OK, and one fable-model request with class
   `build` (+`no_oi`) rejected with the class message (no quota spent).
7. **Report** `docs/handover/routing-H-task-classes-report.md`, including the P4
   measurement recipe: how to compute "share of delegate/loop tokens in opus/fable buckets"
   from `usage.json` `by_model` + the class events (sibling I builds the weekly report; give
   them the formula).

## Scope fence

- **You own:** `config/llm-proxy/classes.json`; in the proxy: classes loader,
  `class_eligible()`, the `?class=` branch of `route_payload()`/`/_route` handler (add a
  parameter; keep `?model=` code paths intact), the one-line filter calls in `pick()` and
  `rank_pool()`, header parsing for class/escalate in `_proxy()`; `anthropic-pool.ts` +
  its test; delegate.sh both copies; the two SKILL.md files; `tests/unit/test_proxy_task_classes.py`;
  your report.
- **Do NOT touch:** `pressure()`, `spread_choice()`, `LAST_PICK` internals, `deepseek_candidate()`,
  `fallback_target()`, the 503 branch's counter (sibling **E**); `llm-failover.ts`;
  `scripts/llm_usage.py`, `config/claude-code/env.sh`, waybar, observability tests (sibling **I**).
- Siblings in parallel: E (`feat/routing-e-no-starvation`), I (`feat/routing-i-hygiene`).

## Constraints

- `CLAUDE.md`; stdlib only; shellcheck; never log tokens; tests patch `CONTROL_DIR` etc.
  to temp dirs, never the real `~/.cache/cc-proxy`.
- Gates (by name): `python3 -m unittest tests.unit.test_proxy_task_classes tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider`; `node --test --experimental-strip-types tests/unit/test_anthropic_pool.mjs tests/unit/test_llm_failover.mjs`; `make test-unit`; `shellcheck` on touched .sh.
- Conventional commits (≤ 50 chars); `GIT_EDITOR=true`; parent owns merges.
- Scratch: `pi-scratch dir routing-h`. Never touch port 8788 or the live cache.

## Parent handshake (mandatory)

```
PARENT: task H <done|blocked>. branch feat/routing-h-task-classes @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-H-task-classes-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance — ≤ ~$15.
