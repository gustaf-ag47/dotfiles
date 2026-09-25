# Brief — What is this workstation's CPU actually doing?

**Deliverable:** a written diagnosis in your tmux window + committed at `docs/handover/2026-09-01_cpu-usage-check.md` on your branch. **Read-only investigation — kill nothing, renice nothing.**

## Why

This machine (skrubben) is running a large agent fleet: ~10 interactive pi/claude sessions in tmux, their watch-child.sh watchers, Docker stacks, and whatever else has accreted. Nobody has checked what that costs. The operator wants to know the CPU picture before it becomes the next silent problem — this week's theme has been mechanisms that degrade without anyone noticing (a tmpfs at 78%, a disk at 83%, 1,334 git stashes).

## Job

1. **Current load vs capacity**: core count, load averages, and whether the machine is CPU-bound right now or merely busy. `top -bn1`, `uptime`, `nproc`.
2. **Top consumers, attributed**: which processes, grouped into (a) agent fleet (pi, claude, node), (b) Docker/containers, (c) browsers/desktop, (d) system. A flat `top` dump is not attribution.
3. **Steady-state vs burst**: sample over a few minutes (e.g. `pidstat 5 6` or repeated top) — an agent mid-inference looks different from idle TUIs. Are idle pi TUIs actually idle, or polling?
4. **The watchers**: `watch-child.sh` instances poll tmux every 20s — count them and measure whether they matter.
5. **Anything surprising**: runaway processes, forgotten containers, thermal throttling (`sensors` if present), swap pressure on the host.
6. **Verdict**: is CPU a constraint for adding more agents, and what single change would help most if so.
