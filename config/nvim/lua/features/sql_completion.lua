-- Intelligent SQL completion for vim-dadbod
-- Provides context-aware autocompletion based on actual database schema
-- Integrates with nvim-cmp and respects modular architecture

local M = {}

-- Cache for database schemas to avoid repeated queries
M.schema_cache = {}
M.cache_duration = 300 -- 5 minutes in seconds

-- SQL keywords by category for intelligent completion
M.sql_keywords = {
  -- Primary statements
  statements = {
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER',
    'TRUNCATE', 'REPLACE', 'MERGE', 'WITH', 'EXPLAIN', 'DESCRIBE', 'SHOW'
  },

  -- Clauses and operators
  clauses = {
    'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT', 'OFFSET',
    'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN', 'CROSS JOIN',
    'ON', 'USING', 'UNION', 'UNION ALL', 'INTERSECT', 'EXCEPT',
    'INTO', 'VALUES', 'SET', 'AS', 'DISTINCT', 'ALL', 'EXISTS', 'NOT EXISTS'
  },

  -- Functions
  functions = {
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'ISNULL', 'NULLIF',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'CAST', 'CONVERT',
    'SUBSTRING', 'LENGTH', 'UPPER', 'LOWER', 'TRIM', 'LTRIM', 'RTRIM',
    'NOW', 'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'DATE', 'YEAR', 'MONTH', 'DAY'
  },

  -- Data types
  types = {
    'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT', 'DECIMAL', 'NUMERIC',
    'FLOAT', 'DOUBLE', 'REAL', 'VARCHAR', 'CHAR', 'TEXT', 'LONGTEXT',
    'DATE', 'DATETIME', 'TIMESTAMP', 'TIME', 'BOOLEAN', 'BOOL', 'JSON', 'BLOB'
  },

  -- Constraints and modifiers
  constraints = {
    'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'NOT NULL', 'DEFAULT',
    'CHECK', 'INDEX', 'CONSTRAINT', 'REFERENCES', 'AUTO_INCREMENT'
  }
}

