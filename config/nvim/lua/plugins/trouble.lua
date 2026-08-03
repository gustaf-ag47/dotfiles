-- Trouble.nvim v3 - Pretty diagnostics, references, quickfix lists
-- Better interface for viewing errors, warnings, and search results

return {
  'folke/trouble.nvim',
  dependencies = { 'nvim-tree/nvim-web-devicons' },
  cmd = 'Trouble',
  opts = {
    auto_close = true,
    auto_preview = true,
    focus = true,
  },
  keys = {
    { '<leader>xt', '<cmd>Trouble diagnostics toggle<cr>', desc = 'All diagnostics' },
    { '<leader>xb', '<cmd>Trouble diagnostics toggle filter.buf=0<cr>', desc = 'Buffer diagnostics' },
    { '<leader>xs', '<cmd>Trouble symbols toggle focus=false<cr>', desc = 'Symbols' },
    { '<leader>xl', '<cmd>Trouble lsp toggle focus=false win.position=right<cr>', desc = 'LSP references' },
    { '<leader>xL', '<cmd>Trouble loclist toggle<cr>', desc = 'Location list' },
    { '<leader>xQ', '<cmd>Trouble qflist toggle<cr>', desc = 'Quickfix list' },
    -- PHPStan project-wide: runs phpstan, feeds results into quickfix+trouble
    {
      '<leader>xP',
      function()
        vim.notify('Running phpstan…', vim.log.levels.INFO)
        vim.fn.setqflist({}, ' ', { title = 'PHPStan' })
        vim.cmd 'cexpr system("phpstan analyse --error-format=raw --no-progress 2>&1")'
        vim.cmd 'Trouble qflist'
      end,
      desc = 'PHPStan → Trouble',
    },
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
