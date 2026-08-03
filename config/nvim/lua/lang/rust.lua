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
              vim.cmd.RustLsp 'runnables'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Run targets' }))

            vim.keymap.set('n', '<leader>rd', function()
              vim.cmd.RustLsp 'debuggables'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Debug targets' }))

            vim.keymap.set('n', '<leader>re', function()
              vim.cmd.RustLsp 'expandMacro'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Expand macro' }))

            vim.keymap.set('n', '<leader>rc', function()
              vim.cmd.RustLsp 'openCargo'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Open Cargo.toml' }))

            vim.keymap.set('n', '<leader>rp', function()
              vim.cmd.RustLsp 'parentModule'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Go to parent module' }))

            vim.keymap.set('n', '<leader>rj', function()
              vim.cmd.RustLsp 'joinLines'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Join lines' }))

            vim.keymap.set('n', '<leader>rh', function()
              vim.cmd.RustLsp { 'hover', 'actions' }
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Hover actions' }))

            vim.keymap.set('n', '<leader>ra', function()
              vim.cmd.RustLsp 'codeAction'
            end, vim.tbl_extend('force', opts, { desc = 'Rust: Code actions' }))

            -- NOTE: Standard LSP keymaps (gd, gr, K, etc.) are set globally in features/lsp.lua
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
      local crates = require 'crates'
      crates.setup {
        lsp = {
          enabled = true,
          actions = true,
          completion = true,
          hover = true,
        },
      }

      -- Crates.nvim keymaps (buffer-local for Cargo.toml only)
      -- Uses <leader>C to avoid conflict with <leader>c (Code actions)
      vim.api.nvim_create_autocmd('BufRead', {
        group = vim.api.nvim_create_augroup('CratesKeymaps', { clear = true }),
        pattern = 'Cargo.toml',
        callback = function(event)
          local wk_ok, wk = pcall(require, 'which-key')
          if wk_ok then
            wk.add { { '<leader>C', group = 'Crates', icon = '📦', buffer = event.buf } }
          end
          local opts = { buffer = event.buf, silent = true }
          vim.keymap.set('n', '<leader>Ct', crates.toggle, vim.tbl_extend('force', opts, { desc = 'Toggle crates' }))
          vim.keymap.set('n', '<leader>Cr', crates.reload, vim.tbl_extend('force', opts, { desc = 'Reload crates' }))
          vim.keymap.set('n', '<leader>Cv', crates.show_versions_popup, vim.tbl_extend('force', opts, { desc = 'Show versions' }))
          vim.keymap.set('n', '<leader>Cf', crates.show_features_popup, vim.tbl_extend('force', opts, { desc = 'Show features' }))
          vim.keymap.set('n', '<leader>Cd', crates.show_dependencies_popup, vim.tbl_extend('force', opts, { desc = 'Show dependencies' }))
          vim.keymap.set('n', '<leader>Cu', crates.update_crate, vim.tbl_extend('force', opts, { desc = 'Update crate' }))
          vim.keymap.set('v', '<leader>Cu', crates.update_crates, vim.tbl_extend('force', opts, { desc = 'Update crates' }))
          vim.keymap.set('n', '<leader>CU', crates.upgrade_crate, vim.tbl_extend('force', opts, { desc = 'Upgrade crate' }))
          vim.keymap.set('v', '<leader>CU', crates.upgrade_crates, vim.tbl_extend('force', opts, { desc = 'Upgrade crates' }))
          vim.keymap.set('n', '<leader>CA', crates.upgrade_all_crates, vim.tbl_extend('force', opts, { desc = 'Upgrade all' }))
          vim.keymap.set('n', '<leader>CH', crates.open_homepage, vim.tbl_extend('force', opts, { desc = 'Open homepage' }))
          vim.keymap.set('n', '<leader>CR', crates.open_repository, vim.tbl_extend('force', opts, { desc = 'Open repository' }))
          vim.keymap.set('n', '<leader>CD', crates.open_documentation, vim.tbl_extend('force', opts, { desc = 'Open docs' }))
          vim.keymap.set('n', '<leader>CC', crates.open_crates_io, vim.tbl_extend('force', opts, { desc = 'Open crates.io' }))
        end,
      })
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

-- Rust-specific keymaps (only active in Rust buffers)
-- NOTE: Most Rust keymaps are set in rustaceanvim's on_attach
M.setup_keymaps = function(bufnr)
  -- Additional keymaps if needed can be added here
  -- Rustaceanvim handles most keymaps in its on_attach
end

-- Rust-specific autocommands
M.setup_autocmds = function()
  local rust_group = vim.api.nvim_create_augroup('RustConfig', { clear = true })

  -- File type detection
  vim.filetype.add {
    extension = {
      rs = 'rust',
    },
  }

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
    callback = function(event)
      vim.opt_local.shiftwidth = 4
      vim.opt_local.tabstop = 4
      vim.opt_local.expandtab = true
      vim.opt_local.textwidth = 100
      vim.opt_local.colorcolumn = '100'

      -- Register Rust which-key group (buffer-local)
      local wk_ok, wk = pcall(require, 'which-key')
      if wk_ok then
        wk.add { { '<leader>r', group = 'Rust', icon = '🦀', buffer = event.buf } }
      end

      -- Setup Rust-specific keymaps for this buffer
      M.setup_keymaps(event.buf)
    end,
  })
end

-- Setup function called by the module system
M.setup = function()
  -- Setup autocommands for Rust files
  M.setup_autocmds()
end

return M
