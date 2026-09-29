# Brief F — P2 "no waste": reset-aware scheduler, end-of-window sweep, Codex parity

**Agent:** delegated pi sub-agent. **Branch:** `feat/routing-f-no-waste` (worktree off
`feat/pi-wait-for-quota-reset` **after wave 1 (E, H, I) is merged** — check
`git log --oneline | head` shows `merge … e/h/i` commits before starting).
**Parent:** the tmux window recorded by delegate.sh. **Date:** 2026-09-28 (wave 2).

## Context

Read first: `docs/research/routing-10-of-10-plan.md` §0 P2, §3 Phase 2 (F1–F3; **F4 is not
yours** — it needs two weeks of data). Then the reports for A (proactive EDF, `preferred`),
D (forecast fields: `burn_per_hour`, `projected_at_reset`, `forecast`, `exhaust_at`,
`weekly_waste_percent`), E (`llm-wait`), I (`llm-usage --week`).

P2: no 7d/7d_oi/Codex window resets with headroom demand could have used (< 5 %). Two
causes remain after A: (1) demand is bursty and human-shaped — quota resets at 02:00/06:00/
10:00 on various days and sits idle until someone starts work; (2) inside the last hours
of a window the ×1.5 sticky band and the 0.98 threshold deliberately leave headroom.

## Your job

1. **F1 `bin/llm-schedule` + user timer.** A tiny queue: `llm-schedule add [--class build]
   [--prefer anthropic|codex|any] [--not-before ISO] -- <command…>` writes a job file
   (`$XDG_DATA_HOME/llm-schedule/queue/<ts>-<slug>.job`, JSON: cmd, cwd, env subset, class,
   prefer, created). `llm-schedule list|rm|run-due`. `config/systemd/user/llm-schedule.{service,timer}`
   runs `run-due` every 5 min: for each job, ask `/_route?class=` (H) and `/_usage` forecast
   (D) and start the job when **either** (a) a window matching `--prefer` has just reset
   (utilization < 10 % and < 30 min since `reset_at` — detect via D's samples), or (b) the
   preferred window's forecast is `waste` with projected waste ≥ 20 %, or (c)
   `--not-before` passed and `any.routable`. Jobs run detached (`systemd-run --user
   --unit llm-job-<slug>` if available, else `setsid nohup`) with `PI_LLM_CLASS` set,
   logging to `$XDG_STATE_HOME/llm-schedule/<slug>.log`; the job file moves to `done/`
   with the start reason. `delegate.sh --when reset|waste|now` (both copies, minimal hunk)
   enqueues instead of spawning when not `now`. Unit tests against fake `/_usage`/`/_route`
   servers (pattern: `tests/unit/test_pi_wait_for_reset.py`).
2. **F2 End-of-window sweep (proxy).** When an account's window (`7d` or `7d_oi`, per the
   request's bucket) is < `CC_PROXY_SWEEP_HOURS` (default 12) from reset **and** D's forecast
   for that window is `waste`, multiply its `pressure()` by `CC_PROXY_SWEEP_BOOST` (default
   2.0) for both `pick()` and `rank_pool()` (one helper `sweep_factor(t, key, now)` used in
   `pressure()` so parity holds automatically). Also lift the `< ROTATE_THRESHOLD`
   preference for that account to 0.995 during the sweep. Never boost an account whose 5h
   window is above the threshold (the sweep must not create a P3 stall). Expose
   `sweep: true` on the ranking rows and log `reason=sweep` moves via `append_route()`.
   Tests: boosted account wins; 5h-limited account is not boosted; preview/picker parity.
3. **F3 Codex on the same footing.** A's `codex_candidate()` pressure uses the *worst* window
   only. Make it `min(pressure_7d, pressure_5h)` when a 5h (`secondary_window` or an
   `additional_rate_limits` 5h) is present, and apply the same sweep boost to Codex when
   D's Codex forecast says `waste` (D samples Codex now). `preferred` in `/_route` must be
   computed with the boosted values. Unit tests in `tests/unit/test_proxy_cross_provider.py`
   (you may add a class there; do not edit existing tests' assertions).
4. **Live check** on a second instance with a copy of the live `usage.json` (isolated
   `XDG_CACHE_HOME`): show a ranking row with `sweep: true` if any window qualifies today,
   otherwise fake it by setting `CC_PROXY_SWEEP_HOURS=200` and show the boost; run
   `llm-schedule add --prefer any -- true` then `run-due` and show the job move to `done/`.
5. **Report** `docs/handover/routing-F-no-waste-report.md`.

## Scope fence

- **You own:** `bin/llm-schedule`, `config/systemd/user/llm-schedule.*`,
  `tests/unit/test_llm_schedule.py`; in the proxy: `sweep_factor()`, the boost hook inside
  `pressure()`, the threshold lift in `pick()`/`rank_pool()` (one line each), the `sweep`
  field on ranking rows, `codex_candidate()` pressure; delegate.sh `--when` hunk (both
  copies); your report.
- **Do NOT touch:** `spread_choice()`, affinity/`LAST_PICK`, the 5h-move logic, burst ramp,
  `llm-usage --capacity` (sibling **G**); `classes.json`/class filtering (done by H);
  `llm-failover.ts`.
- Sibling in parallel: G (`feat/routing-g-no-5h-stalls`).

## Constraints — as briefs A–E: `CLAUDE.md`, stdlib only, shellcheck, tests isolated via
`tests/unit/proxy_fixture.py` (from I), never touch port 8788 or the live cache.
Gates (by name): `python3 -m unittest tests.unit.test_llm_schedule tests.unit.test_claude_token_proxy tests.unit.test_proxy_cross_provider`; `make test-unit`; `shellcheck` on touched .sh.
Conventional commits (≤ 50 chars); `GIT_EDITOR=true`; parent owns merges. Scratch `pi-scratch dir routing-f`.

## Parent handshake (mandatory)

```
PARENT: task F <done|blocked>. branch feat/routing-f-no-waste @ <sha>.
gates: <name: pass/fail …>. report: docs/handover/routing-F-no-waste-report.md.
Awaiting review — reply with further instructions or "retire".
```

## Cost guidance — ≤ ~$15.
