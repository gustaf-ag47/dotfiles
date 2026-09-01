# CPU usage check — skrubben (2026-09-01)

Read-only investigation. Nothing was killed, reniced, or reconfigured.
Sampling window: ~12:03–12:10 local, host up 26 d 2 h.

## TL;DR

**CPU is not the constraint.** The box idles at 85–89 % across 16 threads; the
agent fleet is nearly free when idle. The two real findings are elsewhere:

1. **Syncthing is in a permanent rescan/hash loop** — 143 h of CPU (23 % of a
   core, continuously, for 26 days) and **~75 MB/s of sustained `read()`**
   (475 TB lifetime `rchar`). This is the single biggest recurring cost on the
   machine and it produces no visible symptom.
2. **Memory/swap is the actual pressure point** — 26.4 GiB of 32 GiB swap in
   use with 22 GiB RAM free. That is stale swap from an earlier burst, but the
   headroom for "more agents" is RAM, not CPU.

Plus process hygiene rot: **28 zombies**, **8 stopped processes** (including a
wedged `tmux-safe-save` → tmux-resurrect chain), and **73 running containers**.

## 1. Capacity vs load

| Metric | Value |
|---|---|
| CPU | Intel i9-9900K, 8 cores / **16 threads**, max 5.0 GHz, governor `powersave` |
| Load avg (12:03) | 2.66 / 12.14 / 23.31 |
| Load avg (12:09) | 1.92 / 5.41 / 16.81 |
| `%Cpu(s)` idle | 83–89 % across the sample |
| Tasks | 1 248 total, 2 running, **28 zombie**, **8 stopped** |
| RAM | 62 GiB total, 30–32 GiB used, 22 GiB free, 13–14 GiB cache |
| Swap | 32 GiB total, **26.4 GiB used**, 6.3 GiB free |
| Temps | package 65 °C (high 86, crit 100) — **no thermal throttling** |

The falling 15-min load (23 → 17) against a 1-min load of ~2 means we caught the
tail of a burst (a build/agent run), not steady state. Steady state is ~1.5–3.0
load on 16 threads, i.e. **~10–17 % utilisation**. `vmstat` shows `wa` at 0–2 %,
`si/so` essentially zero during the window — no live swap thrashing.

## 2. Top consumers, attributed

Measured properly as a **delta of cumulative CPU time over a 180 s window**
(`ps -eo pid,times` twice), not an instantaneous `top` snapshot. Percentages are
of one core (1600 % = whole machine).

| Live % (180 s) | Process | Group |
|---:|---|---|
| 57.2 | `pi` (pid 3491367 — an agent mid-run) | agents |
| **28.3** | `syncthing serve` | **system/sync** |
| **23.3** | `promtail` | **observability** |
| 8.9 | `dockerd` | docker |
| 6.1 | `pi` (pid 2477952 — sibling sub-agent) | agents |
| 5.6 + 1.7 + 0.6 | 3× `containerd-shim-runc-v2` | docker |
| 4.4 | `tmux server` | desktop |
| 3.9 | `Hyprland` | desktop |
| 2.2 | `alacritty` | desktop |
| 2.2 | `pi` (pid 2932313 — this sub-agent) | agents |
| 1.7 | opensearch `java`, `waybar`, `firefox` | mixed |
| ~5 | rest (beam.smp ×2, selkies, Sonarr, containerd, authentik, …) | services |

**Group totals over the window:** agents ≈ 67 % of one core across **48
pi/claude/node processes**; docker infra ≈ 18 %; desktop ≈ 12 %; everything else
≈ 60 %, of which syncthing + promtail alone are 52 %.

**Lifetime CPU (26 days uptime) tells a different, more important story:**

| Cumulative CPU | Process |
|---:|---|
| **143.1 h** | syncthing (22.8 % of a core, sustained) |
| **127.6 h** | promtail (20.3 % of a core, sustained) |
| 75.6 h | dockerd |
| 17.3 h | firefox |
| 16.6 h | Hyprland |
| 15.2 h | tmux server |
| 24.5 h | **entire pi/claude/node agent family combined** |

The agent fleet has burned less CPU in 26 days than syncthing burns in five.

## 3. Steady-state vs burst — are idle pi TUIs actually idle?

**Yes, genuinely idle.** Of 30 `pi` processes, only three registered any CPU at
all over the 180 s window: the two actively-inferring agents (57.2 %, 6.1 %) and
this sub-agent (2.2 %). **Every other pi process measured 0.00 %** — not
low-but-polling, literally zero ticks in three minutes. Their lifetime averages
(0.9–3.6 %) come entirely from their own past active phases.

Conclusion: an idle pi TUI is free. Scaling the fleet costs CPU only in
proportion to how many agents are *simultaneously mid-inference*, and inference
is largely network-bound anyway — a busy agent peaks around 0.5–0.6 of a core.

