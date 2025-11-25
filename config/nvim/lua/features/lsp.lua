-- LSP feature module - isolated and following SRP
-- Responsible only for LSP server management and configuration
-- No dependencies on language-specific modules (dependency rule compliance)

local M = {}

-- Core LSP plugins
M.plugins = {
  {
    'neovim/nvim-lspconfig',
    dependencies = {
      { 'williamboman/mason.nvim', config = true },
      'williamboman/mason-lspconfig.nvim',
      'WhoIsSethDaniel/mason-tool-installer.nvim',
      { 'j-hui/fidget.nvim', opts = {} },
      'hrsh7th/cmp-nvim-lsp',
      'b0o/schemastore.nvim', -- JSON/YAML schema support
    },
    config = function()
      -- This will be handled by the feature setup
    end,
  },
}

-- LSP attach keymaps and behavior
M.setup_lsp_attach = function()
  vim.api.nvim_create_autocmd('LspAttach', {
    group = vim.api.nvim_create_augroup('lsp-attach', { clear = true }),
    callback = function(event)
      local map = function(keys, func, desc, mode)
        mode = mode or 'n'
        vim.keymap.set(mode, keys, func, { buffer = event.buf, desc = 'LSP: ' .. desc })
      end

      -- Navigation
      map('gd', require('telescope.builtin').lsp_definitions, '[G]oto [D]efinition')
      map('gr', require('telescope.builtin').lsp_references, '[G]oto [R]eferences')
      map('gI', require('telescope.builtin').lsp_implementations, '[G]oto [I]mplementation')
      map('<leader>D', require('telescope.builtin').lsp_type_definitions, 'Type [D]efinition')
      map('gD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')

      -- Symbols and workspace
      map('<leader>ds', require('telescope.builtin').lsp_document_symbols, '[D]ocument [S]ymbols')
      map('<leader>ws', require('telescope.builtin').lsp_dynamic_workspace_symbols, '[W]orkspace [S]ymbols')

      -- Code actions
      map('<leader>rn', vim.lsp.buf.rename, '[R]e[n]ame')
      map('<leader>ca', vim.lsp.buf.code_action, '[C]ode [A]ction', { 'n', 'x' })

      -- Document highlighting
      local client = vim.lsp.get_client_by_id(event.data.client_id)
      if client and client.supports_method(vim.lsp.protocol.Methods.textDocument_documentHighlight) then
        local highlight_augroup = vim.api.nvim_create_augroup('lsp-highlight', { clear = false })
        vim.api.nvim_create_autocmd({ 'CursorHold', 'CursorHoldI' }, {
          buffer = event.buf,
          group = highlight_augroup,
          callback = vim.lsp.buf.document_highlight,
        })

        vim.api.nvim_create_autocmd({ 'CursorMoved', 'CursorMovedI' }, {
          buffer = event.buf,
          group = highlight_augroup,
          callback = vim.lsp.buf.clear_references,
        })

        vim.api.nvim_create_autocmd('LspDetach', {
          group = vim.api.nvim_create_augroup('lsp-detach', { clear = true }),
          callback = function(event2)
            vim.lsp.buf.clear_references()
            vim.api.nvim_clear_autocmds { group = 'lsp-highlight', buffer = event2.buf }
          end,
        })
      end

      -- Inlay hints
      if client and client.supports_method(vim.lsp.protocol.Methods.textDocument_inlayHint) then
        map('<leader>th', function()
          vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = event.buf })
        end, '[T]oggle Inlay [H]ints')
      end
    end,
  })
end