-- Database-specific schema query templates
M.schema_queries = {
  mysql = {
    tables = [[
      SELECT table_name, table_type, table_comment
      FROM information_schema.tables
      WHERE table_schema = DATABASE()
      ORDER BY table_name
    ]],

    columns = [[
      SELECT table_name, column_name, data_type, is_nullable,
             column_default, column_comment, column_key
      FROM information_schema.columns
      WHERE table_schema = DATABASE()
      ORDER BY table_name, ordinal_position
    ]],

    indexes = [[
      SELECT table_name, index_name, column_name, non_unique
      FROM information_schema.statistics
      WHERE table_schema = DATABASE()
      ORDER BY table_name, index_name, seq_in_index
    ]]
  },

  postgresql = {
    tables = [[
      SELECT schemaname||'.'||tablename as table_name, 'TABLE' as table_type, '' as table_comment
      FROM pg_tables
      WHERE schemaname = current_schema()
      UNION ALL
      SELECT schemaname||'.'||viewname as table_name, 'VIEW' as table_type, '' as table_comment
      FROM pg_views
      WHERE schemaname = current_schema()
      ORDER BY table_name
    ]],

    columns = [[
      SELECT t.table_name, c.column_name, c.data_type, c.is_nullable,
             c.column_default, '' as column_comment,
             CASE WHEN pk.column_name IS NOT NULL THEN 'PRI' ELSE '' END as column_key
      FROM information_schema.tables t
      JOIN information_schema.columns c ON t.table_name = c.table_name
      LEFT JOIN (
        SELECT ku.table_name, ku.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage ku ON tc.constraint_name = ku.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
      ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
      WHERE t.table_schema = current_schema() AND c.table_schema = current_schema()
      ORDER BY t.table_name, c.ordinal_position
    ]],

    indexes = [[
      SELECT t.relname as table_name, i.relname as index_name,
             a.attname as column_name, NOT ix.indisunique as non_unique
      FROM pg_class t, pg_class i, pg_index ix, pg_attribute a
      WHERE t.oid = ix.indrelid AND i.oid = ix.indexrelid
      AND a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
      AND t.relkind = 'r' AND t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
      ORDER BY t.relname, i.relname
    ]]
  },

  sqlite = {
    tables = [[
      SELECT name as table_name, type as table_type, '' as table_comment
      FROM sqlite_master
      WHERE type IN ('table', 'view')
      ORDER BY name
    ]],

    columns = [[
      SELECT m.name as table_name, p.name as column_name, p.type as data_type,
             CASE WHEN p."notnull" = 0 THEN 'YES' ELSE 'NO' END as is_nullable,
             p.dflt_value as column_default, '' as column_comment,
             CASE WHEN p.pk = 1 THEN 'PRI' ELSE '' END as column_key
      FROM sqlite_master m
      JOIN pragma_table_info(m.name) p
      WHERE m.type = 'table'
      ORDER BY m.name, p.cid
    ]],

    indexes = [[
      SELECT m.tbl_name as table_name, il.name as index_name,
             ii.name as column_name, NOT il."unique" as non_unique
      FROM sqlite_master m
      JOIN pragma_index_list(m.name) il
      JOIN pragma_index_info(il.name) ii
      WHERE m.type = 'table'
      ORDER BY m.tbl_name, il.name, ii.seqno
    ]]
  }
}

-- Detect database type from connection string or current database
M.detect_db_type = function()
  local db = vim.g.db or vim.b.db
  if not db then
    return 'mysql' -- default fallback
  end

  if db:match('mysql') or db:match('mariadb') then
    return 'mysql'
  elseif db:match('postgres') or db:match('postgresql') then
    return 'postgresql'
  elseif db:match('sqlite') then
    return 'sqlite'
  else
    return 'mysql' -- default fallback
  end
end

-- Execute database query and return results
M.execute_query = function(query)
  local results = {}

  -- Use vim-dadbod to execute query
  local output = vim.fn['db#cmd']({line1 = 1, line2 = 1}, query)

  if output and #output > 0 then
    -- Parse the output (this is simplified - you might need more robust parsing)
    local lines = vim.split(output, '\n')
    local headers = {}

    for i, line in ipairs(lines) do
      if i == 1 then
        -- Parse headers
        headers = vim.split(line, '\t')
      elseif line ~= '' and not line:match('^%-+') then
        -- Parse data rows
        local values = vim.split(line, '\t')
        local row = {}
        for j, header in ipairs(headers) do
          row[header] = values[j] or ''
        end
        table.insert(results, row)
      end
    end
  end

  return results
end

-- Get database schema information
M.get_schema = function(force_refresh)
  force_refresh = force_refresh or false

  local db_type = M.detect_db_type()
  local cache_key = (vim.g.db or vim.b.db or 'default') .. ':' .. db_type
  local current_time = os.time()

  -- Check cache
  if not force_refresh and M.schema_cache[cache_key] then
    local cached = M.schema_cache[cache_key]
    if current_time - cached.timestamp < M.cache_duration then
      return cached.schema
    end
  end

  local schema = {
    tables = {},
    columns = {},
    indexes = {},
    timestamp = current_time
  }

  local queries = M.schema_queries[db_type]
  if not queries then
    return schema
  end

  -- Get tables
  local ok, tables = pcall(M.execute_query, queries.tables)
  if ok and tables then
    for _, table in ipairs(tables) do
      schema.tables[table.table_name] = {
        name = table.table_name,
        type = table.table_type,
        comment = table.table_comment or ''
      }
    end
  end

  -- Get columns
  local ok2, columns = pcall(M.execute_query, queries.columns)
  if ok and columns then
    for _, column in ipairs(columns) do
      if not schema.columns[column.table_name] then
        schema.columns[column.table_name] = {}
      end
      table.insert(schema.columns[column.table_name], {
        name = column.column_name,
        type = column.data_type,
        nullable = column.is_nullable == 'YES',
        default = column.column_default,
        comment = column.column_comment or '',
        is_primary = column.column_key == 'PRI'
      })
    end
  end

  -- Get indexes
  local ok3, indexes = pcall(M.execute_query, queries.indexes)
  if ok and indexes then
    for _, index in ipairs(indexes) do
      if not schema.indexes[index.table_name] then
        schema.indexes[index.table_name] = {}
      end
      table.insert(schema.indexes[index.table_name], {
        name = index.index_name,
        column = index.column_name,
        unique = index.non_unique == '0'
      })
    end
  end

  -- Cache the schema
  M.schema_cache[cache_key] = {
    schema = schema,
    timestamp = current_time
  }

  return schema
end

-- Parse SQL context to determine what to complete
M.parse_sql_context = function(line, col)
  local before_cursor = line:sub(1, col - 1):upper()
  local _after_cursor = line:sub(col):upper()

  local context = {
    type = 'unknown',
    table_context = nil,
    in_select = false,
    in_from = false,
    in_where = false,
    in_join = false,
    expecting_column = false,
    expecting_table = false,
    last_table = nil
  }

  -- Determine if we're in different SQL clauses
  context.in_select = before_cursor:match('SELECT') and not before_cursor:match('FROM')
  context.in_from = before_cursor:match('FROM') and not before_cursor:match('WHERE') and not before_cursor:match('GROUP BY') and not before_cursor:match('ORDER BY')
  context.in_where = before_cursor:match('WHERE') and not before_cursor:match('GROUP BY') and not before_cursor:match('ORDER BY')
  context.in_join = before_cursor:match('JOIN')

  -- Extract table context
  local table_match = before_cursor:match('FROM%s+(%w+)')
  if not table_match then
    table_match = before_cursor:match('JOIN%s+(%w+)')
  end
  context.last_table = table_match

  -- Determine what type of completion is expected
  if context.in_select and before_cursor:match(',%s*$') then
    context.expecting_column = true
    context.type = 'column'
  elseif context.in_from then
    context.expecting_table = true
    context.type = 'table'
  elseif context.in_where or context.in_join then
    context.expecting_column = true
    context.type = 'column'
  elseif before_cursor:match('%s$') or before_cursor:match('^%s*$') then
    context.type = 'keyword'
  end

  return context
end

-- Generate completion items based on context
M.get_completion_items = function(context, schema)
  local items = {}

  if context.type == 'table' then
    -- Complete table names
    for table_name, table_info in pairs(schema.tables) do
      table.insert(items, {
        label = table_name,
        kind = 17, -- cmp.lsp.CompletionItemKind.Struct (represents table)
        detail = table_info.type .. (table_info.comment ~= '' and ': ' .. table_info.comment or ''),
        documentation = string.format('Table: %s\nType: %s\nComment: %s',
          table_name, table_info.type, table_info.comment),
        insertText = table_name,
        sortText = '1_' .. table_name -- Sort tables first
      })
    end

  elseif context.type == 'column' then
    -- Complete column names
    if context.last_table and schema.columns[context.last_table] then
      -- Context-specific columns for the current table
      for _, column in ipairs(schema.columns[context.last_table]) do
        local detail = column.type .. (column.is_primary and ' (PK)' or '') ..
                      (not column.nullable and ' NOT NULL' or '')

        table.insert(items, {
          label = column.name,
          kind = 5, -- cmp.lsp.CompletionItemKind.Field
          detail = detail,
          documentation = string.format('Column: %s.%s\nType: %s\nNullable: %s\nDefault: %s\nComment: %s',
            context.last_table, column.name, column.type,
            column.nullable and 'YES' or 'NO',
            column.default or 'NULL',
            column.comment or 'None'),
          insertText = column.name,
          sortText = (column.is_primary and '1_' or '2_') .. column.name
        })
      end
    else
      -- All columns from all tables when no specific table context
      for table_name, columns in pairs(schema.columns) do
        for _, column in ipairs(columns) do
          table.insert(items, {
            label = table_name .. '.' .. column.name,
            kind = 5, -- cmp.lsp.CompletionItemKind.Field
            detail = column.type,
            documentation = string.format('Column: %s.%s\nType: %s', table_name, column.name, column.type),
            insertText = table_name .. '.' .. column.name,
            sortText = '3_' .. table_name .. '.' .. column.name
          })
        end
      end
    end

  elseif context.type == 'keyword' then
    -- Complete SQL keywords
    for category, keywords in pairs(M.sql_keywords) do
      for _, keyword in ipairs(keywords) do
        table.insert(items, {
          label = keyword,
          kind = 14, -- cmp.lsp.CompletionItemKind.Keyword
          detail = 'SQL ' .. category,
          insertText = keyword,
          sortText = '4_' .. keyword
        })
      end
    end
  end

  return items
end

-- Main completion function for nvim-cmp
M.complete = function(request, callback)
  local schema = M.get_schema()
  local line = request.context.cursor_line
  local col = request.context.cursor.col

  local context = M.parse_sql_context(line, col)
  local items = M.get_completion_items(context, schema)

  callback({
    items = items,
    isIncomplete = false
  })
end

-- Setup function to integrate with nvim-cmp
M.setup = function(opts)
  -- luacheck: ignore 311
  opts = opts or {}

  -- Register as a completion source
  local ok, cmp = pcall(require, 'cmp')
  if not ok then
    vim.notify('nvim-cmp not found, SQL completion disabled', vim.log.levels.WARN)
    return
  end

  -- Create custom source
  local source = {}

  source.new = function()
    return setmetatable({}, { __index = source })
  end

  source.get_debug_name = function()
    return 'sql_dadbod'
  end

  source.is_available = function()
    return vim.bo.filetype == 'sql' or vim.g.db ~= nil or vim.b.db ~= nil
  end

  source.complete = function(self, request, callback)
    M.complete(request, callback)
  end

  -- Register the source
  cmp.register_source('sql_dadbod', source)

  -- Setup completion for SQL files
  vim.api.nvim_create_autocmd('FileType', {
    pattern = 'sql',
    callback = function()
      cmp.setup.buffer({
        sources = cmp.config.sources({
          { name = 'sql_dadbod', priority = 1000 },
          { name = 'vim-dadbod-completion', priority = 800 },
          { name = 'buffer', priority = 500 },
          { name = 'path', priority = 300 },
        })
      })
    end
  })

  -- Create user commands for manual schema refresh
  vim.api.nvim_create_user_command('SQLRefreshSchema', function()
    M.get_schema(true)
    vim.notify('SQL schema cache refreshed', vim.log.levels.INFO)
  end, { desc = 'Refresh SQL schema cache' })

  vim.api.nvim_create_user_command('SQLShowSchema', function()
    local schema = M.get_schema()
    local lines = { '# Database Schema', '' }

    for table_name, table_info in pairs(schema.tables) do
      table.insert(lines, string.format('## Table: %s (%s)', table_name, table_info.type))
      table.insert(lines, '')

      if schema.columns[table_name] then
        table.insert(lines, '| Column | Type | Nullable | Default | Key |')
        table.insert(lines, '|--------|------|----------|---------|-----|')

        for _, column in ipairs(schema.columns[table_name]) do
          table.insert(lines, string.format('| %s | %s | %s | %s | %s |',
            column.name, column.type,
            column.nullable and 'YES' or 'NO',
            column.default or 'NULL',
            column.is_primary and 'PRI' or ''))
        end
        table.insert(lines, '')
      end
    end

    local buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    vim.api.nvim_buf_set_option(buf, 'filetype', 'markdown')
    vim.api.nvim_set_current_buf(buf)
  end, { desc = 'Show database schema' })
end

return M