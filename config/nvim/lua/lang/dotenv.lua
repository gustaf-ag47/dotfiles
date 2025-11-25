-- .env file language configuration
-- Provides proper filetype detection and prevents shell linting warnings

local M = {}

-- Plugin specifications for .env file support
M.plugins = {}

-- LSP configuration - explicitly disable shell LSP for .env files
M.lsp_config = {}

-- Setup function called by the module system
M.setup = function()
  -- File type detection for .env files
  vim.filetype.add {
    filename = {
      ['.env'] = 'dotenv',
      ['.env.local'] = 'dotenv',
      ['.env.development'] = 'dotenv',
      ['.env.production'] = 'dotenv',
      ['.env.staging'] = 'dotenv',
      ['.env.test'] = 'dotenv',
    },
    pattern = {
      ['%.env%..*'] = 'dotenv',
    },
  }

  -- .env file-specific autocommands
  local dotenv_group = vim.api.nvim_create_augroup('DotenvConfig', { clear = true })

  -- Set up .env file-specific options
  vim.api.nvim_create_autocmd('FileType', {
    group = dotenv_group,
    pattern = 'dotenv',
    callback = function()
      -- Disable diagnostics from bash LSP for .env files
      vim.diagnostic.config({
        virtual_text = false,
        signs = false,
        underline = false,
        update_in_insert = false,
        severity_sort = false,
      }, vim.api.nvim_get_current_buf())

      -- Set proper options for .env files
      vim.opt_local.filetype = 'dotenv'
      vim.opt_local.syntax = 'sh'  -- Use shell syntax highlighting but disable linting
      vim.opt_local.commentstring = '# %s'

      -- Disable LSP for this buffer if it's attached
      local clients = vim.lsp.get_active_clients({ bufnr = 0 })
      for _, client in ipairs(clients) do
        if client.name == 'bashls' or client.name == 'bash-language-server' then
          vim.lsp.buf_detach_client(0, client.id)
        end
      end
    end,
  })

  -- Prevent bash LSP from attaching to .env files
  vim.api.nvim_create_autocmd('LspAttach', {
    group = dotenv_group,
    callback = function(args)
      local client = vim.lsp.get_client_by_id(args.data.client_id)
      if client and (client.name == 'bashls' or client.name == 'bash-language-server') then
        local bufname = vim.api.nvim_buf_get_name(args.buf)
        if bufname:match('%.env') or bufname:match('%.env%.') then
          vim.lsp.buf_detach_client(args.buf, client.id)
        end
      end
    end,
  })

  -- Create .env file specific keymaps
  vim.api.nvim_create_autocmd('FileType', {
    group = dotenv_group,
    pattern = 'dotenv',
    callback = function()
      local opts = { buffer = true, silent = true }

      -- Toggle commented lines
      vim.keymap.set('n', '<leader>/', function()
        local line = vim.api.nvim_get_current_line()
        local row = vim.api.nvim_win_get_cursor(0)[1]

        if line:match('^%s*#') then
          -- Uncomment
          local new_line = line:gsub('^(%s*)#%s*', '%1')
          vim.api.nvim_buf_set_lines(0, row - 1, row, false, { new_line })
        else
          -- Comment
          local new_line = '# ' .. line
          vim.api.nvim_buf_set_lines(0, row - 1, row, false, { new_line })
        end
      end, vim.tbl_extend('force', opts, { desc = 'Toggle comment' }))

      -- Sort environment variables
      vim.keymap.set('n', '<leader>es', function()
        vim.cmd('sort')
      end, vim.tbl_extend('force', opts, { desc = 'Sort env vars' }))
    end,
  })

  -- Custom syntax highlighting for .env files
  vim.api.nvim_create_autocmd('FileType', {
    group = dotenv_group,
    pattern = 'dotenv',
    callback = function()
      -- Define custom syntax highlighting
      vim.cmd([[
        syntax match EnvComment "^#.*$"
        syntax match EnvKey "^[A-Z_][A-Z0-9_]*" nextgroup=EnvEquals
        syntax match EnvEquals "=" contained nextgroup=EnvValue
        syntax match EnvValue ".*$" contained
        syntax match EnvQuotedValue '"[^"]*"' contained
        syntax match EnvQuotedValue "'[^']*'" contained

        highlight default link EnvComment Comment
        highlight default link EnvKey Identifier
        highlight default link EnvEquals Operator
        highlight default link EnvValue String
        highlight default link EnvQuotedValue String
      ]])
    end,
  })
end

return M