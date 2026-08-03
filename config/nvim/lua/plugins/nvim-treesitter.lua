return {
  'nvim-treesitter/nvim-treesitter',
  lazy = false,
  build = ':TSUpdate',
  -- main branch (Nvim 0.12+): setup() only accepts { install_dir }.
  -- highlight/indent are Neovim built-ins; no configs.setup() needed.
  -- Run :TSUpdate to refresh parsers after updates.
}
