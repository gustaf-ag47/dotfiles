-- Inline git conflict resolution with highlights

return {
  'akinsho/git-conflict.nvim',
  version = '*',
  event = 'BufReadPre',
  build = function()
    vim.fn.system { 'python3', vim.fn.expand '$DOTFILES' .. '/bin/nvim-patch-plugins', 'git-conflict' }
  end,
  opts = {
    default_mappings = true,
    default_commands = true,
    disable_diagnostics = false,
    list_opener = 'copen',
    highlights = {
      incoming = 'DiffAdd',
      current = 'DiffText',
    },
  },
}
