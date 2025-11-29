-- TypeScript/JavaScript language configuration
-- Provides TypeScript LSP, ESLint, Prettier, and modern JS/TS tooling

local M = {}

-- Plugin specifications for TypeScript/JavaScript development
M.plugins = {
  -- TypeScript.nvim for enhanced TypeScript support
  {
    'pmizio/typescript-tools.nvim',
    dependencies = { 'nvim-lua/plenary.nvim', 'neovim/nvim-lspconfig' },
    ft = { 'typescript', 'typescriptreact', 'javascript', 'javascriptreact', 'vue' },
    config = function()
      require('typescript-tools').setup {
        on_attach = function(client, bufnr)
          -- TypeScript-specific keymaps
          local opts = { buffer = bufnr, silent = true }

          -- TypeScript-specific actions
          vim.keymap.set('n', '<leader>to', '<cmd>TSToolsOrganizeImports<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Organize imports' }))
          vim.keymap.set('n', '<leader>ts', '<cmd>TSToolsSortImports<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Sort imports' }))
          vim.keymap.set('n', '<leader>tr', '<cmd>TSToolsRemoveUnused<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Remove unused' }))
          vim.keymap.set('n', '<leader>tf', '<cmd>TSToolsFixAll<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Fix all' }))
          vim.keymap.set('n', '<leader>ta', '<cmd>TSToolsAddMissingImports<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Add missing imports' }))
          vim.keymap.set('n', '<leader>td', '<cmd>TSToolsGoToSourceDefinition<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Go to source definition' }))
          vim.keymap.set('n', '<leader>th', '<cmd>TSToolsFileReferences<cr>', vim.tbl_extend('force', opts, { desc = 'TS: File references' }))
          vim.keymap.set('n', '<leader>ti', '<cmd>TSToolsRenameFile<cr>', vim.tbl_extend('force', opts, { desc = 'TS: Rename file' }))

          -- NOTE: Standard LSP keymaps (gd, gr, K, etc.) are set globally in features/lsp.lua
        end,
        settings = {
          -- TypeScript server settings
          typescript = {
            inlayHints = {
              includeInlayParameterNameHints = 'all',
              includeInlayParameterNameHintsWhenArgumentMatchesName = false,
              includeInlayFunctionParameterTypeHints = true,
              includeInlayVariableTypeHints = true,
              includeInlayVariableTypeHintsWhenTypeMatchesName = false,
              includeInlayPropertyDeclarationTypeHints = true,
              includeInlayFunctionLikeReturnTypeHints = true,
              includeInlayEnumMemberValueHints = true,
            },
          },
          javascript = {
            inlayHints = {
              includeInlayParameterNameHints = 'all',
              includeInlayParameterNameHintsWhenArgumentMatchesName = false,
              includeInlayFunctionParameterTypeHints = true,
              includeInlayVariableTypeHints = true,
              includeInlayVariableTypeHintsWhenTypeMatchesName = false,
              includeInlayPropertyDeclarationTypeHints = true,
              includeInlayFunctionLikeReturnTypeHints = true,
              includeInlayEnumMemberValueHints = true,
            },
          },
        },
      }
    end,
  },

  -- Enhanced package.json support
  {
    'vuki656/package-info.nvim',
    dependencies = 'MunifTanjim/nui.nvim',
    ft = 'json',
    config = function()
      require('package-info').setup {
        colors = {
          up_to_date = '#3C4048',
          outdated = '#fc7b7b',
        },
        icons = {
          enable = true,
          style = {
            up_to_date = '|  ',
            outdated = '|  ',
          },
        },
        autostart = true,
        hide_up_to_date = false,
        hide_unstable_versions = false,
        package_manager = 'npm',
      }

      -- Package.json keymaps
      local opts = { silent = true }
      vim.keymap.set('n', '<leader>ns', require('package-info').show, vim.tbl_extend('force', opts, { desc = 'Package: Show info' }))
      vim.keymap.set('n', '<leader>nc', require('package-info').hide, vim.tbl_extend('force', opts, { desc = 'Package: Hide info' }))
      vim.keymap.set('n', '<leader>nt', require('package-info').toggle, vim.tbl_extend('force', opts, { desc = 'Package: Toggle info' }))
      vim.keymap.set('n', '<leader>nu', require('package-info').update, vim.tbl_extend('force', opts, { desc = 'Package: Update' }))
      vim.keymap.set('n', '<leader>nd', require('package-info').delete, vim.tbl_extend('force', opts, { desc = 'Package: Delete' }))
      vim.keymap.set('n', '<leader>ni', require('package-info').install, vim.tbl_extend('force', opts, { desc = 'Package: Install' }))
      vim.keymap.set('n', '<leader>np', require('package-info').change_version, vim.tbl_extend('force', opts, { desc = 'Package: Change version' }))
    end,
  },
}