## 4. The watchers

Two live `watch-child.sh` instances (the `pgrep -fc` count of 6 includes the
grep and its subshells):

```
pid 2572682  age 1233s  cputime 0s   (sibling sub-agent, CI work)
pid 2933967  age  284s  cputime 0s   (Dotfiles:sub-cpu-usage-check-skrubben)
```

**Zero seconds of CPU each, rounded from 20 minutes and 5 minutes of wall time.**
A 20 s `tmux list-panes` poll is unmeasurable. The watchers do not matter and
would not matter at 10× the count.

## 5. Surprises

### 5.1 Syncthing's permanent scan loop (the headline)
- Folder `sync` = `/home/gud1/sync`, `rescanIntervalS=3600`, watcher enabled,
  trashcan versioning (30-day cleanout, hourly cleanup), 215 threads.
- `.stignore` already excludes `node_modules`, `.git`, `.venv`, `vendor`,
  `__pycache__` — yet it still reads **747 MB in 10 s (~75 MB/s `rchar`)**, of
  which ~12 MB/s actually hits disk. Lifetime `rchar` is **475 TB**.
- Index DB is **2.9 GB** (`~/.local/state/syncthing/index-v2`).
- It runs at `NI 11`, so it yields under contention — which is exactly why
  nobody has noticed. It is a constant tax on I/O bandwidth and page cache,
  paid invisibly.

### 5.2 Promtail: 127 h of CPU to tail logs
`homelab-promtail` scrapes the log output of **73 running containers**. 20 % of
a core, permanently, second-biggest consumer on the box. Nobody sized this.

### 5.3 28 zombies, never reaped
Concentrated under a handful of long-lived dev servers that don't `wait()`:
`air -c .air-worktree.toml` (pid 4141556, **11 zombies**), two `next-server`
instances (pids 13184 / 10607, ~10 between them), `beam.smp`, `mysqld`, a
defunct `tmux: client`. Harmless today; a slow PID-table leak.

### 5.4 A wedged tmux-resurrect save chain (8 stopped processes)
```
939006  Tl  fzf (ftsess session-killer)
947654  T   tmux-safe-save
948179  T   tmux-resurrect/scripts/save.sh
948269  T   tmux_spinner.sh "Saving..."
951581  T   save.sh (second instance)
951625  T   -zsh
```
An `ftsess` invocation was SIGTSTP'd mid-save; `tmux-safe-save` and **two**
overlapping `save.sh` runs are frozen with a zombie tmux client. Also stopped:
`ralph/scheduler.sh` (2797854) and `ralph/job-runner.sh` (3396147). This is
precisely the class of silent degradation the operator is worried about —
**tmux session saves may not have completed since this froze.**

### 5.5 Swap
26.4 GiB used with 22 GiB RAM free = stale swap, not active pressure (`si/so`
≈ 0). Largest swapped-out residents: `java` 1.3 GB, `vector` 506 MB, `syncthing`
450 MB, `immich` 421 MB, `firefox` 415 MB, `thunderbird` 382 MB, `mysqld` 348 MB.

### 5.6 Governor
`powersave` on a desktop i9-9900K. Fine given the machine is 85 % idle, but it
does mean burst latency (agent inference, builds) is worse than it needs to be.

## 6. Verdict

**CPU is not a constraint for adding more agents.** 16 threads at ~85 % idle,
no thermal throttling, and idle agents measurably cost nothing. You could double
the fleet on CPU grounds. The binding resource is **RAM** (30 GiB used + 26 GiB
swap already committed) and, second, **I/O bandwidth**.

**The single change that would help most: fix syncthing.** It is 23 % of a core
and 75 MB/s of sustained reads, 24/7, for a folder that is mostly source code.
Concretely, in order of effort:
1. Raise `rescanIntervalS` from 3600 → e.g. 21600 and rely on the fs watcher.
2. Extend `.stignore` to cover the rest of the build/cache churn the agents
   generate (`**/target`, `**/dist`, `**/.next`, `**/.turbo`, `**/build`,
   worktree dirs under `/tmp/wt-*` if any are inside `~/sync`, `**/.pytest_cache`).
3. Verify no folder is stuck out-of-sync and re-hashing forever — a 2.9 GB index
   for one folder is large enough to be worth a look via the syncthing UI.

**Second-best change:** trim promtail's scrape targets to the containers whose
logs are actually consulted, rather than all 73.

**Cheap hygiene wins:** un-wedge or clear the stopped `tmux-safe-save`/`save.sh`
chain (5.4) and confirm resurrect saves are current; restart the `air` and
`next-server` dev servers to clear the zombie backlog.

---
*Delegated sub-agent run `20260901T100334Z-2932007`.*
