-- Python language module - isolated and self-contained
-- Follows SRP: responsible only for Python-specific configuration
-- NO dependencies on other language modules (strict dependency rule compliance)
-- Can only depend on: core modules, feature modules, utils modules

local M = {}

-- Python-specific plugin specifications
M.plugins = {
  -- Enhanced Python support
  {
    'python-lsp/python-lsp-server',
    ft = 'python',
    dependencies = {
      'neovim/nvim-lspconfig',
    },
  },
  
  -- Python debugging
  {
    'mfussenegger/nvim-dap-python',
    ft = 'python',
    dependencies = { 'mfussenegger/nvim-dap' },
    config = function()
      -- Configuration will be handled in setup()
    end,
  },
  
  -- Python virtual environment support
  {
    'linux-cultist/venv-selector.nvim',
    ft = 'python',
    branch = 'regexp',
    dependencies = {
      'neovim/nvim-lspconfig',
      'nvim-telescope/telescope.nvim',
      'mfussenegger/nvim-dap-python',
    },
    config = function()
      -- Configuration will be handled in setup()
    end,
  },
  
  -- Enhanced Python syntax and indentation
  {
    'Vimjas/vim-python-pep8-indent',
    ft = 'python',
  },
  
  -- Python text objects
  {
    'jeetsukumaran/vim-pythonsense',
    ft = 'python',
  },
}

