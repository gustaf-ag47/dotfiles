-- Minimal isolated config for testing and bug reproduction
-- Usage: nvim -u config/nvim/minimal.lua [file]
--
-- Plugins install to config/nvim/.repro/ (gitignored, not your real data dir).
-- First run downloads lazy.nvim and syncs plugins — subsequent runs are fast.
--
-- To test a specific language, uncomment the relevant section below.

local root = vim.fn.fnamemodify(vim.fn.resolve(vim.fn.expand '<sfile>'), ':h')
local repro = root .. '/.repro'

-- Redirect all XDG dirs so this never touches your real Neovim state
for _, name in ipairs { 'config', 'data', 'state', 'cache' } do
  vim.env[('XDG_%s_HOME'):format(name:upper())] = repro .. '/' .. name
end

-- Bootstrap lazy.nvim
local lazypath = repro .. '/data/lazy/lazy.nvim'
if not vim.uv.fs_stat(lazypath) then
  vim.fn.system {
    'git',
    'clone',
    '--filter=blob:none',
    '--single-branch',
    'https://github.com/folke/lazy.nvim.git',
    lazypath,
  }
end
vim.opt.rtp:prepend(lazypath)

vim.g.mapleader = ' '
vim.g.maplocalleader = ' '

require('lazy').setup({
  -- Always-on: syntax + LSP plumbing
  {
    'nvim-treesitter/nvim-treesitter',
    build = ':TSUpdate',
    -- nvim-treesitter v1.0+ (Neovim 0.12+): no setup() call needed,
    -- highlight is enabled by default. Install parsers on demand via :TSInstall.
  },
  { 'neovim/nvim-lspconfig' },
  { 'williamboman/mason.nvim', config = true },
  { 'williamboman/mason-lspconfig.nvim' },

  -- Uncomment to test Go workflow:
  -- { 'ray-x/go.nvim', dependencies = { 'ray-x/guihua.lua' }, ft = { 'go', 'gomod' }, config = true },
  -- { 'leoluz/nvim-dap-go', ft = 'go', dependencies = { 'mfussenegger/nvim-dap' }, config = true },

  -- Uncomment to test completion:
  -- { 'hrsh7th/nvim-cmp', dependencies = { 'hrsh7th/cmp-nvim-lsp', 'hrsh7th/cmp-buffer' } },

  -- Uncomment to test a specific plugin from your config:
  -- { dir = root },  -- loads your full config as the plugin under test
}, {
  root = repro .. '/data/lazy',
  lockfile = repro .. '/lazy-lock.json',
  -- XDG overrides above already prevent ~/.config/nvim from loading
})
