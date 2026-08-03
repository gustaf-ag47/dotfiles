# Neovim config documentation

In-tree docs for the modules, tools, and conventions this config uses.

## Table of contents

| Doc | Covers |
|---|---|
| [`tools.md`](tools.md) | The `tools/` directory and the `audit.sh` static analyser |
| [`commands-and-keymaps.md`](commands-and-keymaps.md) | Quick reference for the user commands and `<leader>` mappings this config registers |

Design notes:
- [`../MODULAR_APPROACH.md`](../MODULAR_APPROACH.md)

Historical planning/handover docs (the PHP onboarding handover, the implementation
plan, and the June 2026 refactor session log) now live in the Obsidian vault at
`$NOTES/dotfiles/`. They're research notes rather than config, so they're kept
out of git.

## Conventions

- **Module location rules**:
  - `lua/plugins/*.lua` — lazy.nvim plugin spec ONLY (no business logic). One file per plugin (or per closely-coupled group).
  - `lua/lang/*.lua` — per-language wiring (LSP, treesitter, formatter, linters). Each file `return`s a list of plugin specs.
  - `lua/features/*.lua` — cross-cutting Lua modules that other modules `require`. Pure code, no plugin specs.
  - `lua/core/*.lua` — bootstrap (options, keymaps, lazy.nvim setup, autocmds, module loader).

- **`vim.notify` at startup**: anything that may run during nvim's startup phase (lua/core/*, `dofile`'d project configs in `$NOTES/nvim-projects/`) must wrap `vim.notify` in `vim.schedule(function() ... end)`. Otherwise the notification lands in the cmdline area before the UI is ready and forces a "Press ENTER" prompt. The audit script catches violations.

- **Long-running flags** (`in_progress`, `busy`, `locked`, etc.) must have a `_since` timestamp companion AND a self-heal path that triggers after a TTL. Otherwise a missed reset wedges the feature forever. The audit script catches violations.

- **Lazy.nvim `cmd =` list**: only list commands that REQUIRE the plugin to be loaded. Commands you register yourself in `init()` must NOT appear in `cmd =` because lazy.nvim's stub-deletion-on-first-trigger will wipe them. The audit script catches violations.

- **Project-local configs** belong in `$NOTES/nvim-projects/<project>.lua`. Each project's `.nvim.lua` is a tiny stub that documents where the real config lives.

## Where the moving parts live

```
.config/nvim/                            # this dir
  init.lua                               # entry — requires 'core'
  lazy-lock.json                         # pinned plugin versions
  lua/
    core/                                # bootstrap
      init.lua                           #   chain of requires
      options.lua                        #   vim.opt.* globals (incl. exrc = true)
      keymaps.lua                        #   global <leader> bindings
      autocmds.lua                       #   global autocmds (LazyDone loads project config)
      lazy.lua                           #   lazy.nvim bootstrap
      modules.lua                        #   dynamic feature/lang loader
    features/                            # cross-cutting modules
      dbui_autoreload.lua                #   libuv fs_event watcher for connections.json
      dbui_dml_guard.lua                 #   prod-DML safety
      dbui_health.lua                    #   :DBUIHealth probe
      dbui_sso.lua                       #   :DBUILogin + watcher
      dbui_project.lua                   #   workspace/project scope detection
      lsp.lua, completion.lua, debugging.lua
    lang/                                # per-language modules
      sql.lua                            #   includes cmp entry_filter for vim-dadbod-completion
      php.lua, python.lua, go.lua, rust.lua, twig.lua, typescript.lua, dotenv.lua, vimfony.lua
    plugins/                             # plugin specs
      dadbod.lua                         #   wires up all dbui_* modules
      markdown-render.lua                #   canonical render-markdown.nvim spec
      avante.lua, anki.lua, telescope.lua, oil.lua, neo-tree.lua, ...
    snippets/                            # luasnip snippets
  tools/
    audit.sh                             # static analyser (run before commits)
  docs/                                  # you are here
```

## How the workflow loops

```
$ cd ~/some/project
  └─ DirChanged fires
     └─ features/dbui_project.lua detects (workspace, project) from cwd
        └─ sets vim.g.db_ui_save_location to the project's dir
        └─ inherits workspace-level entries into vim.g.dbs
        └─ resets dadbod-ui's cache and re-renders drawer
        └─ re-arms features/dbui_autoreload.lua watchers on the new files

$ :DBUI
  Drawer shows only DBs in scope for this cwd.

$ <leader>e on a SQL buffer
  ├─ vim-dadbod's :DB fires User DBExecutePre
  └─ features/dbui_dml_guard.lua runs
     ├─ if connection name contains "prod"
     │  └─ parse buffer SQL for DML/DDL keywords
     │     └─ if found: error() to abort
     └─ else: pass through

$ <leader>dh   →  :DBUIHealth
  Reports: scope / SSO / tunnel / IAM token / autoreloader / cmp source list.

$ <leader>dL   →  :DBUILogin
  Terminal split runs `aws sso login --use-device-code`. On success:
  ├─ runs prod-db-token.sh (token rotation)
  ├─ runs systemctl --user restart prod-db-tunnel (kicks the tunnel)
  └─ dbui_autoreload picks up new connections.json, patches b:db on open
     query buffers, drawer ✓ marks refresh.
```

## How to add a new module

1. Decide which directory: `features/` (cross-cutting), `plugins/` (lazy spec), `lang/` (per-language), `core/` (bootstrap).
2. Copy the closest existing module as a template. Replace its header comment.
3. If it has a busy flag, add a `_since` timestamp + self-heal.
4. If it shows messages during startup, wrap `vim.notify` in `vim.schedule`.
5. Run `bash tools/audit.sh` and confirm 0 issues.
6. If it adds e2e behaviour, add probes to `$NOTES/db_ui/scripts/regression.sh` (or wherever its regression suite lives).

## Source of truth for the lower-level docs

The DBUI subsystem has a separate, deeper documentation set in `$NOTES/db_ui/docs/` (10 markdown files covering each subsystem, the pi/openai/anthropic auth comparison, IAM token flow, tmux testing recipes, etc.). When in doubt, look there. The docs/ here cover what's in *this* git repo only.
