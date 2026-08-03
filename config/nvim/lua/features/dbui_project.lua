-- Project-aware DBUI scope: switch g:db_ui_save_location based on cwd so the
-- drawer only shows DBs relevant to the workspace/project you're currently in.
--
-- Layout under $NOTES/db_ui/:
--
--   connections.json                           ← global fallback (when no workspace matches)
--   workspaces/
--     <workspace_name>/
--       connections.json                       ← workspace-shared DBs (every project sees them)
--       <conn_name>/                           ← saved-query subdirs (shared)
--       projects/
--         <project_name>/
--           connections.json                   ← project-only DBs
--           <conn_name>/                       ← saved-query subdirs (project-only)
--
-- Detection precedence (highest first):
--   1. Marker file `.dbui-workspace` in any ancestor dir → explicit override
--   2. Configured path_patterns (e.g. '/sync/src/YourOrg/')
--   3. Configured git_remote_patterns (e.g. 'github%.com[:/]YourOrg/')
--   4. Fall through to global $NOTES/db_ui/connections.json
--
-- Within the chosen workspace, the active PROJECT is determined by walking up
-- from cwd looking for a `.dbui-project` marker, OR by matching cwd against
-- the names of subdirectories under workspaces/<ws>/projects/.
--
-- On a matched (workspace, project) the module:
--   * sets g:db_ui_save_location to the project's dir (so its connections.json
--     and saved-query subdirs are the drawer's primary view)
--   * sets vim.g.dbs to the workspace-shared connections.json contents (so the
--     workspace-level DBs appear in the drawer alongside the project ones)
--   * calls db_ui#reset_state() so the next :DBUI re-reads from the new spot
--
-- On a workspace match without a specific project:
--   * sets g:db_ui_save_location to the workspace's dir
--   * vim.g.dbs is left nil (the workspace's connections.json IS the source)
--
-- On no match, falls back to $NOTES/db_ui/.

local M = {}

local DEFAULTS = {
  -- List of workspaces. First match wins. Each entry is:
  --   { name = '...', path_patterns = {...}, git_remote_patterns = {...} }
  workspaces = {},
  -- Notify on every DirChanged. Set false to be silent.
  notify_on_change = true,
}

local config = vim.deepcopy(DEFAULTS)
local current = {
  workspace = nil,
  project   = nil,
  save_location = nil,
  shared_path = nil,
}

local function notes_dir()
  return vim.env.NOTES or ((vim.env.SYNC or vim.env.HOME) .. '/Vault')
end

local function db_ui_root()
  return notes_dir() .. '/db_ui'
end

local function read_json(path)
  if vim.fn.filereadable(path) == 0 then return nil end
  local raw = table.concat(vim.fn.readfile(path), '\n')
  local ok, parsed = pcall(vim.json.decode, raw)
  if ok then return parsed end
  return nil
end

-- Walk up from `start` looking for any of the marker names in `markers`.
-- A marker can be a file OR a directory (so `.git/` is detected too).
-- Returns (dir, marker_path) of the first found, or nil.
local function find_marker_upwards(start, markers)
  local dir = start
  for _ = 1, 32 do
    for _, m in ipairs(markers) do
      local cand = dir .. '/' .. m
      if vim.fn.filereadable(cand) == 1 or vim.fn.isdirectory(cand) == 1 then
        return dir, cand
      end
    end
    local parent = vim.fn.fnamemodify(dir, ':h')
    if parent == dir then break end
    dir = parent
  end
  return nil, nil
end

-- Decide the workspace for a given cwd.
-- Returns (workspace_name, workspace_table) or nil.
local function detect_workspace(cwd)
  -- 1. Marker file override
  local mdir, mpath = find_marker_upwards(cwd, { '.dbui-workspace' })
  if mpath then
    local content = (vim.fn.readfile(mpath)[1] or ''):gsub('^%s+', ''):gsub('%s+$', '')
    if content ~= '' then
      for _, ws in ipairs(config.workspaces) do
        if ws.name == content then return ws.name, ws end
      end
    end
  end

  -- 2. Path-pattern match
  for _, ws in ipairs(config.workspaces) do
    for _, pat in ipairs(ws.path_patterns or {}) do
      if cwd:find(pat) then return ws.name, ws end
    end
  end

  -- 3. Git remote match (slower; do last)
  for _, ws in ipairs(config.workspaces) do
    if ws.git_remote_patterns and #ws.git_remote_patterns > 0 then
      local remote = vim.fn.system({ 'git', '-C', cwd, 'remote', 'get-url', 'origin' })
      if vim.v.shell_error == 0 then
        for _, pat in ipairs(ws.git_remote_patterns) do
          if remote:find(pat) then return ws.name, ws end
        end
      end
    end
  end

  return nil, nil
end

-- Decide the project inside a workspace for the given cwd.
local function detect_project(cwd, ws_name)
  if not ws_name then return nil end

  -- 1. .dbui-project marker (must be a file with a project name inside)
  local _, mpath = find_marker_upwards(cwd, { '.dbui-project' })
  if mpath and vim.fn.filereadable(mpath) == 1 then
    local content = (vim.fn.readfile(mpath)[1] or ''):gsub('^%s+', ''):gsub('%s+$', '')
    if content ~= '' then return content end
  end

  -- 2. Subdir-name match: any path component of cwd that equals a known
  --    project dir under workspaces/<ws>/projects/<*>.
  local projects_root = db_ui_root() .. '/workspaces/' .. ws_name .. '/projects'
  if vim.fn.isdirectory(projects_root) == 1 then
    local known = vim.fn.readdir(projects_root) or {}
    -- Try the deepest match first (e.g. cwd contains both "api-platform"
    -- and a generic "platform" — prefer the more specific one).
    table.sort(known, function(a, b) return #a > #b end)
    for _, p in ipairs(known) do
      if cwd:find('/' .. p .. '/', 1, true)
         or cwd:match('/' .. p .. '$')
         or cwd:match('/' .. p .. '/$') then
        return p
      end
    end
  end

  -- 3. Git root basename fallback: walk up looking for .git/, treat the
  --    enclosing dir's basename as the implicit project. Lets new repos
  --    auto-register without pre-creating workspaces/<ws>/projects/<name>/.
  local mdir, _ = find_marker_upwards(cwd, { '.git' })
  if mdir then
    return vim.fn.fnamemodify(mdir, ':t')
  end

  return nil
end

-- Public: compute and apply the current scope.
--
-- opts: {
--   cwd = string,             -- override cwd (default: vim.fn.getcwd())
--   force_workspace = string, -- skip detection, force this workspace
--   force_project = string,   -- skip detection, force this project
--   notify = boolean,         -- emit [DBUI] scope: notify (default: true)
-- }
function M.apply(opts)
  opts = opts or {}
  local cwd = opts.cwd or vim.fn.getcwd()
  local ws_name, proj
  if opts.force_workspace then
    ws_name = opts.force_workspace
    proj    = opts.force_project
  else
    ws_name = detect_workspace(cwd)
    proj    = detect_project(cwd, ws_name)
  end

  local save_loc, scope_label, shared_path
  if ws_name and proj then
    save_loc = db_ui_root() .. '/workspaces/' .. ws_name .. '/projects/' .. proj
    shared_path = db_ui_root() .. '/workspaces/' .. ws_name .. '/connections.json'
    scope_label = ws_name .. '/' .. proj
  elseif ws_name then
    save_loc = db_ui_root() .. '/workspaces/' .. ws_name
    scope_label = ws_name
  else
    save_loc = db_ui_root()
    scope_label = 'default'
  end

  -- Ensure the save_location exists (don't auto-create global; user owns it).
  if save_loc ~= db_ui_root() and vim.fn.isdirectory(save_loc) == 0 then
    vim.fn.mkdir(save_loc, 'p')
    local cjson = save_loc .. '/connections.json'
    if vim.fn.filereadable(cjson) == 0 then
      vim.fn.writefile({ '[]' }, cjson)
    end
  end

  vim.g.db_ui_save_location = save_loc

  -- If in a project subdir, inherit workspace-level entries via g:dbs.
  -- dadbod-ui merges g:dbs with the connections.json at save_location, so
  -- both appear in the drawer (distinct source: 'g:dbs' vs 'file').
  if shared_path and vim.fn.filereadable(shared_path) == 1 then
    local shared = read_json(shared_path)
    if type(shared) == 'table' then
      -- Filter out entries whose name COLLIDES with a project-local entry;
      -- the project's connections.json wins ("more specific shadows").
      local project_names = {}
      local proj_cjson = save_loc .. '/connections.json'
      local proj_conns = read_json(proj_cjson) or {}
      for _, c in ipairs(proj_conns) do
        if c and c.name then project_names[c.name] = true end
      end
      local visible = {}
      for _, c in ipairs(shared) do
        if c and c.name and not project_names[c.name] then
          table.insert(visible, c)
        end
      end
      vim.g.dbs = visible
    else
      vim.g.dbs = nil
    end
  else
    vim.g.dbs = nil
  end

  -- Reset dadbod-ui's in-memory cache.
  pcall(vim.fn['db_ui#reset_state'])

  -- If the drawer is currently visible, close + reopen so the new save_location
  -- is picked up. Without this, the drawer renders from the OLD state because
  -- `:DBUI` typically fires before VimEnter (when run via `nvim -c "DBUI"`).
  local drawer_open = false
  for _, w in ipairs(vim.api.nvim_list_wins()) do
    local b = vim.api.nvim_win_get_buf(w)
    if vim.bo[b].filetype == 'dbui' then
      drawer_open = true; break
    end
  end
  if drawer_open then
    pcall(vim.cmd, 'DBUIClose')
    pcall(vim.cmd, 'DBUI')
  end

  -- Re-arm the autoreloader so it watches the right files.
  pcall(function()
    local ar = require('features.dbui_autoreload')
    if ar.update_paths then
      ar.update_paths({ save_loc .. '/connections.json', shared_path })
    end
  end)

  -- Persist current state for :DBUIHealth.
  current.workspace = ws_name
  current.project   = proj
  current.save_location = save_loc
  current.shared_path = shared_path
  current.scope_label = scope_label

  if opts.notify and config.notify_on_change then
    vim.notify(('[DBUI] scope: %s'):format(scope_label), vim.log.levels.INFO)
  end
end

function M.status()
  return {
    workspace = current.workspace,
    project = current.project,
    save_location = current.save_location,
    shared_path = current.shared_path,
    scope_label = current.scope_label or 'unknown',
  }
end

function M.setup(opts)
  config = vim.tbl_deep_extend('force', config, opts or {})

  -- Initial application + react to cwd changes.
  vim.api.nvim_create_autocmd({ 'VimEnter', 'DirChanged' }, {
    callback = function(ev)
      -- VimEnter: silent. DirChanged: notify.
      M.apply({ notify = ev.event == 'DirChanged' })
    end,
  })

  -- Manual override: `:DBUIScope <name>` lets you force a workspace/project
  -- pair without cd'ing. `:DBUIScope` (no arg) re-runs auto-detection.
  vim.api.nvim_create_user_command('DBUIScope', function(args)
    if args.args == '' or args.args == 'auto' then
      M.apply({ notify = true })
      return
    end
    -- Parse `workspace` or `workspace/project`
    local ws, proj = args.args:match('^([^/]+)/?(.*)$')
    if not ws or ws == '' then
      vim.notify('[DBUI] :DBUIScope <workspace>[/<project>]', vim.log.levels.WARN)
      return
    end
    -- Verify the workspace exists in config
    local matched = false
    for _, w in ipairs(config.workspaces) do
      if w.name == ws then matched = true; break end
    end
    if not matched then
      vim.notify(('[DBUI] unknown workspace: %s'):format(ws), vim.log.levels.ERROR)
      return
    end
    -- Apply the requested scope directly (bypass cwd-based detection).
    M.apply({ force_workspace = ws, force_project = proj ~= '' and proj or nil, notify = true })
  end, {
    nargs = '?',
    complete = function()
      local out = { 'auto' }
      for _, w in ipairs(config.workspaces) do
        table.insert(out, w.name)
        -- Also suggest known projects under that workspace
        local pr = db_ui_root() .. '/workspaces/' .. w.name .. '/projects'
        if vim.fn.isdirectory(pr) == 1 then
          for _, p in ipairs(vim.fn.readdir(pr) or {}) do
            table.insert(out, w.name .. '/' .. p)
          end
        end
      end
      return out
    end,
    desc = 'Force the DBUI scope to a workspace (or workspace/project)',
  })
end

return M
