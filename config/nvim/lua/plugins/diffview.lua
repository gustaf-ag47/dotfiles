-- Git diff viewer and merge conflict resolution
-- Provides 3-way merge, file history, and branch comparison

return {
  'sindrets/diffview.nvim',
  cmd = { 'DiffviewOpen', 'DiffviewFileHistory', 'DiffviewClose' },
  keys = {
    { '<leader>Gd', '<cmd>DiffviewOpen<cr>', desc = 'Diff view open' },
    { '<leader>Gh', '<cmd>DiffviewFileHistory<cr>', desc = 'File history (all)' },
    { '<leader>GH', '<cmd>DiffviewFileHistory %<cr>', desc = 'File history (current)' },
    -- Git history for visual selection (PhpStorm: "Show History for Selection")
    {
      '<leader>GH',
      function()
        local l1, l2 = vim.fn.line "'<", vim.fn.line "'>"
        vim.cmd(string.format('DiffviewFileHistory %% -L%d,%d', l1, l2))
      end,
      mode = 'v',
      desc = 'Git history for selection',
    },
    { '<leader>Gc', '<cmd>DiffviewClose<cr>', desc = 'Close diff view' },
  },
  opts = {
    enhanced_diff_hl = true,
    view = {
      default = {
        layout = 'diff2_horizontal',
      },
      merge_tool = {
        layout = 'diff3_horizontal',
        disable_diagnostics = true,
      },
    },
    file_panel = {
      listing_style = 'tree',
      tree_options = {
        flatten_dirs = true,
        folder_statuses = 'only_folded',
      },
      win_config = {
        position = 'left',
        width = 35,
      },
    },
  },
}
