# Handover: root-cause the Neovim memory leak (13 GB RSS after 9 days)

## Context

On 2026-09-26 the workstation was swap-thrashing (23 GB swap full, load 24 on 16 cores).
The single largest process was a Neovim server:

```
PID 1643855  nvim --embed alphaspellol   RSS 12.7 GB  VmData 13.7 GB  VmSwap 600 MB
parent 1643854  nvim alphaspellol  (TUI client)   uptime 9d 16h   cwd /home/gud1
```

Facts captured before it was killed (all in `/home/gud1/scratch/nvim-leak/`):

- `status.txt` — `/proc/<pid>/status`: **Threads: 1**, VmData 13.7 GB. So the growth is in
  nvim's own heap (Lua state / buffers / undo / extmarks), not in a child LSP server.
- `pstree.txt` — the only child was `supermaven` `sm-agent stdio` (PID 1647403, RSS 2 MB,
  19 threads). No other LSP servers were children at the time of capture.
- `logfds.txt` — nvim held open `~/.local/state/nvim/luasnip.log` and `nio.log`.
- `buffers.txt` — RPC `nvim_list_bufs` **timed out**; the server was unresponsive to
  `--remote-expr` (every call died with SIGTERM from `timeout 20`). It could not be introspected.
- `loaded.txt` — partial `package.loaded` list (53 bytes captured before timeout).
- Log files in `~/.local/state/nvim/`: `lsp.log` 2.9 MB, `mason.log` 602 KB, `neotest.log` 34 MB
  (Jun 29), `nvim.log` 86 KB. Check `lsp.log` / `nvim.log` for a repeating error around the
  Sep 17–25 window.
- The edited file was `alphaspellol` (no extension) opened from `~`. Find what it is
  (`ls -la ~/alphaspellol*`, `file`), its filetype detection, and which plugins attach to it.

Neovim: `NVIM v0.12.3`. Plugin manager: lazy.nvim, 103 plugins under `~/.local/share/nvim/lazy`.

Config lives in this repo: `config/nvim/` (symlinked to `~/.config/nvim`). Read
`config/nvim/MODULAR_APPROACH.md` and `config/nvim/init.lua` first, then
`config/nvim/lua/{core,plugins,features,lang}`.

## Job

1. Identify the most likely leaking component(s). Prime suspects, in order:
   - `config/nvim/lua/plugins/supermaven.lua` — supermaven-nvim keeps per-buffer document
     state and has a known history of unbounded growth on long sessions / large or
     unusual filetypes.
   - `config/nvim/lua/plugins/codecompanion.lua` (also references supermaven) — chat
     buffers / history accumulation.
   - Anything with a timer (`vim.loop.new_timer`, `vim.fn.timer_start`, `vim.defer_fn` in a
     loop) or an autocmd on `CursorMoved`/`TextChanged`/`CursorHold` that appends to a table
     without clearing. `rg -n 'new_timer|timer_start|TextChanged|CursorMoved|CursorHold' config/nvim`.
   - Undo/`undolevels`, `updatetime`, `swapfile`, `shada` settings in `core/`.
   - Treesitter / extmark heavy plugins (indent guides, rainbow, illuminate, gitsigns).
   - LuaSnip / nvim-nio log handles that were still open.
2. **Reproduce**, don't guess. Start `nvim` on the same file (or a copy), leave it idle
   and/or simulate editing, and sample RSS every 60 s for 15–30 min:
   ```bash
   pid=$(pgrep -f 'nvim --embed' | head -1); while sleep 60; do echo "$(date +%T) $(awk '/VmRSS/{print $2}' /proc/$pid/status) kB"; done
   ```
   Inside nvim, sample `collectgarbage("count")` (Lua heap KB) alongside RSS so you can tell
   Lua-side growth from C-side (buffer/undo/extmark) growth:
   `:lua print(collectgarbage("count"))` and `:lua collectgarbage() ` then re-check.
   Use `config/nvim/minimal.lua` (`nvim -u config/nvim/minimal.lua`) and lazy.nvim's
   bisection (`:Lazy` → disable halves) to isolate the plugin.
3. Write a fix in this repo: disable/replace/configure the culprit (e.g. an idle-detach,
   buffer-size cap, filetype exclusion, or GC tuning `collectgarbage("setpause", …)`) —
   whatever the evidence supports. Keep the fix minimal and commented with a link to
   this doc.
4. Add a cheap guard so this can't silently recur: e.g. an autocmd/timer that logs a
   warning (`vim.notify` + `nvim.log`) when RSS exceeds a threshold (2 GB) — implement in
   `config/nvim/lua/features/` following the existing module pattern.
5. Record findings in `docs/nvim-memory-leak.md` (in this repo): evidence, the reproduction,
   what was ruled out, root cause, fix, and the residual risk. Commit on a branch
   `fix/nvim-memory-leak` and push; do **not** merge — the operator will review.

## Scope fence

- You own: `config/nvim/**`, `docs/nvim-memory-leak.md`, this brief.
- Do not touch anything else in the dotfiles repo (shell, pi, tmux, hypr configs).
- Do not kill or restart any other user's processes. There are ~50 other `pi` sessions and a
  Firefox on this box — leave them alone. Only kill nvim instances **you** started.
- Do not run `docker`, do not touch `/var/lib/docker`.

## Constraints

- Scratch and logs go under `$(pi-scratch dir nvim-leak)`, never `/tmp` (tmpfs, small).
- Use `GIT_EDITOR=true` for any git command that might open an editor.
- The machine was just recovered from swap exhaustion. If your reproduction nvim exceeds
  4 GB RSS, kill it and record the number — that is already proof.
- Report, don't fix, anything outside nvim you find surprising.

## Cost guidance

Budget: ~2 hours of wall time. If after bisecting you cannot reproduce growth, write up
what you tried in `docs/nvim-memory-leak.md`, add the RSS guard from step 4 anyway, and
stop. Do not loop indefinitely on speculation.

## Parent

Spawned by the pi session doing the system-health cleanup on 2026-09-26. Leave a summary
in the mailbox when done (delegate.sh's watcher handles the nudge).