-- LSP configuration that will be registered with the LSP feature module
M.lsp_config = {
  -- TypeScript is handled by typescript-tools.nvim
  -- ESLint integration
  eslint = {
    settings = {
      codeAction = {
        disableRuleComment = {
          enable = true,
          location = 'separateLine'
        },
        showDocumentation = {
          enable = true
        }
      },
      codeActionOnSave = {
        enable = false,
        mode = 'all'
      },
      experimental = {
        useFlatConfig = false
      },
      format = true,
      nodePath = '',
      onIgnoredFiles = 'off',
      problems = {
        shortenToSingleLine = false
      },
      quiet = false,
      rulesCustomizations = {},
      run = 'onType',
      useESLintClass = false,
      validate = 'on',
      workingDirectory = {
        mode = 'location'
      }
    }
  },
}

-- Debug configuration for Node.js/TypeScript
M.debug_config = {
  adapters = {
    ['pwa-node'] = {
      type = 'server',
      host = 'localhost',
      port = '${port}',
      executable = {
        command = 'node',
        args = function()
          local ok, mason_registry = pcall(require, 'mason-registry')
          if ok and mason_registry.is_installed('js-debug-adapter') then
            return {
              mason_registry.get_package('js-debug-adapter'):get_install_path() .. '/js-debug/src/dapDebugServer.js',
              '${port}'
            }
          else
            return { 'js-debug-adapter', '${port}' }
          end
        end,
      }
    },
    ['pwa-chrome'] = {
      type = 'server',
      host = 'localhost',
      port = '${port}',
      executable = {
        command = 'node',
        args = function()
          local ok, mason_registry = pcall(require, 'mason-registry')
          if ok and mason_registry.is_installed('js-debug-adapter') then
            return {
              mason_registry.get_package('js-debug-adapter'):get_install_path() .. '/js-debug/src/dapDebugServer.js',
              '${port}'
            }
          else
            return { 'js-debug-adapter', '${port}' }
          end
        end,
      }
    },
  },
  configurations = {
    typescript = {
      {
        type = 'pwa-node',
        request = 'launch',
        name = 'Launch file',
        program = '${file}',
        cwd = '${workspaceFolder}',
        runtimeExecutable = 'node',
        runtimeArgs = { '--loader', 'ts-node/esm' },
      },
      {
        type = 'pwa-node',
        request = 'attach',
        name = 'Attach',
        processId = function()
          local ok, dap_utils = pcall(require, 'dap.utils')
          if ok then
            return dap_utils.pick_process()
          else
            return vim.fn.input('Process ID: ')
          end
        end,
        cwd = '${workspaceFolder}',
      },
      {
        type = 'pwa-node',
        request = 'launch',
        name = 'Debug Jest Tests',
        runtimeExecutable = 'node',
        runtimeArgs = {
          './node_modules/.bin/jest',
          '--runInBand',
        },
        rootPath = '${workspaceFolder}',
        cwd = '${workspaceFolder}',
        console = 'integratedTerminal',
        internalConsoleOptions = 'neverOpen',
      },
    },
    javascript = {
      {
        type = 'pwa-node',
        request = 'launch',
        name = 'Launch file',
        program = '${file}',
        cwd = '${workspaceFolder}',
      },
      {
        type = 'pwa-node',
        request = 'attach',
        name = 'Attach',
        processId = function()
          local ok, dap_utils = pcall(require, 'dap.utils')
          if ok then
            return dap_utils.pick_process()
          else
            return vim.fn.input('Process ID: ')
          end
        end,
        cwd = '${workspaceFolder}',
      },
      {
        type = 'pwa-chrome',
        request = 'launch',
        name = 'Start Chrome',
        url = 'http://localhost:3000',
        webRoot = '${workspaceFolder}',
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir'
      }
    },
    typescriptreact = {
      {
        type = 'pwa-chrome',
        request = 'launch',
        name = 'Start Chrome',
        url = 'http://localhost:3000',
        webRoot = '${workspaceFolder}',
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir'
      }
    },
    javascriptreact = {
      {
        type = 'pwa-chrome',
        request = 'launch',
        name = 'Start Chrome',
        url = 'http://localhost:3000',
        webRoot = '${workspaceFolder}',
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir'
      }
    },
  },
}

