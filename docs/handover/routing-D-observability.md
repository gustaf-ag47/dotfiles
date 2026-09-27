# Brief D — Routing observability: switch log, wasted-quota forecast, llm-usage view

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-d-observability` (worktree,
off `feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh (see the launch prompt).
**Date:** 2026-09-27.

## Context

The operator's goal for the LLM routing stack (`bin/claude-token-proxy` +
`config/pi/extensions/llm-failover.ts` + `scripts/llm_usage.py` / `bin/llm-usage`) is
"never run out of tokens": every perishable quota window (Anthropic 5h/7d/7d-fable per
account, Codex 7d) should be spent before it resets, and no window should hit 100 %
while others still have headroom. Today nobody can *see* whether that is happening:

- There is no record of which provider/account served what over time, only per-token
  lifetime counters (`usage.json`: requests, tokens, `by_model`).
- `llm-usage` shows "% left" and "resets in", but not the burn rate or whether the
  remaining headroom will be used or wasted.
- Cross-provider switches by the extension are only visible as one-off notify lines in
  the pi TUI.

Parent commit `0072ad0` (read its message) made `/_usage` readings expiry-aware and
persisted quota in `usage.json` under `tokens[fp].quota`. Siblings A and B are changing
the *policy* (cross-provider EDF preference; per-session affinity + 5h-aware
selection). Your job is the *instrumentation* that lets the operator judge whether those
policies work, and it must not depend on their unmerged code.

## Your job

1. **Burn-rate ledger in the proxy.** Keep a compact time series per token and per
   bucket (5h / 7d / 7d_oi): sample `(ts, utilization)` whenever a header observation
   arrives (`update_from_headers()` is sibling B's territory only for *selection*; you
   may add one hook call there — coordinate by keeping it a single line
   `record_sample(tok)` and put your code elsewhere). Bound it (e.g. ≤ 200 samples per
   series, drop when a window resets) and persist it under a new `samples` key in
   `usage.json` (extend `save_usage_state()`/`restore_usage_state()` minimally; both are
   yours for this key only).
2. **Forecast in `/_usage`.** For each token window and for the Codex window (from
   `PROVIDER_STATE["openai-codex"]`), compute from the ledger: `burn_per_hour`
   (utilization slope over the last ≥ 2 samples spanning ≥ 15 min, else null),
   `projected_at_reset` (utilization if the slope continues to `reset_at`, clamped), and
   `forecast`: one of `"waste"` (projected < 0.9 at reset — headroom will expire unused),
   `"exhaust"` (projected ≥ 1.0 before reset — say when: `exhaust_at`), `"on_track"`,
   `"unknown"`. Expose per token as `tokens[fp].forecast[window]` and for Codex under
   `providers["openai-codex"].forecast`. Also expose a pool-level summary
   `routing.forecast`: `{"weekly_waste_percent": …, "first_exhaust": {"fp", "window",
   "at"} | null}`. Pure functions, unit-tested with synthetic samples.
3. **Switch/route log.** Append one JSON line per *account change between consecutive
   requests of the same bucket* and per DeepSeek fallback episode to
   `$XDG_CACHE_HOME/cc-proxy/routing.log` (`ts, bucket, from_fp, to_fp, reason`) —
   reason from what the proxy knows (cooldown / pressure / forced / sticky-band). Rotate
   at 1 MB (keep one `.1`). Expose the last 20 entries as `routing.recent` in `/_usage`.
   The pi extension's provider switches: add a **tiny** `POST /_event` endpoint (loopback
   only, JSON `{kind, from, to, reason}`) that appends to the same log; do **not** edit
   `llm-failover.ts` (sibling A owns it) — write the one-call snippet A should add in
   your report so the parent can hand it over.
4. **`llm-usage` view.** In `scripts/llm_usage.py` (yours), render per window a short
   suffix after "resets in …": `· burn 3.1%/h · on track` / `· will waste ~40%` /
   `· exhausts in 2h 10m`, colour-coded; and a `forecast` line under `routing` with the
   pool summary and the last 3 `routing.recent` entries (`14:02 base ccb…→a5d… cooldown`).
   Keep the existing tests in `tests/unit/test_llm_usage.py` green and add yours there.
   `llm-usage --json` must carry the new fields untouched.
5. **Tests.** Python proxy tests in a **new file** `tests/unit/test_proxy_observability.py`
   (sibling B owns `test_claude_token_proxy.py`). Cover: ledger bounds and reset drop,
   slope/forecast arithmetic (waste / exhaust / on_track / unknown), log rotation,
   `/_event` rejects non-loopback-shaped bodies and non-JSON, `/_usage` fields present.
6. **Live check** on a second instance (`CC_PROXY_PORT=8790` from your worktree, separate
   `XDG_CACHE_HOME` under your scratch dir so the live service's `usage.json` is not
   touched): show `curl -s localhost:8790/_usage | jq '.routing.forecast, .routing.recent'`
   and the `llm-usage` output with `PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8790`.
7. **Report** at `docs/handover/routing-D-observability-report.md`.

Done = gates green, live output in the report, report pushed, parent handshake sent.

## Scope fence

- **You own:** new functions for ledger/forecast/log/`/_event` in `bin/claude-token-proxy`,
  the `/_usage` payload builder (`usage_payload`/`_status`/`_usage` handlers) for the
  **new** fields, the `samples` key in `save_usage_state()`/`restore_usage_state()`;
  `scripts/llm_usage.py`; `tests/unit/test_llm_usage.py`;
  `tests/unit/test_proxy_observability.py`; your report.
- **Do NOT touch:** `pick()`, `rank_pool()`, `pressure()`, `bucket_util()`, `LAST_PICK`
  (sibling **B**) — except the single `record_sample(tok)` line you may add in
  `update_from_headers()`; `codex_candidate()`, `anthropic_candidate()`,
  `route_payload()`, `/_route`, `config/pi/extensions/*`, `tests/unit/test_llm_failover.mjs`
  (sibling **A**); `fallback_target()`, `deepseek_*`, `_deepseek_fallback()`,
  `routes.json` (sibling **C**) — you may *read* `FALLBACK` to log episodes;
  `tests/unit/test_claude_token_proxy.py`.
- Never restart or point the live `claude-token-proxy.service` (port 8788) at your file.
- Siblings in parallel: A (`feat/routing-a-cross-provider`), B (`feat/routing-b-affinity-5h`),
  C (`feat/routing-c-deepseek-backstop`).

## Constraints

- Read `CLAUDE.md` fully. Python stdlib only. Never log token values (fingerprints only).
- Gates (report **by name** with summary lines):
  ```bash
  python3 -m unittest tests.unit.test_claude_token_proxy tests.unit.test_proxy_observability tests.unit.test_llm_usage
  make test-unit
  ```
- Conventional commits; `GIT_EDITOR=true` for rebase/merge continuation. **Parent owns
  merges** — push your branch only.
- Scratch: `scratch="$(pi-scratch dir routing-d)"`, never `/tmp`.

## Where to record findings

`docs/handover/routing-D-observability-report.md`: field schema (so A/B/C and the
parent can rely on it), the `llm-failover.ts` snippet for sibling A, gates by name with
output, live output, anything out of scope.

## When blocked

Record it, leave the branch reviewable, push, handshake as blocked.

## Parent handshake (mandatory — do not just go idle)

When done **or** blocked, after pushing, print exactly one final message in this shape and
then wait for the parent's reply (stay in the session; do not exit):

```
PARENT: task D <done|blocked>. branch feat/routing-d-observability @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-D-observability-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance

Target ≤ ~$12. If exceeded without a green gate, write up and handshake as blocked.
