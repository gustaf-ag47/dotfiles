-- DBUI auto-reload — watches $NOTES/db_ui/connections.json with libuv (vim.uv.new_fs_event)
-- and transparently re-binds every open query buffer to the fresh URL whenever the
-- file changes on disk (e.g. when the prod-db-token.service rotates the RDS IAM token).
--
-- Why this exists:
--   * dadbod-ui caches each connection's URL on the dbui instance AND on every query
--     buffer's `b:db`. After the systemd timer rewrites connections.json, both caches
--     are stale → next <leader>e fails with "Access denied" until the user runs
--     :DBUIReload manually (which closes & reopens the drawer).
--   * This module makes that automatic: on every connections.json write we (1) patch
--     `b:db` on every loaded query buffer, (2) call db_ui#reset_state() to drop the
--     in-memory dbs cache, (3) if the drawer is open, redraw it.
--
-- Use:
--   require('features.dbui_autoreload').start()   -- called from dadbod.lua

local M = {}

-- Now supports MULTIPLE paths so it can watch the active project's
-- connections.json AND the inherited workspace-level connections.json
-- simultaneously. Set via M.update_paths({...}) from features/dbui_project.lua
-- whenever the scope changes.
local watchers = {}    ---@type table<string, uv.uv_fs_event_t>
local debounce_timer   ---@type uv.uv_timer_t?
local watched_paths = {} ---@type string[]
local last_mtime = {}  ---@type table<string, integer>  -- per-path mtime guard

-- Legacy single-path globals kept for backward compatibility with the older
-- start()/status() callsites:
local connections_path ---@type string?

local function notes_dir()
  return vim.env.NOTES or ((vim.env.SYNC or vim.env.HOME) .. '/Vault')
end

---@return table<string,string>  name -> url
local function read_connections()
  local f = io.open(connections_path, 'r')
  if not f then return {} end
  local content = f:read('*a')
  f:close()
  local ok, conns = pcall(vim.json.decode, content)
  if not ok or type(conns) ~= 'table' then return {} end
  local by_name = {}
  for _, c in ipairs(conns) do
    if type(c) == 'table' and c.name and c.url then
      by_name[c.name] = c.url
    end
  end
  return by_name
end

-- key_name format from dadbod-ui is "<connection_name>_<source>" where source is
-- "file" (from connections.json), "url" (from g:dbs/g:db_ui_default_query) etc.
local function conn_name_from_key(key_name)
  return (key_name:gsub('_file$', ''):gsub('_url$', ''):gsub('_env$', ''))
end

local function refresh()
  -- Merge entries from all watched files. Later files override earlier ones
  -- (so the project's connections.json shadows the workspace's).
  local by_name = {}
  for _, p in ipairs(watched_paths) do
    local file_path = p  -- capture for closure
    connections_path = file_path  -- read_connections reads from this global; gross but minimal change
    local m = read_connections()
    for k, v in pairs(m) do by_name[k] = v end
  end
  if not next(by_name) then return end

  -- 1) Patch b:db on every loaded dbui-bound buffer so whole-buffer %DB picks up the fresh URL.
  local patched = 0
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(buf) then
      local ok_kn, kn = pcall(vim.api.nvim_buf_get_var, buf, 'dbui_db_key_name')
      if ok_kn and type(kn) == 'string' and kn ~= '' then
        local fresh_url = by_name[conn_name_from_key(kn)]
        if fresh_url then
          pcall(vim.api.nvim_buf_set_var, buf, 'db', fresh_url)
          patched = patched + 1
        end
      end
    end
  end

  -- 1b) Patch vim.g.dbs with fresh URLs. dbui_project.apply() sets vim.g.dbs at
  --     VimEnter/DirChanged but never re-reads on token rotation, so the workspace-
  --     level connections (prod etc.) carry the startup token forever.
  --     Patch in-place to keep the same entry order and any project-level filtering
  --     that apply() already did.
  if vim.g.dbs then
    local updated = {}
    for _, entry in ipairs(vim.g.dbs) do
      local fresh = entry.name and by_name[entry.name]
      updated[#updated + 1] = fresh and { name = entry.name, url = fresh } or entry
    end
    vim.g.dbs = updated
  end

  -- 2) Drop dadbod-ui's in-memory dbs_list/connection cache so visual-mode execution
  --    (which uses dbui_instance.dbs[key].conn) also picks up the new URL next time.
  pcall(vim.fn['db_ui#reset_state'])

  -- 3) If the drawer is currently visible, close + reopen it so connection counts
  --    and the ✓ markers reflect the new state immediately.
  local drawer_open = false
  for _, w in ipairs(vim.api.nvim_list_wins()) do
    local b = vim.api.nvim_win_get_buf(w)
    if vim.bo[b].filetype == 'dbui' then
      drawer_open = true
      break
    end
  end
  if drawer_open then
    pcall(vim.cmd, 'DBUIClose')
    pcall(vim.cmd, 'DBUI')
  end

  if patched > 0 then
    vim.notify(
      ('[DBUI] auto-reloaded — %d buffer%s rebound'):format(patched, patched == 1 and '' or 's'),
      vim.log.levels.INFO
    )
  end
