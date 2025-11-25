-- SQL language module - isolated and self-contained
-- Follows SRP: responsible only for SQL-specific configuration
-- NO dependencies on other language modules (strict dependency rule compliance)
-- Can only depend on: core modules, feature modules, utils modules

local M = {}

-- SQL-specific plugin specifications
M.plugins = {
  -- SQL LSP and enhanced support
  {
    'nanotee/sqls.nvim',
    ft = { 'sql', 'mysql', 'plsql' },
    dependencies = {
      'neovim/nvim-lspconfig',
    },
    config = function()
      -- Configuration will be handled in setup()
    end,
  },

  -- Database interface and REPL
  {
    'tpope/vim-dadbod',
    ft = { 'sql', 'mysql', 'plsql' },
    cmd = { 'DB', 'DBUI' },
  },

  -- Database UI
  {
    'kristijanhusak/vim-dadbod-ui',
    ft = { 'sql', 'mysql', 'plsql' },
    cmd = { 'DBUI', 'DBUIToggle', 'DBUIAddConnection' },
    dependencies = { 'tpope/vim-dadbod' },
    config = function()
      -- Configuration will be handled in setup()
    end,
  },

  -- Database completion
  {
    'kristijanhusak/vim-dadbod-completion',
    ft = { 'sql', 'mysql', 'plsql' },
    dependencies = {
      'tpope/vim-dadbod',
      'hrsh7th/nvim-cmp',
    },
    config = function()
      -- Configuration will be handled in setup()
    end,
  },

  -- SQL formatting
  {
    'joereynolds/SQHell.vim',
    ft = { 'sql', 'mysql', 'plsql' },
    cmd = { 'SQHellExecute', 'SQHellExecuteFile' },
  },

  -- Enhanced SQL syntax
  {
    'shmup/vim-sql-syntax',
    ft = { 'sql', 'mysql', 'plsql' },
  },
}

