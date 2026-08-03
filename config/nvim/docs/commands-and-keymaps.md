# Commands & keymaps quick reference

Only the commands and keymaps **this config registers** (i.e., not the
ones the plugins ship with built-in). For built-in plugin commands see
their own docs.

## DBUI

| Command | Keymap | What it does | Source |
|---|---|---|---|
| `:DBUI` | `<leader>du` | Toggle drawer | plugin built-in |
| `:DBUIReload` | `<leader>dr` | Re-read connections.json explicitly (also re-init dadbod-ui state). | `plugins/dadbod.lua` init() |
| `:DBUIHealth` | `<leader>dh` | One-shot diagnostic: scope / SSO / tunnel / IAM token / autoreloader / cmp sources. Multi-line report persists to `:messages`. | `plugins/dadbod.lua` init() → `features/dbui_health.lua` |
| `:DBUILogin` | `<leader>dL` | AWS SSO login in a terminal split + auto-refresh IAM token + restart SSM tunnel + autoreloader rebinds buffers. No leaving nvim. | `plugins/dadbod.lua` init() → `features/dbui_sso.lua` |
| `:DBUIAbortLogin` | — | Reset stuck `in_progress` flag from a previous `:DBUILogin` that didn't clean up. | `plugins/dadbod.lua` init() → `features/dbui_sso.lua` |
| `:DBUIAutoReloadStatus` | — | Inspect the libuv fs_event watcher (paths, mtime per path, count). | `plugins/dadbod.lua` init() → `features/dbui_autoreload.lua` |
| `:DBUIScope <ws>[/<proj>]` | — | Force the active workspace/project scope without `cd`. Tab-completes known workspaces and projects. `:DBUIScope auto` re-runs cwd-based detection. | `features/dbui_project.lua` |
| `:DBUIAddConnection` | `<leader>da` | Prompt for a new connection. | plugin built-in |
| `:DBUIFindBuffer` | `<leader>df` | Jump to a query buffer from the drawer. | plugin built-in |

SQL buffer keymaps (registered on `FileType={sql,mysql,plsql}`):

| Mode | Keymap | What |
|---|---|---|
| n | `<leader>e` | Execute query under cursor (whole buffer) |
| v | `<leader>e` | Execute visual selection |
| n | `<leader>W` | Save query permanently to save_location |
| n | `<leader>be` | Edit bind parameters (`:varname` syntax) |

## Cmp / completion

These are global cmp behavior. See `lua/features/completion.lua` for full
list. Key ones to remember:

| Keymap | What |
|---|---|
| `<C-Space>` | Manually trigger completion menu |
| `<C-n>` / `<C-p>` (or `<Tab>` / `<S-Tab>`) | Next / previous item in popup |
| `<C-y>` | **Confirm whatever's highlighted** (most reliable; works even when nothing was Tab'd into) |
| `<CR>` | Confirm IF an item is explicitly selected (else just insert newline) |
| `<C-e>` | Abort popup |
| `<C-f>` / `<C-b>` | Scroll documentation pop-up |

Supermaven (inline AI ghost text — separate from cmp):

| Keymap | What |
|---|---|
| `<M-l>` | Accept full inline suggestion |
| `<M-w>` | Accept one word |
| `<C-]>` | Dismiss |

## Project-local config

| Mechanism | Where |
|---|---|
| `vim.opt.exrc = true` enables `.nvim.lua` per project | `lua/core/options.lua` |
| Project configs (private, not in dotfiles) | `$NOTES/nvim-projects/<project>.lua` |
| Project's `.nvim.lua` typically just documents that config lives elsewhere | each project root |
| Load happens on `LazyDone` autocmd | `lua/core/autocmds.lua` |
| `:trust` is required once per `.nvim.lua` | nvim built-in |

## Audit tooling

| Command | What |
|---|---|
| `bash $DOTFILES/config/nvim/tools/audit.sh` | Run all 5 static checks (~1s) |

See [`tools.md`](tools.md) for details on each check and how to add new ones.

## What's NOT in this list

- Plugin-shipped commands (`:Mason`, `:Lazy`, `:Telescope`, etc.) — see their own docs.
- DAP / debugger keymaps (`<leader>dc`, `<leader>db`, etc.) — see `lua/features/debugging.lua`.
- LSP defaults (`gd`, `gr`, `K`, etc.) — see `lua/features/lsp.lua`.
- Telescope mappings (`<leader>f*`, `<leader>s*`) — see `lua/plugins/telescope.lua`.
- Window/buffer/quit/save mappings (`<leader>ww`, `<leader>qq`, etc.) — see `lua/core/keymaps.lua`.
