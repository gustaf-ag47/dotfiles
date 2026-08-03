-- Overseer: async task runner for background phpstan, test watches, etc.
-- Feeds results into quickfix / trouble for project-wide problems view

return {
  {
    'stevearc/overseer.nvim',
    cmd = { 'OverseerRun', 'OverseerToggle', 'OverseerInfo' },
    keys = {
      { '<leader>or', '<cmd>OverseerRun<cr>',    desc = 'Tasks: Run' },
      { '<leader>ot', '<cmd>OverseerToggle<cr>', desc = 'Tasks: Toggle panel' },
      { '<leader>oi', '<cmd>OverseerInfo<cr>',   desc = 'Tasks: Info' },
    },
    opts = {
      task_list = {
        direction = 'bottom',
        min_height = 10,
        max_height = 20,
      },
    },
  },
}
