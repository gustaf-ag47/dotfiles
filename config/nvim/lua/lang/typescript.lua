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
          vim.keymap.set('n', '<leader>to', '<cmd>TSToolsOrganizeImports<cr>', vim.tbl_extend('force', opts, { desc = 'Organize imports' }))
          vim.keymap.set('n', '<leader>ts', '<cmd>TSToolsSortImports<cr>', vim.tbl_extend('force', opts, { desc = 'Sort imports' }))
          vim.keymap.set('n', '<leader>tr', '<cmd>TSToolsRemoveUnused<cr>', vim.tbl_extend('force', opts, { desc = 'Remove unused' }))
          vim.keymap.set('n', '<leader>tf', '<cmd>TSToolsFixAll<cr>', vim.tbl_extend('force', opts, { desc = 'Fix all' }))
          vim.keymap.set('n', '<leader>ta', '<cmd>TSToolsAddMissingImports<cr>', vim.tbl_extend('force', opts, { desc = 'Add missing imports' }))
          vim.keymap.set('n', '<leader>td', '<cmd>TSToolsGoToSourceDefinition<cr>', vim.tbl_extend('force', opts, { desc = 'Source definition' }))
          vim.keymap.set('n', '<leader>th', '<cmd>TSToolsFileReferences<cr>', vim.tbl_extend('force', opts, { desc = 'File references' }))
          vim.keymap.set('n', '<leader>tR', '<cmd>TSToolsRenameFile<cr>', vim.tbl_extend('force', opts, { desc = 'Rename file + imports' }))

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
      local pkg = require 'package-info'
      pkg.setup {
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

      -- Package.json keymaps (buffer-local for package.json only)
      vim.api.nvim_create_autocmd('BufRead', {
        group = vim.api.nvim_create_augroup('PackageInfoKeymaps', { clear = true }),
        pattern = 'package.json',
        callback = function(event)
          local opts = { buffer = event.buf, silent = true }
          vim.keymap.set('n', '<leader>ns', pkg.show, vim.tbl_extend('force', opts, { desc = 'Package: Show info' }))
          vim.keymap.set('n', '<leader>nc', pkg.hide, vim.tbl_extend('force', opts, { desc = 'Package: Hide info' }))
          vim.keymap.set('n', '<leader>nt', pkg.toggle, vim.tbl_extend('force', opts, { desc = 'Package: Toggle info' }))
          vim.keymap.set('n', '<leader>nu', pkg.update, vim.tbl_extend('force', opts, { desc = 'Package: Update' }))
          vim.keymap.set('n', '<leader>nd', pkg.delete, vim.tbl_extend('force', opts, { desc = 'Package: Delete' }))
          vim.keymap.set('n', '<leader>ni', pkg.install, vim.tbl_extend('force', opts, { desc = 'Package: Install' }))
          vim.keymap.set('n', '<leader>np', pkg.change_version, vim.tbl_extend('force', opts, { desc = 'Package: Change version' }))
        end,
      })
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
          location = 'separateLine',
        },
        showDocumentation = {
          enable = true,
        },
      },
      codeActionOnSave = {
        enable = false,
        mode = 'all',
      },
      experimental = {
        useFlatConfig = false,
      },
      format = true,
      nodePath = '',
      onIgnoredFiles = 'off',
      problems = {
        shortenToSingleLine = false,
      },
      quiet = false,
      rulesCustomizations = {},
      run = 'onType',
      useESLintClass = false,
      validate = 'on',
      workingDirectory = {
        mode = 'location',
      },
    },
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
          if ok and mason_registry.is_installed 'js-debug-adapter' then
            return {
              mason_registry.get_package('js-debug-adapter'):get_install_path() .. '/js-debug/src/dapDebugServer.js',
              '${port}',
            }
          else
            return { 'js-debug-adapter', '${port}' }
          end
        end,
      },
    },
    ['pwa-chrome'] = {
      type = 'server',
      host = 'localhost',
      port = '${port}',
      executable = {
        command = 'node',
        args = function()
          local ok, mason_registry = pcall(require, 'mason-registry')
          if ok and mason_registry.is_installed 'js-debug-adapter' then
            return {
              mason_registry.get_package('js-debug-adapter'):get_install_path() .. '/js-debug/src/dapDebugServer.js',
              '${port}',
            }
          else
            return { 'js-debug-adapter', '${port}' }
          end
        end,
      },
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
            return vim.fn.input 'Process ID: '
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
            return vim.fn.input 'Process ID: '
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
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir',
      },
    },
    typescriptreact = {
      {
        type = 'pwa-chrome',
        request = 'launch',
        name = 'Start Chrome',
        url = 'http://localhost:3000',
        webRoot = '${workspaceFolder}',
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir',
      },
    },
    javascriptreact = {
      {
        type = 'pwa-chrome',
        request = 'launch',
        name = 'Start Chrome',
        url = 'http://localhost:3000',
        webRoot = '${workspaceFolder}',
        userDataDir = '${workspaceFolder}/.vscode/vscode-chrome-debug-userdatadir',
      },
    },
  },
}

-- TypeScript-specific keymaps (only active in TS/JS buffers)
-- NOTE: Most keymaps are set in typescript-tools.nvim's on_attach
M.setup_keymaps = function(bufnr)
  -- Additional keymaps if needed can be added here
  -- typescript-tools.nvim handles most keymaps in its on_attach
end

-- TypeScript/JavaScript-specific autocommands
M.setup_autocmds = function()
  local js_ts_group = vim.api.nvim_create_augroup('JSTSConfig', { clear = true })

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

  -- Auto-format on save (only if formatter is available)
  vim.api.nvim_create_autocmd('BufWritePre', {
    group = js_ts_group,
    pattern = { '*.ts', '*.tsx', '*.js', '*.jsx', '*.vue' },
    callback = function()
      -- Only format if a formatter is available
      local clients = vim.lsp.get_clients()
      for _, client in ipairs(clients) do
        if client:supports_method 'textDocument/formatting' then
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
    callback = function(event)
      vim.opt_local.shiftwidth = 2
      vim.opt_local.tabstop = 2
      vim.opt_local.expandtab = true
      vim.opt_local.textwidth = 120
      vim.opt_local.colorcolumn = '120'

      -- Enable inlay hints for TypeScript files
      if vim.lsp.inlay_hint then
        vim.lsp.inlay_hint.enable(true)
      end

      -- Register TypeScript which-key groups (buffer-local)
      local wk_ok, wk = pcall(require, 'which-key')
      if wk_ok then
        wk.add {
          { '<leader>t', group = 'TypeScript', icon = '', buffer = event.buf },
          { '<leader>n', group = 'NPM Package', icon = '', buffer = event.buf },
        }
      end

      -- Setup TS/JS-specific keymaps for this buffer
      M.setup_keymaps(event.buf)
    end,
  })

  -- JSON files specific to JS/TS projects
  vim.api.nvim_create_autocmd('FileType', {
    group = js_ts_group,
    pattern = { 'json', 'jsonc' },
    callback = function()
      local filename = vim.fn.expand '%:t'
      if filename == 'package.json' or filename == 'tsconfig.json' or filename == 'jsconfig.json' then
        vim.opt_local.shiftwidth = 2
        vim.opt_local.tabstop = 2
        vim.opt_local.expandtab = true
      end
    end,
  })
end

-- Setup function called by the module system
M.setup = function()
  -- Setup autocommands for TS/JS files
  M.setup_autocmds()
end

return M