-- LSP server configurations (language-agnostic)
M.base_servers = {
  -- Bash language server with .env file exclusion
  bashls = {
    filetypes = { 'sh', 'bash' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      -- Don't attach to .env files
      if fname:match('%.env') or fname:match('%.env%.') then
        return nil
      end
      return util.find_git_ancestor(fname)
    end,
    settings = {
      bashIde = {
        globPattern = "**/*@(.sh|.inc|.bash|.command)",
      },
    },
  },

  lua_ls = {
    settings = {
      Lua = {
        completion = {
          callSnippet = 'Replace',
        },
        diagnostics = {
          globals = { 'vim' },
        },
        workspace = {
          library = {
            vim.env.VIMRUNTIME,
            "${3rd}/luv/library",
            "${3rd}/busted/library",
          },
          checkThirdParty = false,
        },
        telemetry = { enable = false },
      },
    },
  },

  -- JSON language server
  jsonls = {
    settings = {
      json = {
        validate = { enable = true },
      },
    },
    on_new_config = function(new_config)
      -- Try to load schemastore schemas
      local ok, schemastore = pcall(require, 'schemastore')
      if ok then
        new_config.settings.json.schemas = schemastore.json.schemas()
      end
    end,
  },

  -- YAML language server
  yamlls = {
    settings = {
      yaml = {
        schemaStore = {
          enable = false,
          url = '',
        },
        format = {
          enable = true,
        },
        validate = true,
        completion = true,
        hover = true,
      },
    },
    on_new_config = function(new_config)
      -- Try to load schemastore schemas
      local ok, schemastore = pcall(require, 'schemastore')
      if ok then
        new_config.settings.yaml.schemas = schemastore.yaml.schemas()
      end
    end,
  },

  -- TOML language server
  taplo = {
    settings = {
      taplo = {
        configFile = {
          enabled = true,
        },
        schema = {
          enabled = true,
        },
      },
    },
  },

  -- Dockerfile language server
  dockerls = {
    settings = {
      docker = {
        languageserver = {
          formatter = {
            ignoreMultilineInstructions = true,
          },
        },
      },
    },
  },
}

-- Get default capabilities with completion support
M.get_capabilities = function()
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  if pcall(require, 'cmp_nvim_lsp') then
    capabilities = vim.tbl_deep_extend('force', capabilities, require('cmp_nvim_lsp').default_capabilities())
  end
  return capabilities
end

-- Setup Mason and LSP servers
M.setup_mason = function()
  require('mason').setup({
    ui = {
      border = 'rounded',
      icons = {
        package_installed = '✓',
        package_pending = '➜',
        package_uninstalled = '✗'
      }
    },
    install_root_dir = vim.fn.stdpath('data') .. '/mason',
  })

  -- Modern language servers and tools
  local ensure_installed = vim.tbl_keys(M.base_servers or {})
  vim.list_extend(ensure_installed, {
    -- Language servers
    'typescript-language-server',
    'eslint-lsp',
    'rust-analyzer',
    'pyright',
    'ruff',
    'json-lsp',
    'yaml-language-server',
    'dockerfile-language-server',
    'taplo', -- TOML language server
    'bash-language-server',

    -- Formatters
    'stylua', -- Lua formatter
    'prettier', -- JS/TS/JSON/YAML formatter
    'ruff', -- Python formatter/linter
    'rustfmt', -- Rust formatter

    -- Linters
    'eslint_d', -- Fast ESLint
    'mypy', -- Python type checker

    -- Debug adapters
    'js-debug-adapter', -- JavaScript/TypeScript debugger
    'debugpy', -- Python debugger
    'codelldb', -- Rust/C++ debugger
  })

  require('mason-tool-installer').setup {
    ensure_installed = ensure_installed,
    auto_update = true,
    run_on_start = true,
    start_delay = 3000, -- 3 second delay
    debounce_hours = 5, -- at least 5 hours between attempts
  }

  require('mason-lspconfig').setup {
    automatic_installation = true,
    handlers = {
      function(server_name)
        local server = M.base_servers[server_name] or {}
        server.capabilities = vim.tbl_deep_extend('force', {}, M.get_capabilities(), server.capabilities or {})
        require('lspconfig')[server_name].setup(server)
      end,
    },
  }
end

-- Register a language server configuration
M.register_server = function(server_name, config)
  if not M.base_servers then
    M.base_servers = {}
  end

  M.base_servers[server_name] = vim.tbl_deep_extend('force', {
    capabilities = M.get_capabilities(),
  }, config or {})

  -- If LSP is already setup, configure this server immediately
  if package.loaded['lspconfig'] then
    require('lspconfig')[server_name].setup(M.base_servers[server_name])
  end
end

-- Setup LSP diagnostics
M.setup_diagnostics = function()
  vim.diagnostic.config({
    virtual_text = {
      prefix = '●',
      source = 'if_many',
    },
    signs = true,
    underline = true,
    update_in_insert = false,
    severity_sort = true,
    float = {
      border = 'rounded',
      source = 'always',
      header = '',
      prefix = '',
    },
  })

  -- Diagnostic signs
  if vim.g.have_nerd_font then
    local signs = { Error = '󰅚 ', Warn = '󰀪 ', Hint = '󰌶 ', Info = ' ' }
    for type, icon in pairs(signs) do
      local hl = 'DiagnosticSign' .. type
      vim.fn.sign_define(hl, { text = icon, texthl = hl, numhl = hl })
    end
  end
end

-- Setup the LSP feature module
M.setup = function()
  -- Setup LSP diagnostics first
  M.setup_diagnostics()

  -- Setup LSP attach behavior
  M.setup_lsp_attach()

  -- Setup Mason and LSP servers
  M.setup_mason()
end

return M