-- Setup function called by the module system
M.setup = function()
  -- File type detection for modern JS/TS files
  vim.filetype.add {
    extension = {
      ts = 'typescript',
      tsx = 'typescriptreact',
      js = 'javascript',
      jsx = 'javascriptreact',
      mjs = 'javascript',
      cjs = 'javascript',
      vue = 'vue',
    },
    filename = {
      ['.eslintrc.js'] = 'javascript',
      ['.eslintrc.cjs'] = 'javascript',
      ['tsconfig.json'] = 'jsonc',
      ['jsconfig.json'] = 'jsonc',
    },
    pattern = {
      ['tsconfig*.json'] = 'jsonc',
      ['.eslintrc.json'] = 'jsonc',
    },
  }

  -- TypeScript/JavaScript-specific autocommands
  local js_ts_group = vim.api.nvim_create_augroup('JSTSConfig', { clear = true })

  -- Auto-format on save (only if Prettier is available)
  vim.api.nvim_create_autocmd('BufWritePre', {
    group = js_ts_group,
    pattern = { '*.ts', '*.tsx', '*.js', '*.jsx', '*.vue' },
    callback = function()
      -- Only format if a formatter is available
      local clients = vim.lsp.get_active_clients()
      for _, client in ipairs(clients) do
        if client.supports_method('textDocument/formatting') then
          vim.lsp.buf.format { async = false }
          break
        end
      end
    end,
  })

  -- Set up TypeScript/JavaScript-specific options
  vim.api.nvim_create_autocmd('FileType', {
    group = js_ts_group,
    pattern = { 'typescript', 'typescriptreact', 'javascript', 'javascriptreact', 'vue' },
    callback = function()
      vim.opt_local.shiftwidth = 2
      vim.opt_local.tabstop = 2
      vim.opt_local.expandtab = true
      vim.opt_local.textwidth = 120
      vim.opt_local.colorcolumn = '120'

      -- Enable inlay hints for TypeScript files
      if vim.lsp.inlay_hint then
        vim.lsp.inlay_hint.enable(true)
      end
    end,
  })

  -- JSON files specific to JS/TS projects
  vim.api.nvim_create_autocmd('FileType', {
    group = js_ts_group,
    pattern = { 'json', 'jsonc' },
    callback = function()
      local filename = vim.fn.expand('%:t')
      if filename == 'package.json' or filename == 'tsconfig.json' or filename == 'jsconfig.json' then
        vim.opt_local.shiftwidth = 2
        vim.opt_local.tabstop = 2
        vim.opt_local.expandtab = true
      end
    end,
  })

  -- Custom TypeScript snippets
  vim.api.nvim_create_autocmd('FileType', {
    group = js_ts_group,
    pattern = { 'typescript', 'typescriptreact' },
    callback = function()
      -- Custom TypeScript snippets can be added here
      -- They will be loaded by LuaSnip if available
    end,
  })
end

return M