-- Prod DML/DDL guard for vim-dadbod queries
--
-- Hooks the `User DBExecutePre` autocmd that tpope's vim-dadbod fires before
-- every `:DB` invocation. When the current buffer's connection name matches
-- a "prod tag" (default: substring "prod", case-insensitive), the guard scans
-- the buffer for DML/DDL keywords. If found, the query is aborted with a
-- loud `[DBUI] BLOCKED:` message.
--
-- Defence-in-depth: the prod Aurora cluster is read-only and the IAM user
-- is `dev_readonly`. This guard adds an editor-level check so wrong-tab
-- mistakes are caught BEFORE bytes leave nvim.
--
-- Usage (from plugins/dadbod.lua):
--   require('features.dbui_dml_guard').setup({
--     prod_tags = { 'prod' },   -- substring match (lowercased)
--     dangerous = { 'UPDATE','DELETE','INSERT', … },  -- override if needed
--   })
--
-- Public API:
--   M.check(lines, opts?) -> keyword|nil
--     Pure function. Returns the first dangerous keyword found, or nil if
--     the SQL is safe. Used by the regression suite to test the parser
--     without a DB connection.

local M = {}

local DEFAULTS = {
  -- Substring(s) on the lowercased connection name that activate the guard.
  prod_tags = { 'prod' },

  -- Dangerous keywords. Match if appearing as the first significant token
  -- of any line/`;`-statement after stripping safe prefixes and lock clauses.
  dangerous = {
    'UPDATE',
    'DELETE',
    'INSERT',
    'DROP',
    'TRUNCATE',
    'ALTER',
    'REPLACE',
    'GRANT',
    'REVOKE',
    'CREATE',
    'RENAME',
    'MERGE',
    'CALL',
    'LOAD',
  },

  -- Word-boundary keywords that should bypass the guard when they're the
  -- first significant token of a statement. EXPLAIN/DESC/SHOW are read-only
  -- on MySQL+Postgres. EXPLAIN ANALYZE is special-cased (it EXECUTES on
  -- both engines, so we strip the prefix and re-check the inner).
  safe_prefixes = { 'EXPLAIN', 'DESCRIBE', 'DESC', 'SHOW' },

  -- Lock clauses to strip before the dangerous-keyword scan. These are
  -- read-intent, not write-intent (SELECT … FOR UPDATE locks rows but
  -- doesn't modify them).
  lock_clauses = {
    '[Ff][Oo][Rr]%s+[Uu][Pp][Dd][Aa][Tt][Ee]',
    '[Ff][Oo][Rr]%s+[Ss][Hh][Aa][Rr][Ee]',
    '[Ll][Oo][Cc][Kk]%s+[Ii][Nn]%s+[Ss][Hh][Aa][Rr][Ee]%s+[Mm][Oo][Dd][Ee]',
  },
}

local config = vim.deepcopy(DEFAULTS)

-- ---------------------------------------------------------------------------
-- Pure parser
-- ---------------------------------------------------------------------------

-- Strip /* */, --, '…', "…", `…` so keywords inside data/identifiers don't
-- false-positive. Returns the cleaned SQL with string contents replaced by
-- empty markers (so position offsets stay roughly the same for downstream
-- statement-splitting).
local function strip_strings_and_comments(s)
  s = s:gsub('/%*.-%*/', ' ') -- /* block comment */
  s = s:gsub('%-%-[^\n]*', ' ') -- -- line comment
  s = s:gsub("'[^']*'", "''") -- 'string literal'
  s = s:gsub('"[^"]*"', '""') -- "double-quoted"
  s = s:gsub('`[^`]*`', '``') -- `backtick identifier`
  return s
end

-- Check ONE chunk (one line, one ;-statement). Returns the offending keyword
-- name (uppercase) or nil if safe.
local function check_chunk(chunk)
  -- Trim leading whitespace + structural noise (parens, commas)
  local s = chunk:gsub('^[%s%(%),]+', ''):upper()
  if s == '' then
    return nil
  end

  -- EXPLAIN ANALYZE on MySQL and Postgres EXECUTES the inner statement;
  -- strip the prefix and re-check.
  s = s:gsub('^EXPLAIN%s+ANALYZE%s+', '')

  -- Bare safe prefixes: skip this chunk entirely.
  for _, p in ipairs(config.safe_prefixes) do
    if s:match('^' .. p .. '%f[%W]') then
      return nil
    end
  end

  -- Strip lock clauses (read-intent, not write).
  for _, pat in ipairs(config.lock_clauses) do
    s = s:gsub(pat, ' ')
  end

  -- Global word-boundary scan. The frontier %f[%w_]KW%f[^%w_] treats
  -- underscore as a word-char so identifiers like `update_log` /
  -- `customer_delete_id` / `created_at` don't trigger.
  for _, kw in ipairs(config.dangerous) do
    if s:find('%f[%w_]' .. kw .. '%f[^%w_]') then
      return kw
    end
  end
  return nil
end

-- Scan a multi-line buffer.
--
-- Splits per-line, then per-`;` within each line, so all three statement-
-- separation conventions are caught:
--   1. `SELECT 1; DELETE FROM x;`    (semicolons)
--   2. `SELECT 1\nDELETE FROM x`     (newlines, no `;` — common while iterating)
--   3. Visual-line exec of a single DML line in a buffer with other SELECTs
--      (we can't detect visual mode from the autocmd, so whole-buffer is safe)
--
-- @param lines  string[] | string  Either a list of lines or a single SQL string.
-- @return       string|nil         First dangerous keyword found, else nil.
function M.check(lines)
  local sql
  if type(lines) == 'table' then
    sql = table.concat(lines, '\n')
  elseif type(lines) == 'string' then
    sql = lines
  else
    return nil
  end
  sql = strip_strings_and_comments(sql)
  for line in sql:gmatch '[^\n]+' do
    for chunk in line:gmatch '[^;]+' do
      local hit = check_chunk(chunk)
      if hit then
        return hit
      end
    end
  end
  return nil
end

-- Decide whether the guard should activate for a given buffer's connection.
function M.is_prod(key_name)
  if not key_name then
    return false
  end
  local lower = key_name:lower()
  for _, tag in ipairs(config.prod_tags) do
    if lower:find(tag, 1, true) then
      return true
    end
  end
  return false
end

-- ---------------------------------------------------------------------------
-- Wiring (User DBExecutePre autocmd)
-- ---------------------------------------------------------------------------

local autocmd_id

function M.setup(opts)
  config = vim.tbl_deep_extend('force', config, opts or {})

  -- Tear down a prior autocmd if setup() is being re-called (lazy reload).
  if autocmd_id then
    pcall(vim.api.nvim_del_autocmd, autocmd_id)
    autocmd_id = nil
  end

  autocmd_id = vim.api.nvim_create_autocmd('User', {
    pattern = '*DBExecutePre',
    desc = 'Block DML/DDL on prod-tagged connections',
    callback = function()
      local key = vim.b.dbui_db_key_name
      if not M.is_prod(key) then
        return
      end

      local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
      local hit = M.check(lines)
      if hit then
        local msg = ('[DBUI] BLOCKED: %s on %s. Use a non-prod connection.'):format(hit, key)
        -- nvim_err_writeln persists to :messages (vim.notify inside silent
        -- doautocmd is sometimes swallowed). Schedule so it survives the
        -- error() that aborts :DB.
        vim.schedule(function()
          vim.api.nvim_err_writeln(msg)
        end)
        error('prod DML blocked: ' .. hit) -- aborts :DB
      end
    end,
  })
end

return M
