# Neovim memory leak: 13 GB RSS after 9 days (2026-09-26)

Brief: [`docs/handover/nvim-memory-leak.md`](handover/nvim-memory-leak.md).
Raw captures from the dead process: `~/scratch/nvim-leak/`. Reproduction logs:
`$(pi-scratch dir nvim-leak)` (`typing.log`, `stall.log`, `idle.log`, `fix*.log`).

## TL;DR

- **Most likely cause: supermaven-nvim's unbounded stdin write queue.**
  On every edit the plugin `uv.write()`s the *whole buffer* (JSON) to `sm-agent`'s
  stdin and ignores the result. If `sm-agent` stops reading stdin, libuv keeps every
  pending payload in nvim's heap with no cap. Reproduced: growth is linear in
  (buffer size × edits) and only stops when the agent drains or is killed.
- **Fix:** `config/nvim/lua/plugins/supermaven.lua` caps the queue at 16 MB. Past the
  cap it SIGKILLs the agent, closes the pipes (frees the queue) and starts a fresh
  agent. It also skips non-file buffers and buffers over 1 MB.
- **Guard:** `config/nvim/lua/features/memguard.lua` checks RSS every 60 s. Above
  2 GB it warns via `vim.notify` and writes a line to `~/.local/state/nvim/nvim.log`.
  `:MemGuard` prints the current numbers.
- **Confidence: medium.** The mechanism is proven and it is the only unbounded
  structure found. I could not prove that the agent actually stalled in the dead
  session, because that process was unresponsive and has since been killed.

## Evidence from the dead process (PID 1643855)

| Fact | Reading |
|---|---|
| RSS 12.5 GiB, all `Private_Dirty` anon (smaps_rollup) | Heap growth inside nvim, not file mappings or a child process |
| Only child: `sm-agent stdio`, RSS **2.3 MB** | A working agent in the repro uses 20–25 MB. 2.3 MB means its pages had gone cold and been swapped out, which fits an agent that stopped reading stdin. Suggestive, not proof. |
| Two other nvim servers with the same config, both up 8d20h, **no sm-agent child** (never entered insert mode) | 110 MB RSS each. Everything else in the config ran for as long without leaking. This is the natural control group. |
| Unresponsive to `--remote-expr` | Fits a multi-GB LuaJIT heap (queued Lua strings) under swap: GC sweeps and page-ins stall the loop |
| `Threads: 1` | **Not meaningful.** nvim 0.12 / libuv 1.52 spins its `libuv-worker` threads up and down; the repro showed both 1 and 5 |
| ~51 M voluntary context switches in 9.8 days (~60/s) | Explained by supermaven's 25 ms timer (40 wakeups/s), which it starts at load and never stops. This is CPU churn and does not leak |
| `lsp.log`, `nvim.log`: nothing for PID 1643854/5 | No LSP attached (the file has no filetype); no errors were logged |
| `alphaspellol` (`~/alphaspellol`, 1.7 KB, `file` says "Dyalog APL transfer", which is a false magic match) | Markdown-ish notes with no extension, so `filetype=` is empty and nothing filetype-specific attached. mtime = open time, so the buffer was probably never saved after opening. The session's other buffers are unknown. |

## Reproduction

Harness: a private tmux server (`tmux -L nvimleak`), `nvim --listen <scratch>/nvim.sock`
on a copy of `alphaspellol`, cwd `~`, full config. Samples came from `/proc/<pid>/status`
plus `collectgarbage("count")` and
`binary_handler.stdin:get_write_queue_size()` over RPC.

| Scenario | Duration | RSS | Write queue |
|---|---|---|---|
| Typing ~1 word/s, healthy agent | 4 min | 118 → 114 MB, flat | 0 |
| Idle, healthy agent | 6 min | 117.8 → 118.9 MB, flat (one 1 MB step) | 0 |
| `:terminal` spewing output (no supermaven traffic) | 2.5 min | 118 → 166 MB, then **plateau** (scrollback cap) | n/a |
| Typing, **agent SIGSTOPped** | 5 min | 114.4 → 117.8 MB and rising | 0 → **1.71 MB** for 264 state updates on a 4–6 KB buffer (~6.5 KB per update) |
| …then `SIGCONT` the agent | 5 s | stays | **drains to 0**; Lua heap drops back after GC |
| 1000 × `vim.notify` via nvim-notify | — | +3 MB | n/a (see secondary findings) |

The stalled-agent growth rate scales with buffer size. At ~6.5 KB per update, 13 GB is
about 2 M updates. Editing a 100 KB–1 MB buffer in the same session would get there in
13k–130k keystrokes or completion polls. Upstream's own size cap is 10 MB per buffer.

Fix verification: I set `g:supermaven_max_write_queue_mb=0.3`, SIGSTOPped the agent
and typed. The queue climbed to 258 KB. On the next write it reset to 0, the old agent
was SIGKILLed and reaped (no zombie; an earlier version that closed the handle left
one), a new `sm-agent` started and drained, and a `supermaven` WARN notification was
shown. Memguard verification: with `g:memguard_threshold_mb=50`, the tick after 60 s
wrote
`WRN 2026-09-26T18:49:36 memguard.820207 rss=98MB lua=22MB bufs=1 supermaven[…]` to
`nvim.log` and raised the notification.

## Ruled out or deprioritised

- **Idle growth.** Flat over 6 min. The only idle churn is supermaven's 25 ms timer,
  about 5 MB/min of Lua garbage, which is collected.
- **Supermaven with a healthy agent.** Flat. `state_map` is purged to 50 entries.
  `changed_document_list` is keyed by path and reset each query.
- **Terminal buffers.** They grow only up to `scrollback`, and supermaven's
  `TextChanged` does not fire for them. They are now excluded anyway.
- **LSP servers.** None were attached and none were children.
- **codecompanion.** Lazy-loaded on `VeryLazy`, but it spawns nothing until a chat is
  opened. There was no curl child or chat buffer evidence.
- **Undo** (`undolevels=10000`, `undofile`). This is bounded per buffer. It would need
  enormous edits to reach GBs, and it would not explain the agent-only correlation.
- **luasnip.log / nio.log fds.** Both files are 296 B and 0 B. Holding a handle open
  does not use memory.

## Residual risk

- The root cause is inferred from mechanism plus correlation. Memguard now logs a
  snapshot that includes supermaven's `stdin_queue`, so next time the log will say
  whether the queue was the problem.
- supermaven-nvim is pinned at `07d20fc` (Oct 2024), which is effectively unmaintained
  upstream. Its 25 ms forever-timer and its restart path, which leaks the old pipes
  when the agent crashes (`check_process` never closes them), are still there.
  Removing supermaven altogether is the zero-risk option.
- Memguard only warns. It does not kill anything.

## Secondary findings (not fixed, out of the minimal fix)

- `features/dbui_sso.lua` starts a watcher in **every** nvim, because dadbod's
  `config` runs at startup. Once the AWS SSO token expires it fires a WARN
  notification **every minute, forever** (seen in the repro: "AWS SSO expired
  2026-09-25…"). nvim-notify's history is unbounded, so that adds about 13k entries
  over 9 days, or tens of MB at most. It is annoying rather than the 13 GB. Suggested
  follow-up: warn once per expiry, or only when a DBUI buffer is open.
- `neotest.log` is 34 MB (Jun 29) and is never rotated.