end

local function schedule_refresh()
  -- Debounce — token-rewrite scripts may write twice in rapid succession
  -- (open-truncate then a final flush). 250 ms collapses both into one refresh.
  if debounce_timer then
    debounce_timer:stop()
    if not debounce_timer:is_closing() then debounce_timer:close() end
  end
  debounce_timer = vim.uv.new_timer()
  debounce_timer:start(250, 0, vim.schedule_wrap(function()
    if debounce_timer and not debounce_timer:is_closing() then
      debounce_timer:close()
    end
    debounce_timer = nil
    -- mtime check across ALL watched paths. If ANY changed, refresh.
    local any_changed = false
    for _, p in ipairs(watched_paths) do
      local st = vim.uv.fs_stat(p)
      if st then
        local mtime = st.mtime.sec * 1e9 + st.mtime.nsec
        if mtime ~= last_mtime[p] then
          any_changed = true
          last_mtime[p] = mtime
        end
      end
    end
    if any_changed then refresh() end
  end))
end

local function on_change(err, _filename, events)
  if err then return end
  schedule_refresh()
  -- Some editors do atomic-rename writes. Truncate-writes (what our token script
  -- does) keep the inode and the watcher stays attached. For renames, the watcher
  -- detaches silently — re-arm on the path.
  if events and events.rename and watcher then
    pcall(function() watcher:stop() end)
    vim.defer_fn(function()
      if watcher and connections_path then
        pcall(function() watcher:start(connections_path, {}, vim.schedule_wrap(on_change)) end)
      end
    end, 50)
  end
end

-- Internal: start a single watcher on one path.
local function start_one(path)
  if watchers[path] then return end
  if vim.fn.filereadable(path) == 0 then return end
  local st = vim.uv.fs_stat(path)
  if st then last_mtime[path] = st.mtime.sec * 1e9 + st.mtime.nsec end
  local handle = vim.uv.new_fs_event()
  if not handle then return end
  local ok = pcall(function()
    handle:start(path, {}, vim.schedule_wrap(function(err, _filename, events)
      if err then return end
      schedule_refresh()
      -- atomic-rename re-arm (per-path)
      if events and events.rename then
        pcall(function() handle:stop() end)
        vim.defer_fn(function()
          if watchers[path] then
            pcall(function() handle:start(path, {}, vim.schedule_wrap(on_change)) end)
          end
        end, 50)
      end
    end))
  end)
  if not ok then
    pcall(function() handle:close() end)
    return
  end
  watchers[path] = handle
end

local function stop_one(path)
  local h = watchers[path]
  if not h then return end
  pcall(function() h:stop() end)
  pcall(function() h:close() end)
  watchers[path] = nil
  last_mtime[path] = nil
end

-- Replace the watched-paths set. Called from features/dbui_project.lua
-- whenever the active scope changes.
function M.update_paths(paths)
  paths = paths or {}
  -- normalize: drop nils, dedupe
  local seen = {}
  local new_paths = {}
  for _, p in ipairs(paths) do
    if type(p) == 'string' and p ~= '' and not seen[p] then
      seen[p] = true
      table.insert(new_paths, p)
    end
  end
  -- Stop watchers no longer wanted
  for path, _ in pairs(watchers) do
    if not seen[path] then stop_one(path) end
  end
  -- Start new ones
  for _, p in ipairs(new_paths) do start_one(p) end
  watched_paths = new_paths
  -- Keep the legacy global pointing at the first path (for status()).
  connections_path = new_paths[1]
end

function M.start()
  -- Legacy startup: watch the default $NOTES/db_ui/connections.json. The
  -- project module (if loaded) will immediately overwrite via update_paths.
  if next(watchers) ~= nil then return end
  local default = notes_dir() .. '/db_ui/connections.json'
  M.update_paths({ default })

  vim.api.nvim_create_autocmd('VimLeavePre', {
    once = true,
    callback = function() M.stop() end,
  })
end

function M.stop()
  if debounce_timer then
    pcall(function() debounce_timer:stop() end)
    if debounce_timer and not debounce_timer:is_closing() then
      pcall(function() debounce_timer:close() end)
    end
    debounce_timer = nil
  end
  for path, _ in pairs(watchers) do stop_one(path) end
end

-- Manual probe: print current watcher state, useful when debugging.
function M.status()
  local n = 0
  for _ in pairs(watchers) do n = n + 1 end
  return {
    active = n > 0,
    -- Legacy single-path field (first watched path) + new fields
    path = connections_path,
    paths = vim.deepcopy(watched_paths),
    watcher_count = n,
    last_mtime = last_mtime,
  }
end

return M
