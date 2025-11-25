-- Go language module - isolated and self-contained
-- Follows SRP: responsible only for Go-specific configuration
-- No dependencies on other language modules (dependency rule compliance)

local M = {}

-- Go-specific plugin specifications
M.plugins = {
  {
    'ray-x/go.nvim',
    dependencies = { 'ray-x/guihua.lua', 'nvim-treesitter/nvim-treesitter' },
    ft = { 'go', 'gomod', 'gowork', 'gotmpl' },
    config = function()
      require('go').setup({
        -- Go tool configuration
        goimports = 'gopls',
        gofmt = 'gofumpt',
        max_line_len = 120,
        tag_transform = false,
        test_dir = '',
        comment_placeholder = '   ',
        lsp_cfg = false, -- Don't let go.nvim configure LSP (we handle it separately)
        lsp_gq = true,
        lsp_keymaps = false, -- We define our own keymaps

        -- Diagnostic configuration
        lsp_diag_hdlr = true,
        lsp_diag_underline = true,
        lsp_diag_virtual_text = { space = 0, prefix = '■' },
        lsp_diag_signs = true,
        lsp_diag_update_in_insert = false,

        -- Code actions and linters
        lsp_document_formatting = true,
        gopls_cmd = nil,
        gopls_remote_auto = true,
        dap_debug = true,
        dap_debug_keymap = false, -- We define our own debug keymaps
        dap_debug_gui = true,
        dap_debug_vt = true,

        -- Build and test configuration
        build_tags = '',
        textobjects = true,
        test_runner = 'go',
        verbose_tests = true,
        run_in_floaterm = false,

        -- Formatting and imports
        auto_format = true,
        auto_lint = false,

        -- Trouble integration
        trouble = true,
        luasnip = true,
      })
    end,
  },

  -- Delve debugger for Go
  {
    'leoluz/nvim-dap-go',
    ft = 'go',
    dependencies = { 'mfussenegger/nvim-dap' },
    config = function()
      require('dap-go').setup({
        dap_configurations = {
          {
            type = 'go',
            name = 'Attach remote',
            mode = 'remote',
            request = 'attach',
          },
        },
        delve = {
          path = 'dlv',
          initialize_timeout_sec = 20,
          port = '${port}',
          args = {},
          build_flags = '',
        },
      })
    end,
  },
}

