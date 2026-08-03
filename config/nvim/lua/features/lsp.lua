-- LSP feature module - isolated and following SRP
-- Responsible only for LSP server management and configuration
-- No dependencies on language-specific modules (dependency rule compliance)
-- Updated for Neovim 0.11+ native LSP configuration (vim.lsp.config)

local M = {}

-- Core LSP plugins
M.plugins = {
  {
    'neovim/nvim-lspconfig',
    event = { 'BufReadPre', 'BufNewFile' },
    dependencies = {
      { 'williamboman/mason.nvim', config = true },
      'williamboman/mason-lspconfig.nvim',
      'WhoIsSethDaniel/mason-tool-installer.nvim',
      { 'j-hui/fidget.nvim', opts = {} },
      'hrsh7th/cmp-nvim-lsp',
      'b0o/schemastore.nvim', -- JSON/YAML schema support
    },
    config = function()
      -- Setup LSP when plugin loads
      require('features.lsp').setup()
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
        vim.keymap.set(mode, keys, func, { buffer = event.buf, desc = desc })
      end

      -- Navigation (g prefix - standard vim convention)
      --
      -- Telescope's lsp_definitions/etc. capture the window inside the async
      -- vim.schedule callback, so nvim_get_current_win() may return a Telescope
      -- picker window by the time it fires (e.g. intelephense returns 9 results
      -- for an interface → picker opens → picker window becomes current →
      -- nvim_win_set_buf on the picker window closes it → nvim_set_current_win
      -- fails with "Invalid window id"). Fix: capture win BEFORE the LSP request
      -- using vim.lsp.buf.definition with on_list, then pass the pre-captured
      -- win to the single-result jump, or open Telescope with pre-resolved items
      -- for multi-result cases.
      local function lsp_goto(method, telescope_fn)
        return function()
          local win = vim.api.nvim_get_current_win()
          local opts = {
            on_list = function(options)
              if #options.items == 0 then return end
              if #options.items == 1 then
                local item = options.items[1]
                local b = item.bufnr or vim.fn.bufadd(item.filename)
                vim.cmd("normal! m'")
                vim.bo[b].buflisted = true
                vim.api.nvim_win_set_buf(win, b)
                vim.api.nvim_win_set_cursor(win, { item.lnum, item.col - 1 })
              else
                local conf = require('telescope.config').values
                require('telescope.pickers').new({}, {
                  prompt_title = telescope_fn:gsub('_', ' '):gsub('^%l', string.upper),
                  finder = require('telescope.finders').new_table({
                    results = options.items,
                    entry_maker = require('telescope.make_entry').gen_from_quickfix({}),
                  }),
                  previewer = conf.qflist_previewer({}),
                  sorter = conf.generic_sorter({}),
                  push_cursor_on_edit = true,
                  push_tagstack_on_edit = true,
                }):find()
              end
            end,
          }
          -- vim.lsp.buf.references has signature (context, opts); others have (opts)
          if method == 'references' then
            vim.lsp.buf.references(nil, opts)
          else
            vim.lsp.buf[method](opts)
          end
        end
      end
      map('gd', lsp_goto('definition', 'lsp_definitions'), 'Go to definition')
      map('gr', lsp_goto('references', 'lsp_references'), 'Go to references')
      map('gI', lsp_goto('implementation', 'lsp_implementations'), 'Go to implementation')
      map('gD', vim.lsp.buf.declaration, 'Go to declaration')
      map('gy', lsp_goto('type_definition', 'lsp_type_definitions'), 'Go to type definition')

      -- LSP commands (l prefix)
      map('<leader>ls', require('telescope.builtin').lsp_document_symbols, 'Document symbols')
      map('<leader>lS', require('telescope.builtin').lsp_dynamic_workspace_symbols, 'Workspace symbols')
      map('<leader>li', ':LspInfo<CR>', 'LSP info')
      map('<leader>lr', ':LspRestart<CR>', 'LSP restart')

      -- Code actions (c prefix)
      -- Rename handled by inc-rename.nvim plugin
      map('<leader>ca', vim.lsp.buf.code_action, 'Code action', { 'n', 'x' })

      -- Document highlighting
      local client = vim.lsp.get_client_by_id(event.data.client_id)
      if client and client:supports_method(vim.lsp.protocol.Methods.textDocument_documentHighlight) then
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

      -- Inlay hints toggle
      if client and client:supports_method(vim.lsp.protocol.Methods.textDocument_inlayHint) then
        map('<leader>uh', function()
          vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled { bufnr = event.buf })
        end, 'Toggle inlay hints')
      end
    end,
  })
