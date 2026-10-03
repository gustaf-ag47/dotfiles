# Takeover report: Neovim RSS watchdog

## Investigation and resolution

- Inspected `0662dd5`: it changed only the supermaven plugin, added `features/memguard.lua`, wired it in `core/modules.lua`, and added the investigation and handover documents.
- Kept the RSS watchdog, its feature-loader wiring, and `docs/nvim-memory-leak.md`. The loader's `load_features()` requires each listed module and `setup_modules()` invokes its `setup()` after `LazyDone`; `features/debugging.lua` follows the same pattern. Removed the watchdog's supermaven-specific snapshot fields now that the plugin is absent.
- Dropped the queue cap and all supermaven plugin changes: master commit `672ee94` deleted `config/nvim/lua/plugins/supermaven.lua` entirely to eliminate the unbounded queue. Updated the investigation document to distinguish historical queue-cap experiments from the current removal.
- Kept master's `docs/handover/nvim-memory-leak.md` unchanged: `git diff master 0662dd5 -- docs/handover/nvim-memory-leak.md` produced no differences. The cherry-pick had only one modify/delete conflict (supermaven), resolved by keeping master's deletion.

## Verification

From this worktree:

```sh
XDG_CONFIG_HOME="$PWD/config" nvim --headless "+lua local ok,m = pcall(require,'features.memguard'); print('memguard require:', ok)" "+lua vim.defer_fn(function() print('MemGuard cmd:', vim.fn.exists(':MemGuard')) vim.cmd('qa!') end, 3000)" 2>&1
# raw output (Neovim did not emit a newline between prints):
memguard require: trueMemGuard cmd: 2
# exit=0

nvim --headless "+luafile $PWD/config/nvim/lua/features/memguard.lua" +qa 2>&1
# raw output: (empty)
# exit=0
```

## PR

https://github.com/gustaf-ag47/dotfiles/pull/20 — open against master; do not merge automatically.

## Out of scope

The original investigation notes a repeating expired AWS SSO warning from `features/dbui_sso.lua` and an unrotated 34 MB `neotest.log`. Neither is addressed here.
