# Brief I — Hygiene & guard-rails: test isolation, drop shell probing, alerts, weekly report

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-i-hygiene` (worktree off
`feat/pi-wait-for-quota-reset`). **Parent:** the tmux window recorded by delegate.sh.
**Date:** 2026-09-28.

## Context

Read first: `docs/research/routing-10-of-10-plan.md` §0 (the four metrics P1–P4 and the
guard-rails) and §3 Phase 5 (I1–I3; I4 is a separate repo, not yours). Then
`routing-D-observability-report.md` (schema of `forecast`, `routing.recent`, `routing.log`,
`_samples`), and `scripts/llm_usage.py`.

Observed problems this brief fixes:

1. **Test isolation leak.** After `make test-unit` on the merged tree, the *live*
   `~/.cache/cc-proxy/routing.log` contained events with test fingerprints
   (`3e9e905643d4 → 7a5443b66367`). At least one test calls a code path that writes via
   the real `ROUTING_LOG`/`CONTROL_DIR`/`USAGE_STATE_FILE`. Also `routing.recent` on the
   live proxy now shows those fake rows.
2. **Shell startup spends quota.** `config/claude-code/env.sh` runs `claude-token-refresh`
   on every new shell: haiku probes to pick a token the proxy now picks better. The only
   remaining consumer of `CLAUDE_CODE_OAUTH_TOKEN` in the shell env is the *opt-out*
   path (`PI_ANTHROPIC_POOL=off`) and Claude Code CLI itself when not pointed at the proxy.
3. **No alerts, no weekly numbers.** D's forecasts exist but nothing tells the operator
   before an exhaust, and nobody computes P1–P4.

## Your job

1. **I0 Test isolation (do this first, it protects everyone).** Find every test that can
   touch the real cache: grep `CONTROL_DIR`, `ROUTING_LOG`, `USAGE_STATE_FILE`, `SAMPLES`,
   `append_route`, `save_usage_state` in `tests/unit/*.py` and the proxy; make a shared
   fixture (`tests/unit/proxy_fixture.py` with a `mixin`/context manager) that redirects
   **all** of them to a `TemporaryDirectory` and restores after, and use it from every
   proxy test class (`test_claude_token_proxy.py`, `test_proxy_cross_provider.py`,
   `test_proxy_deepseek_backstop.py`, `test_proxy_observability.py`). Add a guard test that
   runs the whole proxy suite in a subprocess with `XDG_CACHE_HOME` pointed at a temp dir
   and asserts the real `~/.cache/cc-proxy` mtimes did not change. Then clean the live
   `routing.log` of rows whose `from_fp`/`to_fp` are not in the live pool (write a tiny
   `bin/claude-token-proxy-logclean` or do it once by hand and say so in the report — the
   live proxy on 8788 may keep running; do **not** restart it).
2. **I1 Remove `claude-token-refresh` from shell startup.** In `config/claude-code/env.sh`
   drop the `_cc_apply_refresh` path; keep only the cached-file / raw-cctoken fallbacks
   (they are file reads, no network) so `CLAUDE_CODE_OAUTH_TOKEN` is still exported for
   the opt-out path and for the `claude` CLI. Keep `ANTHROPIC_BASE_URL` export to the proxy
   when the service is active (check how it is done today and keep it). Update the header
   comment. Check `bin/claude-token-refresh` callers (`rg claude-token-refresh`) and leave
   the binary in place (other scripts may call it explicitly); note them in the report.
   Verify a fresh `zsh -ic 'echo $CLAUDE_CODE_TOKEN_SOURCE'` still works and makes no
   network call (`strace -f -e trace=network` or just time it: < 50 ms).
3. **I2 Alerts.** `bin/waybar-claude-usage` renders the bar module from `/_usage`. Add
   states: `critical` when `routing.forecast.first_exhaust` is < 2 h away or
   `routing.starved` (sibling E is adding it — read it defensively, missing = 0) > 0;
   `warning` when any 7d/7d_oi window `forecast == "waste"` with projected waste > 30 %.
   Waybar `class` field + CSS in `config/gui/Wayland/waybar/style.css` (there is already a
   claude-usage style; extend, keep Tokyo Night colours). Additionally a
   `bin/llm-alert` script suitable for a systemd user timer (`config/systemd/user/llm-alert.{service,timer}`,
   every 10 min) that sends **one** `notify-send` per condition transition (state file in
   `$XDG_CACHE_HOME/llm-alert/`), never repeating. Do not enable the timer; document
   `systemctl --user enable --now llm-alert.timer`.
4. **I3 Weekly report.** `llm-usage --week` prints the four §0 metrics for the last 7 days
   from `/_usage` + `routing.log` + `usage.json`:
   - P1 `starved_requests` (from `routing.starved`/`kind=starved` events; 0 if absent),
   - P2 `weekly_waste_percent` per 7d/7d_oi window and for Codex (D's forecast at the
     latest sample before each reset in the period; if a window has not reset in the
     period, the current projection, marked `~`),
   - P3 `avoidable_5h_stalls` (5h quota-429 cooldown events on account X while another
     account's 5h reading at that time was ≥ 30 % left — derive from `routing.log`
     `reason=cooldown` moves + `_samples`; document the approximation),
   - P4 share of tokens in opus/fable buckets for non-interactive classes (sibling H will
     provide `kind=class`/escalate events and the formula in their report; if their branch
     is not merged yet, implement against the documented event shape and mark `n/a` when
     no events exist),
   - cache-hit ratio = `cache_read_input_tokens / (input_tokens + cache_read + cache_creation)`
     from the token counters.
   Also `--week --json`. Append a "## Log" entry to `docs/research/routing-10-of-10-plan.md`
   with the first real numbers. Unit tests with synthetic logs/samples in `tests/unit/test_llm_usage.py`.
5. **Report** `docs/handover/routing-I-hygiene-report.md`.

## Scope fence

- **You own:** `tests/unit/proxy_fixture.py` + the isolation edits in the four proxy test
  files (fixture wiring only — do not change what they assert), `config/claude-code/env.sh`,
  `bin/waybar-claude-usage`, `bin/llm-alert`, `config/systemd/user/llm-alert.*`, waybar
  `style.css` claude-usage block, `scripts/llm_usage.py` (`--week` and helpers — keep
  existing rendering intact), `tests/unit/test_llm_usage.py`, the plan doc's Log section,
  your report.
- **Do NOT touch:** `bin/claude-token-proxy` at all this wave (siblings E and H are both in
  it) — if you need a field the proxy lacks, compute it client-side from `routing.log`/
  `usage.json` and list the wish in the report; `config/pi/extensions/*`; `delegate.sh`;
  `classes.json`/`routes.json`.
- Siblings in parallel: E (`feat/routing-e-no-starvation`), H (`feat/routing-h-task-classes`).

## Constraints

- `CLAUDE.md`; stdlib only in Python; bash: `#!/bin/bash`, `set -euo pipefail`, shellcheck;
  never print token values.
- Gates (by name): `make test-unit`; `shellcheck bin/waybar-claude-usage bin/llm-alert`;
  `zsh -n config/claude-code/env.sh`; the new isolation guard test by name.
- Conventional commits (≤ 50 chars); `GIT_EDITOR=true`; parent owns merges.
- Scratch: `pi-scratch dir routing-i`. Never restart port 8788.

## Parent handshake (mandatory)

```
PARENT: task I <done|blocked>. branch feat/routing-i-hygiene @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-I-hygiene-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance — ≤ ~$12.
