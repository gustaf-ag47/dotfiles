-- Canonical render-markdown spec. plugins/avante.lua used to declare a SECOND
-- top-level spec for the same plugin with `file_types = { 'markdown', 'Avante' }`
-- and `ft = { 'markdown', 'Avante' }`. lazy.nvim merged them but the merge
-- ordering was unpredictable. Now consolidated here.
return {
  'MeanderingProgrammer/render-markdown.nvim',
  dependencies = { 'nvim-treesitter/nvim-treesitter', 'nvim-tree/nvim-web-devicons' },
  ft = { 'markdown', 'Avante' },
  ---@module 'render-markdown'
  ---@type render.md.UserConfig
  opts = {
    file_types = { 'markdown', 'Avante' },
  },
}
