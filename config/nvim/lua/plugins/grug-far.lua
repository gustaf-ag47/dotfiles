-- Project-wide search and replace

return {
  'MagicDuck/grug-far.nvim',
  cmd = 'GrugFar',
  keys = {
    { '<leader>S', '<cmd>GrugFar<cr>', desc = 'Search & Replace (project)' },
    {
      '<leader>S',
      function()
        require('grug-far').with_visual_selection()
      end,
      mode = 'v',
      desc = 'Search & Replace (selection)',
    },
  },
  opts = {
    headerMaxWidth = 80,
  },
}
