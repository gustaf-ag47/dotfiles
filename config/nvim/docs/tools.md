# tools/

Workflow helpers for the nvim config itself. Currently:

- [`audit.sh`](#auditsh) — static analysis for common footguns

## `audit.sh`

```bash
bash $DOTFILES/config/nvim/tools/audit.sh
```

Run before each commit. Exits 0 when clean. Five sections, all of which
catch real bugs we hit during this config's evolution:

### 1) `vim.notify` at startup-risk locations

Scans `lua/core/*.lua` and `$NOTES/nvim-projects/*.lua` for `vim.notify`
calls that aren't wrapped in `vim.schedule(function() ... end)`.

**Why it matters**: those locations run during nvim's startup phase before
the UI is ready. A raw `vim.notify` lands in the cmdline area and triggers
"Press ENTER or type command to continue", blocking startup.

**Fixed footprint** by running this:
- `lua/core/modules.lua` × 3 (the M.safe_require error, the feature setup
  error, the language setup error)
- `lua/core/autocmds.lua` × 1 (the project-config load error)
- `$NOTES/nvim-projects/<php-project>.lua` × 1 (the "<php-project>: PHP 7.4" startup banner)
- `$NOTES/nvim-projects/<go-project>.lua` × 1 (the equivalent for the Go project)

### 2) Busy/lock flags without auto-reset

Scans for `local <flag> = true/false` declarations whose name matches
`in_progress|busy|locked|is_loading|pending`, and which don't have a
companion `_since` timestamp variable OR comments referring to `TTL`,
`stale_after`, or `self_heal`.

**Why it matters**: the "I marked something busy and forgot to unmark it"
pattern is universal and silent. The SSO watcher wedged for ~38 hours
because the `in_progress` flag stayed true after a manually-killed
terminal split.

**Fixed footprint**: `dbui_sso.lua` — added `in_progress_since`
timestamp + a self-heal check in `M.login()` that auto-resets if
`in_progress_since` is >10 min old.

### 3) lazy.nvim `cmd =` entries that ALSO appear in `nvim_create_user_command`

Scans each plugin spec for any string in its `cmd = {...}` array that is
also registered via `nvim_create_user_command()` in the same file's
`init()` callback.

**Why it matters**: lazy.nvim's stub-deletion-on-first-trigger pattern
silently wipes init-registered commands that happen to share a name with
a cmd-list entry. Symptom: `:DBUIReload` mysteriously stops working after
the first `:DBUI` invocation, no error trace.

**Fixed footprint**: `plugins/dadbod.lua` — `cmd = {}` now only lists
commands that genuinely require the plugin to be loaded (`DBUI`,
`DBUIToggle`, `DBUIAddConnection`, `DBUIFindBuffer`). All the
init-registered ones (`DBUIReload`, `DBUIHealth`, `DBUILogin`,
`DBUIAbortLogin`, `DBUIAutoReloadStatus`) are NOT listed and stay alive.

### 4) Top-level duplicate plugin specs across files

Scans every `'user/repo'` string across `lua/plugins/*.lua` +
`lua/lang/*.lua`. For each plugin appearing in more than one file, classifies
each occurrence:

- `DEP` — inside `dependencies = {...}` of another spec (safe)
- `OPT` — has `optional = true` nearby (lazy.nvim extension pattern, safe)
- `TOP` — top-level spec entry (dangerous if duplicated)

Flags only when 2+ TOP-level entries exist for the same plugin.

**Why it matters**: lazy.nvim merges duplicate specs, but the merge order
is unpredictable. We lost the canonical `init` of `vim-dadbod-ui` early
in this session because `lang/sql.lua` had its own (incomplete)
top-level spec for it. Took an hour to find.

**Fixed footprint**:
- `lang/sql.lua` — dropped the duplicate `vim-dadbod-ui` and
  `vim-dadbod-completion` top-level specs.
- `plugins/avante.lua` — dropped duplicate `render-markdown.nvim` top-level
  spec. The canonical one lives in `plugins/markdown-render.lua`, which
  now includes Avante in its `ft` list and `opts.file_types`.

### 5) Dead modules

Scans every `.lua` under `lua/` and checks whether each one is referenced
by a `require('X')` OR `require 'X'` (both syntaxes) anywhere in the tree.
Filters out modules that the dynamic loader in `core/modules.lua` picks up
(everything under `features/`, `lang/`, `plugins/`) and snippets (loaded
by luasnip via filename convention).

**Why it matters**: 496 lines of `features/sql_completion.lua` were dead
code for who-knows-how-long because the custom cmp source it registered
called the non-existent `vim.fn['db#cmd']` and silently returned 0 items
every time.

**Fixed footprint**: deleted `features/sql_completion.lua`.

## Exit codes

```
0     — all sections clean (commit safely)
N>0   — N issues flagged (review then commit, OR fix and re-run)
2     — script error (e.g. can't find nvim config root)
```

## Workflow recommendation

Add to your shell rc:

```bash
alias audit-nvim="bash $DOTFILES/config/nvim/tools/audit.sh"
```

Optionally wire as a git pre-commit hook:

```bash
mkdir -p $DOTFILES/.git/hooks
cat > $DOTFILES/.git/hooks/pre-commit <<'EOF'
#!/usr/bin/env bash
# Run nvim audit only if nvim config has staged changes
if git diff --cached --name-only | grep -q '^config/nvim/'; then
  bash "$(git rev-parse --show-toplevel)/config/nvim/tools/audit.sh" || {
    echo "✗ audit failed — fix issues or run 'git commit --no-verify'"
    exit 1
  }
fi
EOF
chmod +x $DOTFILES/.git/hooks/pre-commit
```

## Adding new checks

The script is bash + inlined python3 heredocs. Each section is independent;
follow the existing patterns. The python sections use the same standard
library; no extra dependencies.

Suggested next checks (not yet implemented):

- **Inconsistent notify wrappers**: detect mixed use of `vim.notify`,
  `nvim_err_writeln`, and `nvim_echo` for the same kind of message across
  the codebase. One wrapper, one convention.
- **`<leader>` mapping conflicts**: cross-file scan of `vim.keymap.set`
  calls to flag clashes within the same mode.
- **Missing `desc` on keymaps**: which-key shows the description; `nil` desc
  is a UX regression.
- **Missing health check coverage**: each `features/<name>.lua` should have
  a corresponding entry in `dbui_health.lua` (or its own `:checkhealth`
  hook).
