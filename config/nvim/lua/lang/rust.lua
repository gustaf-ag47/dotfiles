-- Rust language configuration
-- Provides rust-analyzer LSP, debugging, and Rust-specific tooling

local M = {}

-- Plugin specifications for Rust development
M.plugins = {
  -- Rust-specific enhancements
  {
    'mrcjkb/rustaceanvim',
    version = '^5', -- Recommended
    lazy = false, -- This plugin is already lazy
    ft = { 'rust' },
    config = function()
      vim.g.rustaceanvim = {
        -- Plugin configuration
        tools = {
          -- Options for rust-analyzer
          hover_actions = {
            auto_focus = true,
          },
          -- Options for debugging
          runnables = {
            use_telescope = true,
          },
          debuggables = {
            use_telescope = true,
          },
        },
        -- LSP configuration
        server = {
          on_attach = function(client, bufnr)
            -- Set up rust-specific keymaps
            local opts = { buffer = bufnr, silent = true }

            -- Rust-specific actions
            vim.keymap.set('n', '<leader>rr', function()
              vim.cmd.RustLsp('runnables')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Run targets' }))

            vim.keymap.set('n', '<leader>rd', function()
              vim.cmd.RustLsp('debuggables')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Debug targets' }))

            vim.keymap.set('n', '<leader>re', function()
              vim.cmd.RustLsp('expandMacro')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Expand macro' }))

            vim.keymap.set('n', '<leader>rc', function()
              vim.cmd.RustLsp('openCargo')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Open Cargo.toml' }))

            vim.keymap.set('n', '<leader>rp', function()
              vim.cmd.RustLsp('parentModule')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Go to parent module' }))

            vim.keymap.set('n', '<leader>rj', function()
              vim.cmd.RustLsp('joinLines')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Join lines' }))

            vim.keymap.set('n', '<leader>rh', function()
              vim.cmd.RustLsp { 'hover', 'actions' }
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Hover actions' }))

            vim.keymap.set('n', '<leader>ra', function()
              vim.cmd.RustLsp('codeAction')
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Code actions' }))

            -- Standard LSP keymaps
            vim.keymap.set('n', 'gD', vim.lsp.buf.declaration, vim.tbl_extend('force', opts, { desc = 'Go to declaration' }))
            vim.keymap.set('n', 'gd', vim.lsp.buf.definition, vim.tbl_extend('force', opts, { desc = 'Go to definition' }))
            vim.keymap.set('n', 'K', vim.lsp.buf.hover, vim.tbl_extend('force', opts, { desc = 'Hover documentation' }))
            vim.keymap.set('n', 'gi', vim.lsp.buf.implementation, vim.tbl_extend('force', opts, { desc = 'Go to implementation' }))
            vim.keymap.set('n', '<C-k>', vim.lsp.buf.signature_help, vim.tbl_extend('force', opts, { desc = 'Signature help' }))
            vim.keymap.set('n', 'gr', vim.lsp.buf.references, vim.tbl_extend('force', opts, { desc = 'Find references' }))
            vim.keymap.set('n', '<leader>rn', vim.lsp.buf.rename, vim.tbl_extend('force', opts, { desc = 'Rename symbol' }))
            vim.keymap.set('n', '<leader>ca', vim.lsp.buf.code_action, vim.tbl_extend('force', opts, { desc = 'Code actions' }))
            vim.keymap.set('n', '<leader>f', function()
              vim.lsp.buf.format { async = true }
            end, vim.tbl_extend('force', opts, { desc = 'Format document' }))
          end,
          default_settings = {
            -- rust-analyzer language server configuration
            ['rust-analyzer'] = {
              -- Enable all features
              cargo = {
                allFeatures = true,
                buildScripts = {
                  enable = true,
                },
              },
              -- Enable procedural macros
              procMacro = {
                enable = true,
              },
              -- Enable check on save
              checkOnSave = {
                command = 'clippy',
                extraArgs = { '--all-targets' },
              },
              -- Inlay hints
              inlayHints = {
                bindingModeHints = {
                  enable = false,
                },
                chainingHints = {
                  enable = true,
                },
                closingBraceHints = {
                  enable = true,
                  minLines = 25,
                },
                closureReturnTypeHints = {
                  enable = 'never',
                },
                lifetimeElisionHints = {
                  enable = 'never',
                  useParameterNames = false,
                },
                maxLength = 25,
                parameterHints = {
                  enable = true,
                },
                reborrowHints = {
                  enable = 'never',
                },
                renderColons = true,
                typeHints = {
                  enable = true,
                  hideClosureInitialization = false,
                  hideNamedConstructor = false,
                },
              },
              -- Assist configuration
              assist = {
                importEnforceGranularity = true,
                importPrefix = 'crate',
              },
              -- Lens configuration
              lens = {
                enable = true,
                run = {
                  enable = true,
                },
                debug = {
                  enable = true,
                },
                implementations = {
                  enable = true,
                },
                references = {
                  adt = {
                    enable = true,
                  },
                  enumVariant = {
                    enable = true,
                  },
                  method = {
                    enable = true,
                  },
                  trait = {
                    enable = true,
                  },
                },
              },
              -- Hover configuration
              hover = {
                actions = {
                  enable = true,
                },
                links = {
                  enable = true,
                },
              },
              -- Semantic highlighting
              semanticHighlighting = {
                strings = {
                  enable = true,
                },
              },
              -- Completion configuration
              completion = {
                postfix = {
                  enable = true,
                },
                privateEditable = {
                  enable = false,
                },
                callable = {
                  snippets = 'fill_arguments',
                },
              },
            },
          },
        },
        -- DAP configuration
        dap = {
          adapter = {
            type = 'executable',
            command = 'lldb-dap',
            name = 'rt_lldb',
          },
        },
      }
    end,
  },

  -- Crates.nvim for Cargo.toml management
  {
    'saecki/crates.nvim',
    ft = { 'rust', 'toml' },
    config = function()
      require('crates').setup {
        completion = {
          cmp = {
            enabled = true,
          },
          crates = {
            enabled = true,
            max_results = 8,
            min_chars = 3,
          },
        },
        lsp = {
          enabled = true,
          actions = true,
          completion = true,
          hover = true,
        },
      }

      -- Crates.nvim keymaps
      local opts = { silent = true }
      vim.keymap.set('n', '<leader>ct', require('crates').toggle, vim.tbl_extend('force', opts, { desc = 'Crates: Toggle' }))
      vim.keymap.set('n', '<leader>cr', require('crates').reload, vim.tbl_extend('force', opts, { desc = 'Crates: Reload' }))

      vim.keymap.set('n', '<leader>cv', require('crates').show_versions_popup, vim.tbl_extend('force', opts, { desc = 'Crates: Show versions' }))
      vim.keymap.set('n', '<leader>cf', require('crates').show_features_popup, vim.tbl_extend('force', opts, { desc = 'Crates: Show features' }))
      vim.keymap.set('n', '<leader>cd', require('crates').show_dependencies_popup, vim.tbl_extend('force', opts, { desc = 'Crates: Show dependencies' }))

      vim.keymap.set('n', '<leader>cu', require('crates').update_crate, vim.tbl_extend('force', opts, { desc = 'Crates: Update crate' }))
      vim.keymap.set('v', '<leader>cu', require('crates').update_crates, vim.tbl_extend('force', opts, { desc = 'Crates: Update crates' }))
      vim.keymap.set('n', '<leader>ca', require('crates').update_all_crates, vim.tbl_extend('force', opts, { desc = 'Crates: Update all' }))

      vim.keymap.set('n', '<leader>cU', require('crates').upgrade_crate, vim.tbl_extend('force', opts, { desc = 'Crates: Upgrade crate' }))
      vim.keymap.set('v', '<leader>cU', require('crates').upgrade_crates, vim.tbl_extend('force', opts, { desc = 'Crates: Upgrade crates' }))
      vim.keymap.set('n', '<leader>cA', require('crates').upgrade_all_crates, vim.tbl_extend('force', opts, { desc = 'Crates: Upgrade all' }))

      vim.keymap.set('n', '<leader>cH', require('crates').open_homepage, vim.tbl_extend('force', opts, { desc = 'Crates: Open homepage' }))
      vim.keymap.set('n', '<leader>cR', require('crates').open_repository, vim.tbl_extend('force', opts, { desc = 'Crates: Open repository' }))
      vim.keymap.set('n', '<leader>cD', require('crates').open_documentation, vim.tbl_extend('force', opts, { desc = 'Crates: Open documentation' }))
      vim.keymap.set('n', '<leader>cC', require('crates').open_crates_io, vim.tbl_extend('force', opts, { desc = 'Crates: Open crates.io' }))
    end,
  },
}

-- LSP configuration that will be registered with the LSP feature module
M.lsp_config = {
  -- rust-analyzer is handled by rustaceanvim, so we don't need to configure it here
}

-- Debug configuration for Rust
M.debug_config = {
  adapters = {
    lldb = {
      type = 'executable',
      command = 'lldb-dap',
      name = 'lldb',
    },
  },
  configurations = {
    rust = {
      {
        name = 'Launch',
        type = 'lldb',
        request = 'launch',
        program = function()
          return vim.fn.input('Path to executable: ', vim.fn.getcwd() .. '/', 'file')
        end,
        cwd = '${workspaceFolder}',
        stopOnEntry = false,
        args = {},
        runInTerminal = false,
      },
    },
  },
}

-- Setup function called by the module system
M.setup = function()
  -- File type detection
  vim.filetype.add {
    extension = {
      rs = 'rust',
    },
  }

  -- Rust-specific autocommands
  local rust_group = vim.api.nvim_create_augroup('RustConfig', { clear = true })

  -- Auto-format on save
  vim.api.nvim_create_autocmd('BufWritePre', {
    group = rust_group,
    pattern = '*.rs',
    callback = function()
      vim.lsp.buf.format { async = false }
    end,
  })

  -- Set up Rust-specific options
  vim.api.nvim_create_autocmd('FileType', {
    group = rust_group,
    pattern = 'rust',
    callback = function()
      vim.opt_local.shiftwidth = 4
      vim.opt_local.tabstop = 4
      vim.opt_local.expandtab = true
      vim.opt_local.textwidth = 100
      vim.opt_local.colorcolumn = '100'
    end,
  })

  -- Enhanced Rust snippets
  vim.api.nvim_create_autocmd('FileType', {
    group = rust_group,
    pattern = 'rust',
    callback = function()
      -- Custom Rust snippets can be added here
      -- They will be loaded by LuaSnip if available
    end,
  })
end

return M