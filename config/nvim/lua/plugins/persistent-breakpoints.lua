-- Persist breakpoints across sessions

return {
  'Weissle/persistent-breakpoints.nvim',
  event = 'BufReadPost',
  opts = {
    save_dir = vim.fn.stdpath('data') .. '/breakpoints',
    load_breakpoints_event = { 'BufReadPost' },
    perf_record = false,
  },
  keys = {
    {
      '<leader>dB',
      function()
        require('persistent-breakpoints.api').toggle_breakpoint()
      end,
      desc = 'Toggle breakpoint (persistent)',
    },
    {
      '<leader>dX',
      function()
        require('persistent-breakpoints.api').clear_all_breakpoints()
      end,
      desc = 'Clear all breakpoints (persistent)',
    },
    {
      '<leader>dC',
      function()
        require('persistent-breakpoints.api').set_conditional_breakpoint()
      end,
      desc = 'Conditional breakpoint (persistent)',
    },
  },
}
