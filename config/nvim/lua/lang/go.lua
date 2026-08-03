-- Go language module - isolated and self-contained
-- Follows SRP: responsible only for Go-specific configuration
-- No dependencies on other language modules (dependency rule compliance)
-- Updated for Neovim 0.11+ native LSP configuration (vim.lsp.config)

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
    build = function()
      vim.fn.system({ 'python3', vim.fn.expand('$DOTFILES') .. '/bin/nvim-patch-plugins', 'nvim-dap-go' })
    end,
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
          build_flags = { '-tags', 'integration' },
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
    root_markers = { 'go.work', 'go.mod', '.git' },
    settings = {
      gopls = {
        -- Code completion
        completeUnimported = true,
        usePlaceholders = true,

        -- Analyses
        analyses = {
          unusedparams = true,
          unreachable = true,
          unusedwrite = true,
          nilness = true,    -- nil pointer dereference detection
          shadow = true,     -- variable shadowing detection
          stdversion = true, -- warns on stdlib APIs newer than go.mod go directive
          -- Suppress low-signal style checks for application code
          ST1000 = false,    -- package comment requirement (noisy on non-library code)
          QF1008 = false,    -- embedded field selector can be omitted (minor style)
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

        -- Inlay hints
        hints = {
          assignVariableTypes = true,
          compositeLiteralFields = true,
          compositeLiteralTypes = true,
          constantValues = true,
          functionTypeParameters = true,
          parameterNames = true,
          rangeVariableTypes = true,
        },
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
  map('n', '<leader>gfw', '<cmd>GoFillSwitch<cr>', vim.tbl_extend('force', opts, { desc = 'Go fill switch' }))
  map('n', '<leader>gim', '<cmd>GoImpl<cr>', vim.tbl_extend('force', opts, { desc = 'Go implement interface' }))
  map('n', '<leader>gta', '<cmd>GoAddTags<cr>', vim.tbl_extend('force', opts, { desc = 'Go add struct tags' }))
  map('n', '<leader>gtr', '<cmd>GoRmTags<cr>', vim.tbl_extend('force', opts, { desc = 'Go remove struct tags' }))
  map('n', '<leader>gvu', '<cmd>GoVulnCheck<cr>', vim.tbl_extend('force', opts, { desc = 'Go vuln check' }))

  -- Alternate between foo.go and foo_test.go
  map('n', '<leader>go', '<cmd>GoAlt<cr>',  vim.tbl_extend('force', opts, { desc = 'Go alternate file' }))
  map('n', '<leader>gO', '<cmd>GoAltV<cr>', vim.tbl_extend('force', opts, { desc = 'Go alternate file (vsplit)' }))

  -- Run go generate and refresh buffers
  map('n', '<leader>gg', function()
    vim.cmd('GoGenerate')
    vim.defer_fn(function() vim.cmd('checktime') end, 500)
  end, vim.tbl_extend('force', opts, { desc = 'Go generate' }))

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

      -- Register Go which-key group (buffer-local)
      local wk_ok, wk = pcall(require, 'which-key')
      if wk_ok then
        wk.add({ { '<leader>g', group = 'Go', icon = '󰟓', buffer = event.buf } })
      end

      -- Auto-enable inlay hints for Go buffers
      vim.lsp.inlay_hint.enable(true, { bufnr = event.buf })

      -- Setup Go-specific keymaps for this buffer
      M.setup_keymaps(event.buf)

      -- Auto-format on save
      vim.api.nvim_create_autocmd('BufWritePre', {
        group = augroup,
        buffer = event.buf,
        callback = function()
          -- organizeImports via gopls code action (Neovim 0.11+ API)
          local params = vim.lsp.util.make_range_params(0, 'utf-8')
          params.context = { only = { 'source.organizeImports' } }
          local result = vim.lsp.buf_request_sync(0, 'textDocument/codeAction', params, 3000)
          for _, res in pairs(result or {}) do
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

  -- Code generation (required by go.nvim commands)
  'impl',
  'gomodifytags',
  'gotests',
  'govulncheck',

  -- Documentation
  'godoc',
}

-- Initialize the Go module
M.setup = function()
  -- Setup autocommands for Go files
  M.setup_autocmds()

  -- Get default capabilities from main LSP config
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local ok, cmp_nvim_lsp = pcall(require, 'cmp_nvim_lsp')
  if ok then
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  end

  -- Configure and enable gopls using native Neovim 0.11+ API
  if M.lsp_config.gopls then
    local config = vim.tbl_deep_extend('force', M.lsp_config.gopls, { capabilities = capabilities })
    vim.lsp.config('gopls', config)
    vim.lsp.enable('gopls')
  end
end

return M