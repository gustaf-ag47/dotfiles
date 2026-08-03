return { -- Autoformat
  'stevearc/conform.nvim',
  event = { 'BufWritePre' },
  cmd = { 'ConformInfo' },
  keys = {
    {
      '<leader>cf',
      function()
        require('conform').format { async = true, lsp_format = 'fallback' }
      end,
      mode = { 'n', 'v' },
      desc = 'Format',
    },
  },
  opts = {
    notify_on_error = false,
    -- Override php_cs_fixer to use our Docker-aware wrapper from ~/dotfiles/bin/.
    -- The local vendor/bin/php-cs-fixer targets the container's PHP version (7.4),
    -- not the host PHP (8.5). Conform's default finder picks up vendor/bin and
    -- fails with a version mismatch; the wrapper handles Docker exec transparently.
    -- Conform creates temp files in the source file's directory (accessible via the
    -- Docker volume mount at /srv).
    formatters = {
      php_cs_fixer = {
        command = vim.fn.exepath 'php-cs-fixer',
      },
    },
    -- PHP-CS-Fixer runs via Docker and is too slow for a synchronous save.
    -- PHP uses format_after_save (async) below; all other filetypes use this.
    format_on_save = function(bufnr)
      local ft = vim.bo[bufnr].filetype
      if ft == 'php' then
        return nil
      end -- handled by format_after_save
      local disable_filetypes = { c = true, cpp = true }
      return {
        timeout_ms = 500,
        lsp_format = disable_filetypes[ft] and 'never' or 'fallback',
      }
    end,
    format_after_save = function(bufnr)
      if vim.bo[bufnr].filetype == 'php' then
        return { lsp_format = 'fallback' }
      end
    end,
    formatters_by_ft = {
      lua = { 'stylua' },
      python = { 'ruff_format', 'ruff_organize_imports' },
      go = { 'gofumpt', 'goimports' },
      rust = { 'rustfmt' },
      php = { 'php_cs_fixer' },
      javascript = { 'prettierd', 'prettier', stop_after_first = true },
      typescript = { 'prettierd', 'prettier', stop_after_first = true },
      javascriptreact = { 'prettierd', 'prettier', stop_after_first = true },
      typescriptreact = { 'prettierd', 'prettier', stop_after_first = true },
      json = { 'prettierd', 'prettier', stop_after_first = true },
      yaml = { 'prettierd', 'prettier', stop_after_first = true },
      markdown = { 'prettierd', 'prettier', stop_after_first = true },
      html = { 'prettierd', 'prettier', stop_after_first = true },
      css = { 'prettierd', 'prettier', stop_after_first = true },
      sh = { 'shfmt' },
      bash = { 'shfmt' },
      zsh = { 'shfmt' },
      sql = { 'sql_formatter' },
      toml = { 'taplo' },
    },
  },
}