end

-- LSP server configurations (language-agnostic)
M.base_servers = {
  -- Bash language server with .env file exclusion
  bashls = {
    filetypes = { 'sh', 'bash' },
    root_markers = { '.git', '.hg' },
    on_attach = function(client, bufnr)
      local fname = vim.api.nvim_buf_get_name(bufnr)
      if fname:match('%.env') or fname:match('%.env%.') then
        client:stop()
      end
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

  -- Python language servers
  pyright = {
    settings = {
      python = {
        analysis = {
          typeCheckingMode = 'basic',
          autoImportCompletions = true,
          diagnosticMode = 'workspace',
          autoSearchPaths = true,
          useLibraryCodeForTypes = true,
        },
      },
    },
  },

  ruff = {},

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
    'taplo',
    'bash-language-server',
    'intelephense',
    'phpactor',
    'twiggy-language-server',

    -- Formatters
    'stylua',
    'prettier',
    'ruff',
    'php-cs-fixer',

    -- Linters
    'eslint_d',
    'mypy',
    'phpstan',

    -- Go tools
    'gopls',
    'gofumpt',
    'goimports',
    'golangci-lint',
    'delve',
    'gotestsum',
    'impl',
    'gomodifytags',
    'staticcheck',
    -- govulncheck is not in the Mason registry; install via: go install golang.org/x/vuln/cmd/govulncheck@latest

    -- Debug adapters
    'js-debug-adapter',
    'debugpy',
    'codelldb',
    'php-debug-adapter',
  })

  require('mason-tool-installer').setup {
    ensure_installed = ensure_installed,
    auto_update = true,
    run_on_start = true,
    start_delay = 3000, -- 3 second delay
    debounce_hours = 5, -- at least 5 hours between attempts
  }

  -- Setup mason-lspconfig with automatic installation
  require('mason-lspconfig').setup {
    automatic_installation = true,
  }

  -- Configure and enable LSP servers using Neovim 0.11+ native API
  local capabilities = M.get_capabilities()
  local servers_to_enable = {}

  for server_name, server_config in pairs(M.base_servers) do
    local config = vim.tbl_deep_extend('force', {}, server_config)
    config.capabilities = vim.tbl_deep_extend('force', {}, capabilities, config.capabilities or {})

    -- Use vim.lsp.config for Neovim 0.11+
    vim.lsp.config(server_name, config)
    table.insert(servers_to_enable, server_name)
  end

  -- Enable all configured servers
  vim.lsp.enable(servers_to_enable)
end

-- Register a language server configuration
M.register_server = function(server_name, config)
  if not M.base_servers then
    M.base_servers = {}
  end

  M.base_servers[server_name] = vim.tbl_deep_extend('force', {
    capabilities = M.get_capabilities(),
  }, config or {})

  -- Configure and enable this server immediately using native API
  vim.lsp.config(server_name, M.base_servers[server_name])
  vim.lsp.enable(server_name)
end

-- Setup LSP diagnostics
M.setup_diagnostics = function()
  vim.diagnostic.config({
    virtual_text = {
      prefix = '●',
      source = 'if_many',
    },
    signs = vim.g.have_nerd_font and {
      text = {
        [vim.diagnostic.severity.ERROR] = '󰅚 ',
        [vim.diagnostic.severity.WARN]  = '󰀪 ',
        [vim.diagnostic.severity.HINT]  = '󰌶 ',
        [vim.diagnostic.severity.INFO]  = ' ',
      },
    } or true,
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