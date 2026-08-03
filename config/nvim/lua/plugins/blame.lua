return {
  'FabijanZulj/blame.nvim',
  cmd = 'BlameToggle',
  keys = {
    { '<leader>Gb', '<cmd>BlameToggle<cr>', desc = 'Blame toggle panel' },
  },
  opts = {
    date_format = '%Y-%m-%d',
    merge_consecutive = false,
    max_summary_width = 30,
    mappings = {
      commit_info = 'i',
      stack_push = '<TAB>',
      stack_pop = '<BS>',
      show_commit = '<CR>',
      close = { '<esc>', 'q' },
    },
  },
}