-- SQL-specific LSP configuration
M.lsp_config = {
  sqls = {
    cmd = { 'sqls' },
    filetypes = { 'sql', 'mysql' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern('.sqls.yml', '.git')(fname) or util.path.dirname(fname)
    end,
    settings = {
      sqls = {
        connections = {
          -- Example connection configurations
          -- Users should override these in their local config
          {
            driver = 'mysql',
            dataSourceName = 'root:password@tcp(127.0.0.1:3306)/database_name',
            alias = 'local_mysql',
          },
          {
            driver = 'postgresql',
            dataSourceName = 'host=127.0.0.1 port=5432 user=postgres password=password dbname=database_name sslmode=disable',
            alias = 'local_postgres',
          },
          {
            driver = 'sqlite3',
            dataSourceName = './database.db',
            alias = 'local_sqlite',
          },
        },
      },
    },
    on_attach = function(client, bufnr)
      -- SQL-specific LSP attach behavior
      require('sqls').on_attach(client, bufnr)
    end,
    capabilities = {},
  },

  -- Alternative: sqlls (SQL Language Server)
  sqlls = {
    cmd = { 'sql-language-server', 'up', '--method', 'stdio' },
    filetypes = { 'sql', 'mysql' },
    root_dir = function(fname)
      local util = require('lspconfig.util')
      return util.root_pattern('.git')(fname) or util.path.dirname(fname)
    end,
    settings = {},
  },
}

-- SQL-specific keymaps (only active in SQL buffers)
M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set

  -- Database operations
  map('n', '<leader>e', '<cmd>DBUIToggle<cr>', vim.tbl_extend('force', opts, { desc = 'Toggle database UI' }))
  map('n', '<leader>dB', '<cmd>DBUIAddConnection<cr>', vim.tbl_extend('force', opts, { desc = 'Add database connection' }))
  map('n', '<leader>df', '<cmd>DBUIFindBuffer<cr>', vim.tbl_extend('force', opts, { desc = 'Find database buffer' }))
  map('n', '<leader>dr', '<cmd>DBUIRenameBuffer<cr>', vim.tbl_extend('force', opts, { desc = 'Rename database buffer' }))
  map('n', '<leader>dl', '<cmd>DBUILastQueryInfo<cr>', vim.tbl_extend('force', opts, { desc = 'Last query info' }))

  -- Query execution
  map('n', '<leader>se', '<cmd>DB<cr>', vim.tbl_extend('force', opts, { desc = 'Execute SQL query' }))
  map('v', '<leader>se', ':DB<cr>', vim.tbl_extend('force', opts, { desc = 'Execute selected SQL' }))
  map('n', '<leader>sE', '<cmd>%DB<cr>', vim.tbl_extend('force', opts, { desc = 'Execute entire file' }))
  map('n', '<leader>sr', function()
    vim.cmd('DB ' .. vim.fn.getline('.'))
  end, vim.tbl_extend('force', opts, { desc = 'Execute current line' }))

  -- Query building helpers
  map('n', '<leader>ss', function()
    local table_name = vim.fn.input('Table name: ')
    if table_name ~= '' then
      vim.api.nvim_put({ 'SELECT * FROM ' .. table_name .. ';' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert SELECT statement' }))

  map('n', '<leader>si', function()
    local table_name = vim.fn.input('Table name: ')
    if table_name ~= '' then
      vim.api.nvim_put({ 'INSERT INTO ' .. table_name .. ' () VALUES ();' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert INSERT statement' }))

  map('n', '<leader>su', function()
    local table_name = vim.fn.input('Table name: ')
    if table_name ~= '' then
      vim.api.nvim_put({ 'UPDATE ' .. table_name .. ' SET  WHERE ;' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert UPDATE statement' }))

  map('n', '<leader>sd', function()
    local table_name = vim.fn.input('Table name: ')
    if table_name ~= '' then
      vim.api.nvim_put({ 'DELETE FROM ' .. table_name .. ' WHERE ;' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert DELETE statement' }))

  -- Schema operations
  map('n', '<leader>st', function()
    local table_name = vim.fn.input('Table name: ')
    if table_name ~= '' then
      vim.api.nvim_put({ 'DESCRIBE ' .. table_name .. ';' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Describe table' }))

  map('n', '<leader>sT', '<cmd>lua require("sqls").show_databases()<cr>', vim.tbl_extend('force', opts, { desc = 'Show databases' }))
  map('n', '<leader>sc', '<cmd>lua require("sqls").show_connections()<cr>', vim.tbl_extend('force', opts, { desc = 'Show connections' }))
  map('n', '<leader>sS', '<cmd>SQLShowSchema<cr>', vim.tbl_extend('force', opts, { desc = 'Show database schema' }))

  -- Intelligent completion controls
  map('n', '<leader>sR', '<cmd>SQLRefreshSchema<cr>', vim.tbl_extend('force', opts, { desc = 'Refresh schema cache' }))
  map('n', '<leader>sC', '<cmd>lua require("cmp").complete()<cr>', vim.tbl_extend('force', opts, { desc = 'Trigger completion' }))

  -- Formatting
  map('n', '<leader>sf', function()
    -- Simple SQL formatting (you can integrate with external formatters)
    vim.cmd('normal! gg=G')
  end, vim.tbl_extend('force', opts, { desc = 'Format SQL' }))

  map('v', '<leader>sf', '=', vim.tbl_extend('force', opts, { desc = 'Format selected SQL' }))

  -- Comments
  map('n', '<leader>s/', 'I-- <Esc>', vim.tbl_extend('force', opts, { desc = 'Comment line' }))
  map('v', '<leader>s/', ':s/^/-- /<cr>:nohl<cr>', vim.tbl_extend('force', opts, { desc = 'Comment selection' }))

  -- SQL Hell operations (if available)
  map('n', '<leader>sh', '<cmd>SQHellExecute<cr>', vim.tbl_extend('force', opts, { desc = 'Execute with SQHell' }))
  map('n', '<leader>sH', '<cmd>SQHellExecuteFile<cr>', vim.tbl_extend('force', opts, { desc = 'Execute file with SQHell' }))

  -- Snippets and templates
  map('n', '<leader>sp', function()
    local proc_name = vim.fn.input('Procedure name: ')
    if proc_name ~= '' then
      local lines = {
        'DELIMITER //',
        'CREATE PROCEDURE ' .. proc_name .. '()',
        'BEGIN',
        '    -- Procedure body here',
        'END//',
        'DELIMITER ;',
      }
      vim.api.nvim_put(lines, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Create stored procedure template' }))

  map('n', '<leader>sv', function()
    local view_name = vim.fn.input('View name: ')
    if view_name ~= '' then
      local lines = {
        'CREATE VIEW ' .. view_name .. ' AS',
        'SELECT ',
        'FROM ;',
      }
      vim.api.nvim_put(lines, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Create view template' }))
end

-- SQL-specific autocommands
M.setup_autocmds = function()
  local augroup = vim.api.nvim_create_augroup('SQLConfig', { clear = true })

  -- SQL filetype settings and keymaps
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = { 'sql', 'mysql', 'plsql' },
    callback = function(event)
      -- SQL-specific editor settings
      vim.opt_local.expandtab = true
      vim.opt_local.tabstop = 2
      vim.opt_local.shiftwidth = 2
      vim.opt_local.softtabstop = 2
      vim.opt_local.commentstring = '-- %s'

      -- Setup SQL-specific keymaps for this buffer
      M.setup_keymaps(event.buf)

      -- Set up completion for dadbod
      if pcall(require, 'cmp') then
        require('cmp').setup.buffer({
          sources = {
            { name = 'vim-dadbod-completion' },
            { name = 'buffer' },
          },
        })
      end
    end,
  })

  -- Auto-detect SQL file types
  vim.api.nvim_create_autocmd({ 'BufRead', 'BufNewFile' }, {
    group = augroup,
    pattern = { '*.sql', '*.ddl', '*.dml', '*.mysql', '*.pgsql', '*.plsql' },
    callback = function()
      vim.bo.filetype = 'sql'
    end,
  })

  -- SQL syntax highlighting enhancements
  vim.api.nvim_create_autocmd('FileType', {
    group = augroup,
    pattern = 'sql',
    callback = function()
      -- Enhanced SQL keywords highlighting
      vim.api.nvim_set_hl(0, 'sqlKeyword', { fg = '#569cd6', bold = true })
      vim.api.nvim_set_hl(0, 'sqlFunction', { fg = '#dcdcaa' })
      vim.api.nvim_set_hl(0, 'sqlString', { fg = '#ce9178' })
      vim.api.nvim_set_hl(0, 'sqlComment', { fg = '#6a9955', italic = true })
    end,
  })

  -- Database connection helpers
  vim.api.nvim_create_autocmd('VimEnter', {
    group = augroup,
    callback = function()
      -- Auto-load database connections from environment or config files
      M.load_database_connections()
    end,
  })
end

-- Load database connections from various sources
M.load_database_connections = function()
  -- Try to load from .env file
  local env_file = vim.fn.getcwd() .. '/.env'
  if vim.fn.filereadable(env_file) == 1 then
    -- Parse .env file for database URLs
    -- This is a simplified example - you'd want more robust parsing
    local lines = vim.fn.readfile(env_file)
    for _, line in ipairs(lines) do
      if line:match('^DATABASE_URL=') then
        local url = line:match('DATABASE_URL=(.+)')
        -- Add to dadbod connections
        vim.g.dbs = vim.g.dbs or {}
        vim.g.dbs.default = url
      end
    end
  end

  -- SQLS will automatically pick up .sqls.yml from current directory if present
end

-- Tool requirements for SQL development
M.required_tools = {
  -- LSP server
  'sqls',
  -- 'sql-language-server', -- Alternative

  -- Formatters
  'sqlfluff',
  'pg_format',

  -- Linters
  'sqlfluff',

  -- Database clients (optional)
  'mysql',
  'postgresql',
  'sqlite3',

  -- Database tools
  'redis-cli',
  'mongosh',
}

-- Setup database UI
M.setup_dadbod_ui = function()
  -- Database UI configuration
  vim.g.db_ui_use_nerd_fonts = 1
  vim.g.db_ui_winwidth = 30
  vim.g.db_ui_notification_width = 50

  -- Default database connections (users should override)
  vim.g.dbs = {
    dev = 'postgresql://localhost:5432/myapp_dev',
    test = 'postgresql://localhost:5432/myapp_test',
    staging = 'postgresql://localhost:5432/myapp_staging',
  }

  -- Auto-execute SQL files
  vim.g.db_ui_auto_execute_table_helpers = 1

  -- Save query history
  vim.g.db_ui_save_location = vim.fn.stdpath('data') .. '/db_ui_queries'

  -- Show database schemas in tree
  vim.g.db_ui_show_database_icon = 1
  vim.g.db_ui_force_echo_messages = 1

  -- Custom icons
  vim.g.db_ui_icons = {
    expanded = '▾',
    collapsed = '▸',
    saved_query = '*',
    new_query = '+',
    tables = '~',
    buffers = '»',
    add_connection = '[+]',
    connection_ok = '✓',
    connection_error = '✕',
  }
end

-- Setup intelligent completion
M.setup_completion = function()
  -- Setup intelligent SQL completion that analyzes actual database schema
  local sql_completion = require('features.sql_completion')
  sql_completion.setup()

  -- Enhanced completion for SQL files
  vim.api.nvim_create_autocmd('FileType', {
    pattern = { 'sql', 'mysql', 'plsql' },
    callback = function()
      require('cmp').setup.buffer({
        sources = {
          { name = 'sql_dadbod', priority = 1000 },        -- Intelligent schema-aware completion
          { name = 'vim-dadbod-completion', priority = 800 }, -- Fallback dadbod completion
          { name = 'buffer', priority = 500 },
          { name = 'path', priority = 300 },
        },
        completion = {
          -- More aggressive completion for SQL
          keyword_length = 1,
          autocomplete = {
            require('cmp.types').cmp.TriggerEvent.TextChanged,
            require('cmp.types').cmp.TriggerEvent.InsertEnter,
          }
        },
        experimental = {
          ghost_text = true,
        }
      })
    end,
  })
end

-- Initialize the SQL module
M.setup = function()
  -- Setup autocommands for SQL files
  M.setup_autocmds()

  -- Setup database UI
  M.setup_dadbod_ui()

  -- Setup completion
  if pcall(require, 'cmp') then
    M.setup_completion()
  end

  -- Register SQL LSP configuration (default to sqls)
  local lspconfig = require('lspconfig')
  if lspconfig.sqls and M.lsp_config.sqls then
    -- Get default capabilities from main LSP config
    local capabilities = vim.lsp.protocol.make_client_capabilities()
    local cmp_nvim_lsp = require('cmp_nvim_lsp')
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())

    -- Setup sqls with our configuration
    local config = vim.tbl_deep_extend('force', M.lsp_config.sqls, { capabilities = capabilities })
    lspconfig.sqls.setup(config)
  end

  -- Create user commands for SQL operations
  M.create_user_commands()
end

-- Create user commands for SQL operations
M.create_user_commands = function()
  -- Database connection commands
  vim.api.nvim_create_user_command('SQLConnect', function(opts)
    local connection_string = opts.args
    if connection_string == '' then
      connection_string = vim.fn.input('Database connection string: ')
    end
    vim.g.db = connection_string
    print('Connected to: ' .. connection_string)
  end, { nargs = '?', desc = 'Connect to database' })

  -- Quick query execution
  vim.api.nvim_create_user_command('SQLExecute', function(opts)
    local query = opts.args
    if query == '' then
      query = vim.fn.input('SQL Query: ')
    end
    vim.cmd('DB ' .. query)
  end, { nargs = '?', desc = 'Execute SQL query' })

  -- Show database schema
  vim.api.nvim_create_user_command('SQLSchema', function()
    vim.cmd('DB SHOW TABLES;')
  end, { desc = 'Show database schema' })

  -- Format SQL buffer
  vim.api.nvim_create_user_command('SQLFormat', function()
    -- Simple formatting - could integrate with external tools
    vim.cmd('normal! gg=G')
  end, { desc = 'Format SQL buffer' })
end

return M