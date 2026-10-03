return {
  'nvim-treesitter/nvim-treesitter',
  lazy = false,
  branch = 'master',
  version = false,
  build = ':TSUpdate',
  -- Stay on the legacy master branch: go.nvim uses nvim-treesitter.configs,
  -- ts_utils and locals, which are absent from the new main branch.
  -- Run :TSUpdate to refresh parsers after updates.
}
