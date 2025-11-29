-- Trouble.nvim - Pretty diagnostics, references, quickfix lists
-- Better interface for viewing errors, warnings, and search results

return {
  'folke/trouble.nvim',
  dependencies = { 'nvim-tree/nvim-web-devicons' },
  cmd = { 'Trouble', 'TroubleToggle' },
  opts = {
    position = 'bottom',
    height = 12,
    icons = true,
    mode = 'workspace_diagnostics',
    fold_open = '',
    fold_closed = '',
    group = true,
    padding = true,
    action_keys = {
      close = 'q',
      cancel = '<esc>',
      refresh = 'r',
      jump = { '<cr>', '<tab>' },
      open_split = { '<c-x>' },
      open_vsplit = { '<c-v>' },
      open_tab = { '<c-t>' },
      jump_close = { 'o' },
      toggle_mode = 'm',
      toggle_preview = 'P',
      hover = 'K',
      preview = 'p',
      close_folds = { 'zM', 'zm' },
      open_folds = { 'zR', 'zr' },
      toggle_fold = { 'zA', 'za' },
      previous = 'k',
      next = 'j',
    },
    indent_lines = true,
    auto_open = false,
    auto_close = true,
    auto_preview = true,
    auto_fold = false,
    signs = {
      error = '',
      warning = '',
      hint = '',
      information = '',
      other = '',
    },
    use_diagnostic_signs = true,
  },
  keys = {
    { '<leader>xx', '<cmd>Trouble diagnostics toggle<cr>', desc = 'Diagnostics (Trouble)' },
    { '<leader>xX', '<cmd>Trouble diagnostics toggle filter.buf=0<cr>', desc = 'Buffer Diagnostics (Trouble)' },
    { '<leader>xs', '<cmd>Trouble symbols toggle focus=false<cr>', desc = 'Symbols (Trouble)' },
    { '<leader>xl', '<cmd>Trouble lsp toggle focus=false win.position=right<cr>', desc = 'LSP Definitions / References (Trouble)' },
    { '<leader>xL', '<cmd>Trouble loclist toggle<cr>', desc = 'Location List (Trouble)' },
    { '<leader>xQ', '<cmd>Trouble qflist toggle<cr>', desc = 'Quickfix List (Trouble)' },
    {
      '[q',
      function()
        if require('trouble').is_open() then
          require('trouble').prev { skip_groups = true, jump = true }
        else
          local ok, err = pcall(vim.cmd.cprev)
          if not ok then
            vim.notify(err, vim.log.levels.ERROR)
          end
        end
      end,
      desc = 'Previous Trouble/Quickfix Item',
    },
    {
      ']q',
      function()
        if require('trouble').is_open() then
          require('trouble').next { skip_groups = true, jump = true }
        else
          local ok, err = pcall(vim.cmd.cnext)
          if not ok then
            vim.notify(err, vim.log.levels.ERROR)
          end
        end
      end,
      desc = 'Next Trouble/Quickfix Item',
    },
  },
}
