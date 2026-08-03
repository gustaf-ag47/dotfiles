-- Session Management with persistence.nvim
-- Automatically saves and restores sessions per directory

return {
  'folke/persistence.nvim',
  event = 'BufReadPre',
  opts = {
    dir = vim.fn.stdpath 'state' .. '/sessions/',
    need = 1, -- Minimum number of buffers to save
    branch = true, -- Include branch name in session file
  },
  keys = {
    {
      '<leader>qs',
      function()
        require('persistence').load()
      end,
      desc = 'Restore session',
    },
    {
      '<leader>qS',
      function()
        require('persistence').select()
      end,
      desc = 'Select session',
    },
    {
      '<leader>ql',
      function()
        require('persistence').load { last = true }
      end,
      desc = 'Restore last session',
    },
    {
      '<leader>qd',
      function()
        require('persistence').stop()
      end,
      desc = 'Stop saving session',
    },
  },
}
