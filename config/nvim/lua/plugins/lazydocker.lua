-- Lazydocker integration - Docker TUI in a floating window
-- Requires lazydocker to be installed on the system

return {
  'mgierada/lazydocker.nvim',
  dependencies = { 'akinsho/toggleterm.nvim' },
  cmd = 'Lazydocker',
  keys = {
    { '<leader>GD', '<cmd>Lazydocker<cr>', desc = 'LazyDocker' },
  },
  opts = {},
}