-- Go-specific LSP configuration
M.lsp_config = {
  gopls = {
    cmd = { 'gopls' },
    filetypes = { 'go', 'gomod', 'gowork', 'gotmpl' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern('go.work', 'go.mod', '.git')(fname)
    end,
    settings = {
      gopls = {
        -- Code completion
        completeUnimported = true,
        usePlaceholders = true,

        -- Analyses
        analyses = {
          unusedparams = true,
          unreachable = true,
          fillstruct = true,
          nonewvars = true,
          undeclaredname = true,
          unusedwrite = true,
        },

        -- Code actions and codelenses
        codelenses = {
          gc_details = false,
          generate = true,
          regenerate_cgo = true,
          run_govulncheck = true,
          test = true,
          tidy = true,
          upgrade_dependency = true,
          vendor = true,
        },

        -- Formatting and imports
        gofumpt = true,
        staticcheck = true,

        -- Hover and documentation
        linksInHover = true,

        -- Semantic tokens (replaces deprecated noSemanticString/noSemanticNumber)
        semanticTokens = true,

        -- Build configuration
        buildFlags = { '-tags', 'integration' },
        env = {
          GOFLAGS = '-tags=integration',
        },

        -- Experimental features
        experimentalPostfixCompletions = true,
      },
    },
    init_options = {
      usePlaceholders = true,
    },
  },
}

-- Go-specific keymaps (only active in Go buffers)
M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set

  -- Go-specific commands
  map('n', '<leader>gr', '<cmd>GoRun<cr>', vim.tbl_extend('force', opts, { desc = 'Go run' }))
  map('n', '<leader>gb', '<cmd>GoBuild<cr>', vim.tbl_extend('force', opts, { desc = 'Go build' }))
  map('n', '<leader>gt', '<cmd>GoTest<cr>', vim.tbl_extend('force', opts, { desc = 'Go test' }))
  map('n', '<leader>gT', '<cmd>GoTestFunc<cr>', vim.tbl_extend('force', opts, { desc = 'Go test function' }))
  map('n', '<leader>gf', '<cmd>GoTestFile<cr>', vim.tbl_extend('force', opts, { desc = 'Go test file' }))
  map('n', '<leader>gc', '<cmd>GoCoverage<cr>', vim.tbl_extend('force', opts, { desc = 'Go coverage' }))

  -- Code generation and refactoring
  map('n', '<leader>ga', '<cmd>GoAddTest<cr>', vim.tbl_extend('force', opts, { desc = 'Go add test' }))
  map('n', '<leader>gat', '<cmd>GoAddAllTest<cr>', vim.tbl_extend('force', opts, { desc = 'Go add all tests' }))
  map('n', '<leader>gie', '<cmd>GoIfErr<cr>', vim.tbl_extend('force', opts, { desc = 'Go if err' }))
  map('n', '<leader>gfs', '<cmd>GoFillStruct<cr>', vim.tbl_extend('force', opts, { desc = 'Go fill struct' }))
  map('n', '<leader>gfs', '<cmd>GoFillSwitch<cr>', vim.tbl_extend('force', opts, { desc = 'Go fill switch' }))

  -- Import management
  map('n', '<leader>gia', '<cmd>GoImport<cr>', vim.tbl_extend('force', opts, { desc = 'Go import add' }))
  map('n', '<leader>gid', '<cmd>GoImportDrop<cr>', vim.tbl_extend('force', opts, { desc = 'Go import drop' }))

  -- Documentation and inspection
  map('n', '<leader>gd', '<cmd>GoDoc<cr>', vim.tbl_extend('force', opts, { desc = 'Go doc' }))
  map('n', '<leader>gD', '<cmd>GoDocBrowser<cr>', vim.tbl_extend('force', opts, { desc = 'Go doc browser' }))

  -- Debugging
  map('n', '<leader>gdb', '<cmd>GoBreakToggle<cr>', vim.tbl_extend('force', opts, { desc = 'Go debug breakpoint' }))
  map('n', '<leader>gdd', '<cmd>GoDebug<cr>', vim.tbl_extend('force', opts, { desc = 'Go debug' }))
  map('n', '<leader>gdt', '<cmd>GoDebugTest<cr>', vim.tbl_extend('force', opts, { desc = 'Go debug test' }))

  -- Linting and formatting
  map('n', '<leader>gl', '<cmd>GoLint<cr>', vim.tbl_extend('force', opts, { desc = 'Go lint' }))
  map('n', '<leader>gv', '<cmd>GoVet<cr>', vim.tbl_extend('force', opts, { desc = 'Go vet' }))
  map('n', '<leader>gmt', '<cmd>GoModTidy<cr>', vim.tbl_extend('force', opts, { desc = 'Go mod tidy' }))
end

-- Go-specific autocommands
M.setup_autocmds = function()
  local augroup = vim.api.nvim_create_augroup('GoConfig', { clear = true })

  -- Go filetype settings and keymaps
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = { 'go', 'gomod', 'gowork', 'gotmpl' },
    callback = function(event)
      -- Go-specific editor settings
      vim.opt_local.expandtab = false
      vim.opt_local.tabstop = 4
      vim.opt_local.shiftwidth = 4
      vim.opt_local.softtabstop = 4

      -- Setup Go-specific keymaps for this buffer
      M.setup_keymaps(event.buf)

      -- Auto-format on save
      vim.api.nvim_create_autocmd('BufWritePre', {
        group = augroup,
        buffer = event.buf,
        callback = function()
          local params = vim.lsp.util.make_range_params()
          params.context = { only = { 'source.organizeImports' } }
          local result = vim.lsp.buf_request_sync(0, 'textDocument/codeAction', params, 3000)
          for cid, res in pairs(result or {}) do
            for _, r in pairs(res.result or {}) do
              if r.edit then
                vim.lsp.util.apply_workspace_edit(r.edit, 'utf-8')
              end
            end
          end
          vim.lsp.buf.format()
        end,
      })
    end,
  })

  -- Go test output highlighting
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = 'go',
    callback = function()
      -- Highlight test output
      vim.api.nvim_set_hl(0, 'GoTestSuccess', { fg = '#50fa7b' })
      vim.api.nvim_set_hl(0, 'GoTestFail', { fg = '#ff5555' })
    end,
  })
end

-- Tool requirements for Go development
M.required_tools = {
  -- LSP server
  'gopls',

  -- Formatters
  'gofumpt',
  'goimports',

  -- Linters
  'golangci-lint',
  'staticcheck',

  -- Debugger
  'delve',

  -- Test tools
  'gotestsum',

  -- Documentation
  'godoc',
}

-- Initialize the Go module
M.setup = function()
  -- Setup autocommands for Go files
  M.setup_autocmds()

  -- Register Go LSP configuration
  local lspconfig = require('lspconfig')
  if lspconfig.gopls and M.lsp_config.gopls then
    -- Get default capabilities from main LSP config
    local capabilities = vim.lsp.protocol.make_client_capabilities()
    local cmp_nvim_lsp = require('cmp_nvim_lsp')
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())

    -- Setup gopls with our configuration
    local config = vim.tbl_deep_extend('force', M.lsp_config.gopls, { capabilities = capabilities })
    lspconfig.gopls.setup(config)
  end
end

return M