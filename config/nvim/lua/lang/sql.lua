-- SQL language module - isolated and self-contained
-- Follows SRP: responsible only for SQL-specific configuration
-- NO dependencies on other language modules (strict dependency rule compliance)
-- Can only depend on: core modules, feature modules, utils modules
-- Updated for Neovim 0.11+ native LSP configuration (vim.lsp.config)

local M = {}

-- Helper function to find root by pattern
local function root_pattern(...)
  local patterns = { ... }
  return function(bufnr, on_dir)
    local fname = vim.api.nvim_buf_get_name(bufnr)
    local path = vim.fn.fnamemodify(fname, ':h')
    while path and path ~= '/' do
      for _, pattern in ipairs(patterns) do
        local target = path .. '/' .. pattern
        if vim.fn.isdirectory(target) == 1 or vim.fn.filereadable(target) == 1 then
          on_dir(path)
          return
        end
      end
      path = vim.fn.fnamemodify(path, ':h')
    end
    -- Fallback to file directory
    on_dir(vim.fn.fnamemodify(fname, ':h'))
  end
end

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

  -- vim-dadbod, vim-dadbod-ui, vim-dadbod-completion specs are defined
  -- canonically in lua/plugins/dadbod.lua (with the full init function that
  -- registers :DBUIReload, :DBUIHealth, :DBUILogin, etc.). Earlier versions
  -- of this file had partial duplicate specs here, which lazy.nvim merged
  -- and which silently dropped the init function. Don't re-add them here.

  -- (vim-dadbod-completion spec also lives in plugins/dadbod.lua. Removed
  -- the duplicate here for the same reason as vim-dadbod-ui above.)

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
    root_dir = root_pattern('.sqls.yml', '.git'),
    settings = {
      sqls = {
        connections = {
          -- Database connections should be configured in one of:
          -- 1. Project-specific: .sqls.yml in project root (recommended, auto-detected)
          -- 2. Global config: ~/.config/sqls/config.yml
          -- 3. Local override: $SYNC/dotfiles-local/config/nvim/sqls-connections.lua
          --
          -- Example .sqls.yml format:
          -- ```yaml
          -- connections:
          --   - alias: mydb
          --     driver: mysql
          --     dataSourceName: user:pass@tcp(host:3306)/dbname
          -- ```
          --
          -- For local override, create: $SYNC/dotfiles-local/config/nvim/sqls-connections.lua
          -- returning a table of connections (see vim-dadbod documentation)
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
    root_dir = root_pattern '.git',
    settings = {},
  },
}

-- SQL-specific keymaps (only active in SQL buffers)
M.setup_keymaps = function(bufnr)
  local opts = { buffer = bufnr, silent = true }
  local map = vim.keymap.set

  -- Database operations (toggle is global <leader>du; execute is <leader>e in dadbod.lua autocmd)
  map('n', '<leader>du', '<cmd>DBUIToggle<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Toggle UI' }))
  map('n', '<leader>da', '<cmd>DBUIAddConnection<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Add connection' }))
  map('n', '<leader>df', '<cmd>DBUIFindBuffer<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Find buffer' }))
  map('n', '<leader>dr', '<cmd>DBUIRenameBuffer<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Rename buffer' }))
  map('n', '<leader>dl', '<cmd>DBUILastQueryInfo<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Last query info' }))
  map('n', '<leader>dc', '<cmd>DBCompletionClearCache<cr>', vim.tbl_extend('force', opts, { desc = 'DB: Clear completion cache' }))
  map('n', '<leader>sr', function()
    vim.cmd('DB ' .. vim.fn.getline '.')
  end, vim.tbl_extend('force', opts, { desc = 'Execute current line' }))

  -- Query building helpers
  map('n', '<leader>ss', function()
    local table_name = vim.fn.input 'Table name: '
    if table_name ~= '' then
      vim.api.nvim_put({ 'SELECT * FROM ' .. table_name .. ';' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert SELECT statement' }))

  map('n', '<leader>si', function()
    local table_name = vim.fn.input 'Table name: '
    if table_name ~= '' then
      vim.api.nvim_put({ 'INSERT INTO ' .. table_name .. ' () VALUES ();' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert INSERT statement' }))

  map('n', '<leader>su', function()
    local table_name = vim.fn.input 'Table name: '
    if table_name ~= '' then
      vim.api.nvim_put({ 'UPDATE ' .. table_name .. ' SET  WHERE ;' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert UPDATE statement' }))

  map('n', '<leader>sd', function()
    local table_name = vim.fn.input 'Table name: '
    if table_name ~= '' then
      vim.api.nvim_put({ 'DELETE FROM ' .. table_name .. ' WHERE ;' }, 'l', true, true)
    end
  end, vim.tbl_extend('force', opts, { desc = 'Insert DELETE statement' }))

  -- Schema operations
  map('n', '<leader>st', function()
    local table_name = vim.fn.input 'Table name: '
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
    vim.cmd 'normal! gg=G'
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
    local proc_name = vim.fn.input 'Procedure name: '
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
    local view_name = vim.fn.input 'View name: '
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
        require('cmp').setup.buffer {
          sources = {
            { name = 'vim-dadbod-completion' },
            { name = 'buffer' },
          },
        }
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
      if line:match '^DATABASE_URL=' then
        local url = line:match 'DATABASE_URL=(.+)'
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

  -- Auto-execute SQL files
  vim.g.db_ui_auto_execute_table_helpers = 1

  -- Note: g:db_ui_save_location is set in plugins/dadbod.lua (must be set before plugin loads)
  -- Connections are loaded from $NOTES/db_ui/connections.json

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
  -- (The custom `sql_dadbod` cmp source previously lived in
  -- features/sql_completion.lua. It called the non-existent vim.fn['db#cmd']
  -- and silently returned 0 items for every connection. vim-dadbod-completion
  -- already covers the same ground and actually works. Deleted 2026-06-18.)

  -- Enhanced completion for SQL files
  --
  -- Context-aware entry_filter on vim-dadbod-completion:
  --   That plugin bulk-fetches every column in every table (when DB has
  --   ≤10k columns) and then returns the full column list on EVERY completion
  --   request, regardless of context. So typing `SELECT * FROM CH` would show
  --   `CHECKSUM` / `CHECK_TIME` (Field-kind) above `CHARACTER_SETS` (Class-kind)
  --   in the popup. Our custom `sql_dadbod` source is already context-aware, but
  --   vim-dadbod-completion still floods the popup with columns. Hide Field +
  --   Function kinds when the cursor is right after a table-reference keyword.
  --
  --   LSP-kind constants from vim_dadbod_completion/init.lua:
  --     5 = Field (column)    ← HIDE after FROM-like
  --     3 = Function          ← HIDE after FROM-like
  --     7 = Class (table)     ← keep
  --     6 = Variable (alias)  ← keep
  --    14 = Keyword           ← keep
  --    19 = Folder (schema)   ← keep
  -- Which SQL clauses imply "I'm typing a TABLE reference next, hide columns"?
  local FROM_LIKE_SET = {
    FROM = true,
    JOIN = true,
    INTO = true,
    UPDATE = true,
    TABLE = true,
    USING = true,
  }
  -- Which clauses unambiguously END the table-list region (we're now expecting
  -- columns or expressions)? Used to short-circuit the lookback.
  local AFTER_TABLES_SET = {
    WHERE = true,
    ON = true,
    GROUP = true,
    ORDER = true,
    HAVING = true,
    LIMIT = true,
    OFFSET = true,
    SELECT = true,
    SET = true,
    VALUES = true,
  }
  -- Find the last SQL clause keyword in the line (or nil if none). Used by
  -- both the table-context and column-context filters.
  local function _last_clause(line)
    -- Bail if cursor is in a position where a different completion mode
    -- should take over (dot-trigger for column-of-table, quoted identifier,
    -- subquery start, etc.).
    if line:find '[%."`%(%)]%s*[%w_]*$' then
      return nil
    end
    local last
    for word in line:gmatch '[%w_]+' do
      if FROM_LIKE_SET[word] or AFTER_TABLES_SET[word] then
        last = word
      end
    end
    return last
  end
  local function _expecting_table_ref(ctx)
    local line = (ctx.cursor_before_line or ''):upper()
    local last = _last_clause(line)
    return last ~= nil and FROM_LIKE_SET[last] == true
  end
  local function _expecting_column_ref(ctx)
    local line = (ctx.cursor_before_line or ''):upper()
    local last = _last_clause(line)
    return last ~= nil and AFTER_TABLES_SET[last] == true
  end
  -- LSP kinds to hide based on context
  local _HIDE_AFTER_FROM = { [5] = true, [3] = true } -- Field (column), Function
  local _HIDE_AFTER_TABLES = { [7] = true } -- Class (table)

  vim.api.nvim_create_autocmd('FileType', {
    pattern = { 'sql', 'mysql', 'plsql' },
    callback = function()
      require('cmp').setup.buffer {
        sources = {
          -- NB: features/sql_completion.lua used to register a `sql_dadbod`
          -- source here at priority 1000. It was always a no-op: its schema
          -- cache stayed at 0 tables / 0 columns because it called the
          -- non-existent `db#cmd()` function. vim-dadbod-completion already
          -- does everything it was meant to do (context-aware completion,
          -- alias resolution, schema/column caching, dot triggers), so we just
          -- promote it to priority 1000.
          {
            name = 'vim-dadbod-completion',
            priority = 1000,
            entry_filter = function(entry, ctx)
              local kind = entry:get_kind()
              if _expecting_table_ref(ctx) then
                -- After FROM/JOIN/UPDATE/INTO/TABLE/USING: only show table-y
                -- things (Class, Folder=schema, Variable=alias, Keyword).
                return not _HIDE_AFTER_FROM[kind]
              elseif _expecting_column_ref(ctx) then
                -- After WHERE/ON/GROUP BY/ORDER BY/HAVING/SET/etc.: only show
                -- columns and aliases and SQL keywords. Hide raw tables so the
                -- popup isn't noisy when you're typing column expressions.
                return not _HIDE_AFTER_TABLES[kind]
              end
              return true
            end,
          },
          { name = 'buffer', priority = 500 },
          { name = 'path', priority = 300 },
        },
        completion = {
          -- More aggressive completion for SQL
          keyword_length = 1,
          autocomplete = {
            require('cmp.types').cmp.TriggerEvent.TextChanged,
            require('cmp.types').cmp.TriggerEvent.InsertEnter,
          },
        },
        experimental = {
          ghost_text = true,
        },
      }
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

  -- Get default capabilities from main LSP config
  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local ok, cmp_nvim_lsp = pcall(require, 'cmp_nvim_lsp')
  if ok then
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  end

  -- Configure and enable sqls using native Neovim 0.11+ API
  if M.lsp_config.sqls then
    local config = vim.tbl_deep_extend('force', M.lsp_config.sqls, { capabilities = capabilities })
    vim.lsp.config('sqls', config)
    vim.lsp.enable 'sqls'
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
      connection_string = vim.fn.input 'Database connection string: '
    end
    vim.g.db = connection_string
    print('Connected to: ' .. connection_string)
  end, { nargs = '?', desc = 'Connect to database' })

  -- Quick query execution
  vim.api.nvim_create_user_command('SQLExecute', function(opts)
    local query = opts.args
    if query == '' then
      query = vim.fn.input 'SQL Query: '
    end
    vim.cmd('DB ' .. query)
  end, { nargs = '?', desc = 'Execute SQL query' })

  -- Show database schema
  vim.api.nvim_create_user_command('SQLSchema', function()
    vim.cmd 'DB SHOW TABLES;'
  end, { desc = 'Show database schema' })

  -- Format SQL buffer
  vim.api.nvim_create_user_command('SQLFormat', function()
    -- Simple formatting - could integrate with external tools
    vim.cmd 'normal! gg=G'
  end, { desc = 'Format SQL buffer' })
end

return M
