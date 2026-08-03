-- Refactoring operations: extract function/variable, inline, and more
-- Provides JetBrains-like refactoring capabilities with preview support

return {
  'ThePrimeagen/refactoring.nvim',
  dependencies = {
    'nvim-lua/plenary.nvim',
    'nvim-treesitter/nvim-treesitter',
    'lewis6991/async.nvim',
  },
  event = { 'BufReadPre', 'BufNewFile' },
  config = function()
    require('refactoring').setup({
      -- Prompt for function return type (for statically typed languages)
      prompt_func_return_type = {
        go = true,
        java = true,
        cpp = true,
        c = true,
        typescript = true,
      },
      -- Prompt for function parameter types
      prompt_func_param_type = {
        go = true,
        java = true,
        cpp = true,
        c = true,
        typescript = true,
      },
      -- Print variable statements (for debugging)
      printf_statements = {},
      print_var_statements = {},
      -- Show success message after refactoring
      show_success_message = true,
    })

  end,
  keys = {
    -- Visual mode refactoring
    {
      '<leader>re',
      function()
        require('refactoring').refactor('Extract Function')
      end,
      mode = 'x',
      desc = 'Extract function',
    },
    {
      '<leader>rf',
      function()
        require('refactoring').refactor('Extract Function To File')
      end,
      mode = 'x',
      desc = 'Extract function to file',
    },
    {
      '<leader>rv',
      function()
        require('refactoring').refactor('Extract Variable')
      end,
      mode = 'x',
      desc = 'Extract variable',
    },
    {
      '<leader>rI',
      function()
        require('refactoring').refactor('Inline Function')
      end,
      mode = 'n',
      desc = 'Inline function',
    },
    {
      '<leader>ri',
      function()
        require('refactoring').refactor('Inline Variable')
      end,
      mode = { 'n', 'x' },
      desc = 'Inline variable',
    },
    {
      '<leader>rb',
      function()
        require('refactoring').refactor('Extract Block')
      end,
      mode = 'n',
      desc = 'Extract block',
    },
    {
      '<leader>rB',
      function()
        require('refactoring').refactor('Extract Block To File')
      end,
      mode = 'n',
      desc = 'Extract block to file',
    },
    -- Select refactoring from menu
    {
      '<leader>rr',
      function()
        require('refactoring').select_refactor()
      end,
      mode = { 'n', 'x' },
      desc = 'Select refactoring',
    },
    -- Debug helpers (print variable)
    {
      '<leader>rp',
      function()
        require('refactoring').debug.printf({ below = false })
      end,
      mode = 'n',
      desc = 'Debug print',
    },
    {
      '<leader>rV',
      function()
        require('refactoring').debug.print_var()
      end,
      mode = { 'n', 'x' },
      desc = 'Debug print variable',
    },
    {
      '<leader>rc',
      function()
        require('refactoring').debug.cleanup({})
      end,
      mode = 'n',
      desc = 'Debug cleanup',
    },
  },
}
