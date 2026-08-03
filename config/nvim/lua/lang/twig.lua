-- Twig language module
-- twiggy-language-server: completion, go-to-def, inlay hints for .twig files
-- Symfony mode gives route/service/template-name awareness.

local M = {}

M.plugins = {
  {
    'nvim-treesitter/nvim-treesitter',
    optional = true,
    opts = function(_, opts)
      if type(opts.ensure_installed) == 'table' then
        vim.list_extend(opts.ensure_installed, { 'twig', 'html' })
      end
    end,
  },
}

M.lsp_config = {
  twiggy_language_server = {
    cmd = { 'twiggy-language-server', '--stdio' },
    filetypes = { 'twig', 'html.twig' },
    root_markers = { 'composer.json', '.git' },
    init_options = {
      framework = 'symfony',
      phpExecutable = 'php',
      -- Enables bin/console debug:twig + debug:router for route/function completion
      symfonyConsolePath = 'bin/console',
    },
  },
}

M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set
  map('n', 'gd', vim.lsp.buf.definition, vim.tbl_extend('force', opts, { desc = 'Go to definition' }))
  map('n', 'K', vim.lsp.buf.hover, vim.tbl_extend('force', opts, { desc = 'Hover' }))
end

M.setup_autocmds = function()
  vim.api.nvim_create_autocmd('FileType', {
    group = vim.api.nvim_create_augroup('TwigConfig', { clear = true }),
    pattern = { 'twig', 'html.twig' },
    callback = function(event)
      local wk_ok, wk = pcall(require, 'which-key')
      if wk_ok then
        wk.add { { '<leader>T', group = 'Twig', icon = '', buffer = event.buf } }
      end
      M.setup_keymaps(event.buf)
    end,
  })
end

M.setup = function()
  M.setup_autocmds()

  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local ok, cmp_nvim_lsp = pcall(require, 'cmp_nvim_lsp')
  if ok then
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  end

  vim.lsp.config('twiggy_language_server', vim.tbl_deep_extend('force', M.lsp_config.twiggy_language_server, { capabilities = capabilities }))
  vim.lsp.enable 'twiggy_language_server'
end

return M
