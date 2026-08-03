-- Test runner: neotest with PHPUnit (Docker-aware) and Go adapters

local function open_term(cmd)
  vim.cmd('botright 15split | terminal ' .. cmd)
  vim.cmd 'startinsert'
end

-- Returns "ClassName::methodName" for the test method nearest to cursor,
-- falling back to just "ClassName" when no method is found.
local function nearest_test_filter()
  local class = vim.fn.expand '%:t:r'
  -- Check current line first (cursor may be on the declaration itself)
  local method = vim.api.nvim_get_current_line():match 'function%s+(test%w+)'
  if not method then
    -- Search backwards for nearest test method declaration
    local line = vim.fn.search('function\\s\\+test', 'bnW')
    if line > 0 then
      method = vim.api.nvim_buf_get_lines(0, line - 1, line, false)[1]:match 'function%s+(%w+)'
    end
  end
  if not method then
    return class
  end
  -- In abstract classes the class name won't match any runnable test — use method alone
  -- so phpunit runs it across all concrete implementations.
  local buf_text = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\n')
  local is_abstract = buf_text:match 'abstract%s+class' ~= nil
  return is_abstract and method or (class .. '::' .. method)
end

return {
  'nvim-neotest/neotest',
  dependencies = {
    'nvim-neotest/nvim-nio',
    'nvim-lua/plenary.nvim',
    'antoinemadec/FixCursorHold.nvim',
    'nvim-treesitter/nvim-treesitter',
    'olimorris/neotest-phpunit',
    'fredrikaverpil/neotest-golang',
  },
  keys = {
    {
      '<leader>Tt',
      function()
        require('neotest').run.run()
      end,
      desc = 'Run nearest test',
    },
    {
      '<leader>Tf',
      function()
        require('neotest').run.run(vim.fn.expand '%')
      end,
      desc = 'Run test file',
    },
    {
      '<leader>Ts',
      function()
        require('neotest').summary.toggle()
      end,
      desc = 'Toggle summary',
    },
    {
      '<leader>To',
      function()
        require('neotest').output.open { enter = true, auto_close = true }
      end,
      desc = 'Show output',
    },
    {
      '<leader>TO',
      function()
        require('neotest').output_panel.toggle()
      end,
      desc = 'Toggle output panel',
    },
    {
      '<leader>Td',
      function()
        require('neotest').run.run { strategy = 'dap' }
      end,
      desc = 'Debug nearest test',
    },
    {
      '<leader>Tw',
      function()
        require('neotest').watch.toggle(vim.fn.expand '%')
      end,
      desc = 'Toggle watch file',
    },
    {
      '<leader>Tx',
      function()
        require('neotest').run.stop()
      end,
      desc = 'Stop test',
    },
    -- Make-based suite runners (PHP only — for integration/API tests needing ephemeral DB)
    {
      '<leader>Tu',
      function()
        open_term 'make test-unit'
      end,
      desc = 'make test-unit',
    },
    {
      '<leader>Ti',
      function()
        open_term 'make test-integration'
      end,
      desc = 'make test-integration',
    },
    {
      '<leader>Ta',
      function()
        open_term 'make test-api'
      end,
      desc = 'make test-api',
    },
  },
  config = function()
    local ok, wk = pcall(require, 'which-key')
    if ok then
      wk.add { { '<leader>T', group = 'Test', icon = '' } }
    end

    -- Filtered make runners registered in config (not keys) so they survive session restore
    local map = function(lhs, cmd, desc)
      vim.keymap.set('n', lhs, function()
        open_term(cmd .. nearest_test_filter())
      end, { desc = desc })
    end
    map('<leader>TI', 'make test-integration-filter FILTER=', 'make test-integration-filter (nearest test)')
    map('<leader>TU', 'make test-unit-filter FILTER=', 'make test-unit-filter (nearest test)')
    map('<leader>TA', 'make test-api-filter FILTER=', 'make test-api-filter (nearest test)')

    require('neotest').setup {
      adapters = {
        require 'neotest-phpunit' {
          -- Use the Docker-aware wrapper from ~/dotfiles/bin/phpunit.
          -- It translates host ↔ container paths and falls back to local vendor/bin.
          phpunit_cmd = function()
            return vim.fn.executable 'phpunit' == 1 and 'phpunit' or 'vendor/bin/phpunit'
          end,
          root_files = { 'composer.json', 'phpunit.xml', 'phpunit.xml.dist' },
          filter_dirs = { '.git', 'node_modules', 'vendor', 'docker', 'var' },
          env = {
            -- Keep off for normal runs. When debugging via <leader>Td (DAP strategy),
            -- set XDEBUG_MODE=debug in the shell before invoking neotest, or use
            -- the project's make debug-integration-filter target instead.
            XDEBUG_MODE = vim.env.XDEBUG_MODE or 'off',
          },
        },
        require 'neotest-golang' {
          runner = 'gotestsum',
          gotestsum_args = { '--format', 'standard-verbose' },
          go_test_args = { '-v', '-race', '-count=1', '-coverprofile=' .. vim.fn.getcwd() .. '/coverage.out' },
          dap_go_opts = {
            delve = { build_flags = { '-tags=integration' } },
          },
        },
      },
      status = {
        virtual_text = true,
        signs = true,
      },
      diagnostic = {
        enabled = true,
      },
      output = {
        enabled = true,
        open_on_run = 'short',
      },
      quickfix = {
        enabled = true,
        open = false,
      },
    }
  end,
}