-- Python-specific LSP configuration
M.lsp_config = {
  -- Ruff LSP for fast linting and formatting (new version)
  ruff = {
    cmd = { 'ruff', 'server', '--preview' },
    filetypes = { 'python' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern(
        'pyproject.toml',
        'ruff.toml',
        '.ruff.toml',
        'setup.py',
        'setup.cfg',
        'requirements.txt',
        'Pipfile',
        '.git'
      )(fname)
    end,
    init_options = {
      settings = {
        -- Ruff configuration
        args = {
          '--extend-select=I', -- Enable import sorting
        },
      }
    },
    single_file_support = true,
  },
  
  pyright = {
    cmd = { 'pyright-langserver', '--stdio' },
    filetypes = { 'python' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern(
        'pyproject.toml',
        'setup.py',
        'setup.cfg',
        'requirements.txt',
        'Pipfile',
        '.git'
      )(fname)
    end,
    settings = {
      python = {
        analysis = {
          -- Type checking mode
          typeCheckingMode = 'basic', -- 'off', 'basic', 'strict'
          
          -- Auto-import completions
          autoImportCompletions = true,
          
          -- Diagnostic settings
          diagnosticMode = 'workspace', -- 'openFilesOnly', 'workspace'
          
          -- Auto search paths
          autoSearchPaths = true,
          
          -- Use library code for types
          useLibraryCodeForTypes = true,
          
          -- Diagnostic severity overrides
          diagnosticSeverityOverrides = {
            reportUnusedImport = 'information',
            reportUnusedClass = 'information',
            reportUnusedFunction = 'information',
            reportUnusedVariable = 'information',
            reportDuplicateImport = 'warning',
            reportPrivateUsage = 'warning',
            reportConstantRedefinition = 'error',
            reportIncompatibleMethodOverride = 'error',
            reportMissingImports = 'error',
            reportUndefinedVariable = 'error',
          },
          
          -- Stub path
          stubPath = vim.fn.stdpath('data') .. '/lazy/python-type-stubs',
          
          -- Extra paths for analysis
          extraPaths = {},
        },
        
        -- Linting configuration
        linting = {
          enabled = true,
          pylintEnabled = false, -- We'll use external tools
          flake8Enabled = false, -- We'll use external tools
          mypyEnabled = false,   -- We'll use external tools
        },
        
        -- Formatting configuration  
        formatting = {
          provider = 'ruff',
        },
        
        -- Virtual environment detection
        defaultInterpreterPath = './venv/bin/python',
        venvPath = '.',
      },
    },
    single_file_support = true,
  },
  
  -- Alternative: pylsp (Python LSP Server)
  pylsp = {
    cmd = { 'pylsp' },
    filetypes = { 'python' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern(
        'pyproject.toml',
        'setup.py',
        'setup.cfg',
        'requirements.txt',
        'Pipfile',
        '.git'
      )(fname)
    end,
    settings = {
      pylsp = {
        plugins = {
          -- Code completion
          jedi_completion = {
            enabled = true,
            include_params = true,
            include_class_objects = true,
            fuzzy = true,
          },
          
          -- Jedi definition
          jedi_definition = { enabled = true },
          jedi_hover = { enabled = true },
          jedi_references = { enabled = true },
          jedi_signature_help = { enabled = true },
          jedi_symbols = { enabled = true, all_scopes = true },
          
          -- Linting
          pycodestyle = {
            enabled = false, -- We'll use external linters
            maxLineLength = 88,
          },
          pyflakes = { enabled = false },
          pylint = { enabled = false },
          mccabe = { enabled = false },
          
          -- Formatting
          black = { enabled = false },
          autopep8 = { enabled = false },
          yapf = { enabled = false },
          ruff = { enabled = true },
          
          -- Import sorting (handled by ruff)
          pyls_isort = { enabled = false },
          
          -- Rope for refactoring
          rope_completion = { enabled = true },
          rope_autoimport = { enabled = true },
        },
      },
    },
    single_file_support = true,
  },
}

-- Python debugging configuration
M.debug_config = {
  adapters = {
    python = {
      type = 'executable',
      command = 'python',
      args = { '-m', 'debugpy.adapter' },
    },
  },
  configurations = {
    python = {
      {
        type = 'python',
        request = 'launch',
        name = 'Launch Python file',
        program = '${file}',
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
      {
        type = 'python',
        request = 'launch',
        name = 'Launch Python module',
        module = '${workspaceFolder}',
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
      {
        type = 'python',
        request = 'attach',
        name = 'Attach to process',
        processId = function()
          return require('dap.utils').pick_process()
        end,
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
      {
        type = 'python',
        request = 'launch',
        name = 'Run Django',
        program = '${workspaceFolder}/manage.py',
        args = { 'runserver' },
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
      {
        type = 'python',
        request = 'launch',
        name = 'Run Flask',
        program = '${workspaceFolder}/app.py',
        env = {
          FLASK_ENV = 'development',
        },
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
      {
        type = 'python',
        request = 'launch',
        name = 'Run pytest',
        module = 'pytest',
        args = { '${workspaceFolder}' },
        pythonPath = function()
          local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
          if vim.fn.executable(venv_python) == 1 then
            return venv_python
          else
            return 'python'
          end
        end,
      },
    },
  },
}

-- Python-specific keymaps (only active in Python buffers)
M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set
  
  -- Python execution
  map('n', '<leader>pr', '<cmd>!python %<cr>', vim.tbl_extend('force', opts, { desc = 'Run Python file' }))
  map('n', '<leader>pR', function()
    local file = vim.fn.expand('%:p')
    vim.cmd('split | terminal python ' .. file)
  end, vim.tbl_extend('force', opts, { desc = 'Run Python file in terminal' }))
  
  -- Virtual environment
  map('n', '<leader>pv', '<cmd>VenvSelect<cr>', vim.tbl_extend('force', opts, { desc = 'Select Python venv' }))
  map('n', '<leader>pV', '<cmd>VenvSelectCached<cr>', vim.tbl_extend('force', opts, { desc = 'Select cached venv' }))
  
  -- Testing
  map('n', '<leader>pt', function()
    vim.cmd('!python -m pytest ' .. vim.fn.expand('%:p'))
  end, vim.tbl_extend('force', opts, { desc = 'Run pytest on file' }))
  map('n', '<leader>pT', '<cmd>!python -m pytest<cr>', vim.tbl_extend('force', opts, { desc = 'Run all pytest' }))
  map('n', '<leader>pc', function()
    vim.cmd('!python -m pytest --cov=' .. vim.fn.expand('%:p:h'))
  end, vim.tbl_extend('force', opts, { desc = 'Run pytest with coverage' }))
  
  -- Formatting and linting with Ruff
  map('n', '<leader>pf', function()
    vim.cmd('!ruff format ' .. vim.fn.expand('%:p'))
    vim.cmd('edit!')
  end, vim.tbl_extend('force', opts, { desc = 'Format with ruff' }))
  map('n', '<leader>pi', function()
    vim.cmd('!ruff check --select I --fix ' .. vim.fn.expand('%:p'))
    vim.cmd('edit!')
  end, vim.tbl_extend('force', opts, { desc = 'Sort imports with ruff' }))
  map('n', '<leader>pl', '<cmd>!ruff check %<cr>', vim.tbl_extend('force', opts, { desc = 'Lint with ruff' }))
  map('n', '<leader>pL', '<cmd>!ruff check --fix %<cr>', vim.tbl_extend('force', opts, { desc = 'Lint and fix with ruff' }))
  map('n', '<leader>pm', '<cmd>!mypy %<cr>', vim.tbl_extend('force', opts, { desc = 'Type check with mypy' }))
  map('n', '<leader>pF', function()
    vim.cmd('!ruff format ' .. vim.fn.expand('%:p'))
    vim.cmd('!ruff check --fix ' .. vim.fn.expand('%:p'))
    vim.cmd('edit!')
  end, vim.tbl_extend('force', opts, { desc = 'Format and fix with ruff' }))
  
  -- REPL and interactive
  map('n', '<leader>pp', function()
    vim.cmd('split | terminal python')
  end, vim.tbl_extend('force', opts, { desc = 'Open Python REPL' }))
  map('n', '<leader>pI', function()
    vim.cmd('split | terminal ipython')
  end, vim.tbl_extend('force', opts, { desc = 'Open IPython' }))
  
  -- Package management
  map('n', '<leader>pP', '<cmd>!pip install -r requirements.txt<cr>', vim.tbl_extend('force', opts, { desc = 'Install requirements' }))
  map('n', '<leader>pF', '<cmd>!pip freeze > requirements.txt<cr>', vim.tbl_extend('force', opts, { desc = 'Freeze requirements' }))
  
  -- Django specific
  map('n', '<leader>pd', '<cmd>!python manage.py runserver<cr>', vim.tbl_extend('force', opts, { desc = 'Django runserver' }))
  map('n', '<leader>pM', '<cmd>!python manage.py migrate<cr>', vim.tbl_extend('force', opts, { desc = 'Django migrate' }))
  map('n', '<leader>ps', '<cmd>!python manage.py shell<cr>', vim.tbl_extend('force', opts, { desc = 'Django shell' }))
  
  -- Debugging
  map('n', '<leader>pdb', function()
    require('dap-python').test_method()
  end, vim.tbl_extend('force', opts, { desc = 'Debug Python test method' }))
  map('n', '<leader>pdm', function()
    require('dap-python').test_class()
  end, vim.tbl_extend('force', opts, { desc = 'Debug Python test class' }))
  map('n', '<leader>pds', function()
    require('dap-python').debug_selection()
  end, vim.tbl_extend('force', opts, { desc = 'Debug Python selection' }))
end

-- Python-specific autocommands
M.setup_autocmds = function()
  local augroup = vim.api.nvim_create_augroup('PythonConfig', { clear = true })
  
  -- Python filetype settings and keymaps
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = { 'python' },
    callback = function(event)
      -- Python-specific editor settings
      vim.opt_local.expandtab = true
      vim.opt_local.tabstop = 4
      vim.opt_local.shiftwidth = 4
      vim.opt_local.softtabstop = 4
      vim.opt_local.textwidth = 88
      vim.opt_local.colorcolumn = '88'
      
      -- Setup Python-specific keymaps for this buffer
      M.setup_keymaps(event.buf)
      
      -- Auto-format on save (optional)
      -- vim.api.nvim_create_autocmd('BufWritePre', {
      --   group = augroup,
      --   buffer = event.buf,
      --   callback = function()
      --     vim.lsp.buf.format()
      --   end,
      -- })
    end,
  })
  
  -- Detect Python virtual environments
  vim.api.nvim_create_autocmd({ 'VimEnter', 'DirChanged' }, {
    group = augroup,
    callback = function()
      -- Auto-detect common virtual environment paths
      local venv_paths = {
        './venv/bin/python',
        './env/bin/python',
        './.venv/bin/python',
        './venv/Scripts/python.exe', -- Windows
        './env/Scripts/python.exe',   -- Windows
      }
      
      for _, path in ipairs(venv_paths) do
        if vim.fn.executable(path) == 1 then
          vim.g.python3_host_prog = path
          break
        end
      end
    end,
  })
  
  -- Python docstring highlighting
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = 'python',
    callback = function()
      -- Highlight docstrings
      vim.api.nvim_set_hl(0, 'pythonDocstring', { fg = '#98be65', italic = true })
    end,
  })
end

-- Tool requirements for Python development
M.required_tools = {
  -- LSP server (choose one)
  'pyright',
  -- 'python-lsp-server',
  
  -- Modern formatter and linter (replaces black, isort, flake8)
  'ruff',
  
  -- Type checker
  'mypy',
  
  -- Debugger
  'debugpy',
  
  -- Testing
  'pytest',
  'pytest-cov',
  
  -- Virtual environment tools
  'virtualenv',
  'pipenv',
  'uv', -- Modern package manager
}

-- Setup Python debugging
M.setup_debugging = function()
  local dap_python = require('dap-python')
  
  -- Auto-detect Python interpreter
  local python_path = vim.fn.exepath('python')
  local venv_python = vim.fn.getcwd() .. '/venv/bin/python'
  
  if vim.fn.executable(venv_python) == 1 then
    python_path = venv_python
  end
  
  dap_python.setup(python_path)
  
  -- Custom test runner
  dap_python.test_runner = 'pytest'
end

-- Setup virtual environment selector
M.setup_venv_selector = function()
  require('venv-selector').setup({
    -- Auto-activate when entering Python projects
    auto_refresh = true,
    
    -- Search paths for virtual environments
    path = {
      './venv',
      './env',
      './.venv',
      '~/.virtualenvs',
      '~/.pyenv/versions',
    },
    
    -- Virtual environment names to look for
    name = { 'venv', 'env', '.venv' },
    
    -- Show virtual environment in statusline
    stay_on_this_version = false,
    
    -- DAP integration
    dap_enabled = true,
  })
end

-- Initialize the Python module
M.setup = function()
  -- Setup autocommands for Python files
  M.setup_autocmds()
  
  -- Setup debugging
  if pcall(require, 'dap-python') then
    M.setup_debugging()
  end
  
  -- Setup virtual environment selector
  if pcall(require, 'venv-selector') then
    M.setup_venv_selector()
  end
  
  -- Register Python LSP configuration
  local lspconfig = require('lspconfig')
  
  -- Get default capabilities from main LSP config
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local cmp_nvim_lsp = require('cmp_nvim_lsp')
  capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  
  -- Setup Ruff LSP for linting and formatting
  if lspconfig.ruff and M.lsp_config.ruff then
    local ruff_config = vim.tbl_deep_extend('force', M.lsp_config.ruff, { capabilities = capabilities })
    lspconfig.ruff.setup(ruff_config)
  end
  
  -- Setup Pyright for type checking
  if lspconfig.pyright and M.lsp_config.pyright then
    local pyright_config = vim.tbl_deep_extend('force', M.lsp_config.pyright, { capabilities = capabilities })
    lspconfig.pyright.setup(pyright_config)
  end
end

return M