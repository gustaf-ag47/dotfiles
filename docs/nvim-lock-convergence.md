# Neovim lock convergence (2026-10-03)

**Decision:** keep the laptop's lock update with two compatibility corrections and one branch correction. `config/nvim/lazy-lock.json` has 101 entries; 54 differ from the previous committed lock. The laptop's original update changed 56 entries. Do not replay its original Treesitter or Telescope branch changes over this result.

- **Treesitter:** restore `nvim-treesitter` to legacy `master` at `cf12346a3414fa1b06af75c79faebe7f76df080a` (previous lock). The laptop's `main` checkout at `4916d6592ede8c07973490d9322f187e07dfefac` does not provide `nvim-treesitter.configs`, `ts_utils`, or `locals`; the installed `go.nvim` checkout (`a3455f48cff718a86275115523dcc735535a13aa`) imports these in `go/ts/textobjects.lua`, `go/snips.lua`, `go/ts/nodes.lua`, etc. `config/nvim/lua/lang/go.lua` sets `textobjects = true`. `go.nvim` must be migrated before adopting Treesitter `main`. README at the main checkout also says highlighting is **not** enabled automatically; fixed misleading comments in the full and minimal config. The legacy module loads in isolation with the pinned Go checkout. Keep parser builds matched to the selected Treesitter revision (`:TSUpdate` on installation).
- **Telescope:** the laptop changed branch `0.1.x` to `master` without changing commit `a0bbec21143c7bc5f8bb02e0005fa0b982edc026`. That commit is at `origin/0.1.x`, not `origin/master`; restore branch `0.1.x`.
- **Refactoring:** laptop pin `6784b54587e6d8a6b9ea199318512170ffb9e418` belongs to `origin/1.0`, not `origin/master`. Change branch metadata to `1.0`, preserving the updated commit.

## Verification

- Neovim installed: **0.12.5**. Checked all 101 lock commits against read-only laptop plugin checkout `~/.local/share/nvim/lazy`: all 101 exist and are ancestors of their lock branch's `origin/<branch>` remote-tracking ref after corrections. This is **local-ref evidence**, not a fresh remote fetch.
- Isolated headless startup: copied config and all plugin checkout directories into `~/.cache/dotfiles-converge/nvim-smoke`, checked out legacy Treesitter in that copy only, redirected all XDG locations to that directory, then ran the copied full `init.lua` with a 45-second timeout. Exit **0**; lazy reported **45 loaded / 101 registered** and `require('nvim-treesitter.configs')` succeeded. Log is at `~/.cache/dotfiles-converge/nvim-smoke/startup.log`. The original laptop checkout and running editors were not altered.
- JSON schema/commit length and branch ancestry check: **pass**, 101/101. `luac -p` across `config/nvim/lua` and `config/nvim/minimal.lua`: **pass**. `git diff --check -- config/nvim`: **pass**.

## Limits / follow-up

- The full-config smoke attempted automatic Mason and Kulala package installs in the **isolated** cache (the config enables them). Neovim canceled pending installations on exit; do not interpret this as verification of Mason-managed servers, parsers, Go textobjects, or all 101 plugin behaviors. No blanket plugin update was run. One successful startup is only a basic load test.
- The CI-gated StyLua and luacheck binaries are not installed locally; syntax checking is not a substitute. CI must run `.github/workflows/nvim.yml` (StyLua, luacheck, syntax and headless load), and a future Go-specific functional test should cover `go.nvim` textobjects before Treesitter main migration.
- The standalone `config/nvim/minimal.lua` is an **unlocked** reproduction config and may install the latest Treesitter main; it is not a substitute for testing this lock. Its comment was corrected to avoid implying highlighting is automatic.
