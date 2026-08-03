return {

  { -- Linting
    'mfussenegger/nvim-lint',
    event = { 'BufReadPre', 'BufNewFile' },
    config = function()
      local lint = require 'lint'
      -- Point golangcilint at the Mason-managed binary.
      -- The system go/bin/golangci-lint can be a custom/broken build;
      -- Mason's pre-built release binary is more reliable.
      -- Use Mason's pre-built golangci-lint v2 binary.
      -- The system go/bin/golangci-lint can be a custom/broken build;
      -- Mason's pre-built release binary is more reliable.
      local mason_golangci = vim.fn.stdpath 'data' .. '/mason/bin/golangci-lint'
      if vim.fn.executable(mason_golangci) == 1 then
        lint.linters.golangcilint = vim.tbl_extend('force', lint.linters.golangcilint, {
          cmd = mason_golangci,
        })
      end

      lint.linters_by_ft = {
        sh = { 'shellcheck' },
        bash = { 'shellcheck' },
        dockerfile = { 'hadolint' },
        yaml = { 'yamllint' },
        go = { 'golangcilint' },
        python = { 'ruff' },
        php = { 'phpstan' },
      }

      -- Create autocommand which carries out the actual linting
      -- on the specified events.
      local lint_augroup = vim.api.nvim_create_augroup('lint', { clear = true })
      vim.api.nvim_create_autocmd({ 'BufEnter', 'BufWritePost', 'InsertLeave' }, {
        group = lint_augroup,
        callback = function()
          if not vim.opt_local.modifiable:get() then
            return
          end
          local ft = vim.bo.filetype
          local event = vim.v.event and vim.v.event.event
          -- PHP (phpstan) and Go (golangci-lint) are slow; skip InsertLeave for both
          if (ft == 'php' or ft == 'go') and event == 'InsertLeave' then
            return
          end
          lint.try_lint()
        end,
      })
    end,
  },
}
