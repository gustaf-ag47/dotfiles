-- Incremental LSP rename with live preview
-- Shows all changes in real-time before applying

return {
  'smjonas/inc-rename.nvim',
  cmd = 'IncRename',
  event = 'LspAttach',
  config = function()
    require('inc_rename').setup {
      -- Input buffer type: 'dressing', 'noice', or nil (cmdline)
      input_buffer_type = nil,
      -- Whether to show message after rename
      show_message = true,
      -- Don't save rename string in cmdline history
      save_in_cmdline_history = false,
      -- Preview highlighting
      preview_empty_name = false,
      -- Post-hook after rename completes
      post_hook = nil,
    }
  end,
  keys = {
    {
      '<leader>cr',
      function()
        return ':IncRename ' .. vim.fn.expand '<cword>'
      end,
      expr = true,
      desc = 'Rename symbol (preview)',
    },
  },
}
