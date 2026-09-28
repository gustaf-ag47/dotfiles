# Routing I hygiene — partial handover

Branch `feat/routing-i-hygiene`. This work is **blocked/incomplete**; do not merge as complete.

## Completed
- `config/claude-code/env.sh`: removed `claude-token-refresh` invocation; retained private cached/raw token file fallback and existing active-proxy URL behavior. `claude-token-refresh` remains for explicit callers; `rg` found installer references and documentation, no other startup call sites.
- Added Waybar forecast/starvation warning/critical class decisions, `bin/llm-alert`, and user service/timer. Timer is not enabled. Enable with `systemctl --user enable --now llm-alert.timer`.
- Existing proxy suite (93 tests) passed before isolation changes (none have yet been wired).

## I0 test isolation
- Added a run-level mixin covering `CONTROL_DIR`, `ROUTING_LOG`, `USAGE_STATE_FILE`, and `SAMPLES` (run-level to protect legacy test classes overriding `setUp`).
- Added `tests.unit.test_proxy_isolation`, which runs all four proxy suites in a subprocess with temporary `XDG_CACHE_HOME` and checks real-cache mtimes.
- Removed fake-fingerprint switch rows from live `routing.log`, retaining only non-fingerprint provider-switch records. Pool fingerprints were obtained from live usage state. No restart performed.
- Guard presently fails while the running service changes `usage.json` during the 9-second subprocess (mtime and size changed); the service was not stopped/restarted. Repeated run confirms unrelated live write. This is an environmental race, not evidence of a test write; guard needs a stable window or service coordination.

## I3 weekly report
Implemented `llm-usage --week [--json]` and a synthetic fixture test. Report computes current forecast waste by observed 7d/7d_oi window (and Codex weekly window), recent starved events, conservative cooldown events with explicit headroom metadata, class-event P4 or n/a, and token cache-hit ratio. It does not reconstruct reset-time historical forecast from sample series yet; these are current projections, not measured reset outcomes.

First live command: `bin/llm-usage --week --json`:

```json
{"period_days":7,"P1_starved_requests":49,"P2_weekly_waste_percent":{"anthropic:7d":"~64.0%","anthropic:7d_oi":"~59.0%","codex:primary_window":"~0.0%"},"P2_note":"~ denotes current forecast projection; reset-time historical forecasts are unavailable from this telemetry shape.","P3_avoidable_5h_stalls":0,"P3_note":"Approximation: cooldown move events are matched to the latest prior 5h sample within 10 minutes; samples do not prove account eligibility.","P4_opus_fable_token_share_percent":"n/a","cache_hit_percent":96.5}
```
P1 counts currently visible recent events plus JSONL events in the seven-day range, de-duplicated by exact event JSON; the live log includes concurrent traffic and the count changes as events arrive, so this is not a durable weekly accumulator.

## Not completed / risks
- `make test-unit`, full gates, and isolation guard-green status remain outstanding; current guard races the active proxy service's periodic usage persistence. No proxy restart was performed.
- Sourced the changed helper in an isolated zsh with `strace -f -e trace=network`; source was `/home/gud1/cctoken` and no Internet IPv4/IPv6 connect was attempted. A normal `zsh -ic` here still loads the user's installed dotfiles checkout at `/mnt/my_encrypted_nvme/sync/src/dotfiles`, not this worktree, and that older installed helper probes tokens; its trace exposed the probe (not this changed file). Fresh worktree shell/helper behavior is network-free.
- P3 is conservative and likely undercounts because the proxy event schema does not currently embed another account's simultaneous 5h headroom. P4 is n/a until `kind=class` usage events exist.

## Follow-up required
Implement shared per-test proxy state redirection covering CONTROL_DIR, ROUTING_LOG, USAGE_STATE_FILE and SAMPLES, then run the required subprocess mtime guard before touching live logs. Implement weekly reporting against fixture-driven synthetic `_usage`, usage-state, and routing logs, and explicitly report n/a when no class events exist. Do not restart port 8788.
