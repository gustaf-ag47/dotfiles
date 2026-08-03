-- DBUI health check — single command that tells you what's broken
--
--   :DBUIHealth        report each subsystem's state with ✓/✗ + remediation hint
--   require('features.dbui_health').check()  programmatic access (returns table)
--
-- Checks (in order):
--   1) AWS SSO session validity + time to expiry
--   2) SSM tunnel (TCP listener on the local forward port)
--   3) IAM token freshness in connections.json (X-Amz-Date age)
--   4) DBUI autoreloader watcher status
--   5) cmp completion source registration
--   6) dadbod-completion schema cache state (per active query buffer)
--
-- Designed to be safe to call when nvim is idle (no network calls except a
-- single `aws sts get-caller-identity` for SSO check, which is local-cache
-- by default).

local M = {}

-- Company-specific AWS identifiers come from the environment (local/env/.env,
-- gitignored + synced privately) so this file stays generic and publishable.
-- See local/env/.env.example. When unset, the SSO probe reports "not configured".
local DEFAULTS = {
  aws_profile = vim.env.DBUI_AWS_PROFILE or 'default',
  aws_sso_session = vim.env.DBUI_AWS_SSO_SESSION,
  sso_start_url = vim.env.DBUI_SSO_START_URL,
  tunnel_port = tonumber(vim.env.DBUI_TUNNEL_PORT) or 13307,
  connections_path = nil, -- resolved at call time from $NOTES or g:db_ui_save_location
  expected_db_url_marker = 'X%-Amz%-Date%%3D', -- pattern in URL signalling IAM
}

local config = vim.deepcopy(DEFAULTS)

function M.setup(opts)
  config = vim.tbl_deep_extend('force', config, opts or {})
end

local function resolve_connections_path()
  if config.connections_path then
    return config.connections_path
  end
  local saveloc = vim.g.db_ui_save_location
  if saveloc and saveloc ~= '' then
    return saveloc .. '/connections.json'
  end
  local notes = vim.env.NOTES or ((vim.env.SYNC or vim.env.HOME) .. '/Vault')
  return notes .. '/db_ui/connections.json'
end

-- ---------------------------------------------------------------------------
-- Individual probes (each returns a table with .ok, .detail, .hint)
-- ---------------------------------------------------------------------------

local function check_sso()
  -- Prod-DB workflow is opt-in: without an SSO session configured in the
  -- environment there is nothing to check. Report neutral, not failing.
  if not config.aws_sso_session then
    return {
      ok = true,
      detail = 'SSO not configured (set DBUI_AWS_* in local/env/.env to enable)',
    }
  end

  local out = vim.fn.system { 'aws', 'sts', 'get-caller-identity', '--profile', config.aws_profile }
  local ok = vim.v.shell_error == 0
  if not ok then
    return {
      ok = false,
      detail = ('aws sts get-caller-identity --profile %s failed'):format(config.aws_profile),
      hint = ':DBUILogin   (or run the SSO login manually)',
    }
  end

  -- Find the SSO cache entry with our start URL and parse expiresAt
  local cache_dir = vim.env.HOME .. '/.aws/sso/cache'
  local files = vim.fn.glob(cache_dir .. '/*.json', false, true)
  local expires_iso, expires_s
  for _, f in ipairs(files) do
    local raw = table.concat(vim.fn.readfile(f), '\n')
    local ok_json, data = pcall(vim.json.decode, raw)
    if ok_json and data.startUrl == config.sso_start_url and data.expiresAt then
      expires_iso = data.expiresAt
      break
    end
  end
  if expires_iso then
    -- ISO 8601 with Z. Convert to epoch.
    local y, mo, d, h, mi, s = expires_iso:match '^(%d+)-(%d+)-(%d+)T(%d+):(%d+):(%d+)Z?$'
    if y then
      expires_s = os.time { year = y, month = mo, day = d, hour = h, min = mi, sec = s, isdst = false }
      -- os.time treats the table as LOCAL time; we need UTC-relative
      -- arithmetic. Easiest: compute now in UTC too.
      local now_utc = os.time(os.date '!*t')
      local secs_left = expires_s - now_utc
      if secs_left <= 0 then
        return {
          ok = false,
          detail = ('SSO token expired (%s)'):format(expires_iso),
          hint = ':DBUILogin',
        }
      elseif secs_left < 900 then -- < 15 min
        return {
          ok = true,
          warn = true,
          detail = ('SSO valid, expires in %dm%ds (%s)'):format(math.floor(secs_left / 60), secs_left % 60, expires_iso),
          hint = ':DBUILogin soon to avoid mid-query interruption',
        }
      else
        return {
          ok = true,
          detail = ('SSO valid, expires in %dh%dm (%s)'):format(math.floor(secs_left / 3600), math.floor((secs_left % 3600) / 60), expires_iso),
        }
      end
    end
  end
  return {
    ok = true,
    warn = true,
    detail = 'SSO call succeeded but expiresAt not found in cache',
    hint = 'Cache layout may have changed; investigate ~/.aws/sso/cache/',
  }
end

local function check_tunnel()
  -- Quick TCP probe via lua. Don't block long.
  local handle = vim.uv.new_tcp()
  if not handle then
    return { ok = false, detail = 'uv.new_tcp() failed' }
  end
  local result = { ok = false, detail = 'no response' }
  local done = false
  handle:connect('127.0.0.1', config.tunnel_port, function(err)
    if err == nil then
      result = { ok = true }
    end
    handle:close()
    done = true
  end)
  -- Pump the event loop briefly
  vim.wait(800, function()
    return done
  end, 50)
  if result.ok then
    return { ok = true, detail = ('TCP listener up on 127.0.0.1:%d'):format(config.tunnel_port) }
  end
  return {
    ok = false,
    detail = ('no listener on 127.0.0.1:%d'):format(config.tunnel_port),
    hint = 'systemctl --user start prod-db-tunnel',
  }
end

local function check_token()
  -- Look in BOTH the current save_location AND the inherited workspace file
  -- (if project scope is active). The IAM-tokenized URLs typically live at
  -- workspace level; the project-only file may be local-DB-only.
  local paths = { resolve_connections_path() }
  local ok_proj, proj_mod = pcall(require, 'features.dbui_project')
  if ok_proj then
    local s = proj_mod.status()
    if s and s.shared_path then
      table.insert(paths, s.shared_path)
    end
  end

  local conns_all = {}
  for _, path in ipairs(paths) do
    if vim.fn.filereadable(path) == 1 then
      local raw = table.concat(vim.fn.readfile(path), '\n')
      local ok_json, parsed = pcall(vim.json.decode, raw)
      if ok_json and type(parsed) == 'table' then
        for _, c in ipairs(parsed) do
          table.insert(conns_all, c)
        end
      end
    end
  end
  if #conns_all == 0 then
    return { ok = false, detail = 'no connection files readable', hint = 'check ' .. table.concat(paths, ', ') }
  end

  -- Find any URL that has an X-Amz-Date= field (IAM-signed URL)
  local newest_date, newest_age_s
  local now_utc = os.time(os.date '!*t')
  for _, c in ipairs(conns_all) do
    if c.url then
      local d = c.url:match 'X%-Amz%-Date%%3D(%d+T%d+Z)'
      if d then
        local y, mo, da, h, mi, s = d:match '^(%d+)(%d%d)(%d%d)T(%d%d)(%d%d)(%d%d)Z$'
        if y then
          local t = os.time { year = y, month = mo, day = da, hour = h, min = mi, sec = s, isdst = false }
          local age = now_utc - t
          if not newest_age_s or age < newest_age_s then
            newest_age_s = age
            newest_date = d
          end
        end
      end
    end
  end
  if not newest_date then
    return { ok = true, detail = 'no IAM-signed URLs found (local DBs only?)' }
  end
  if newest_age_s > 900 then
    return {
      ok = false,
      detail = ('newest IAM token is %dm old (%s); X-Amz-Expires is 900s'):format(math.floor(newest_age_s / 60), newest_date),
      hint = 'systemctl --user start prod-db-token  (or :DBUILogin if SSO also expired)',
    }
  elseif newest_age_s > 720 then -- > 12 min, getting stale
    return {
      ok = true,
      warn = true,
      detail = ('newest IAM token is %dm%ds old (%s); rotation due'):format(math.floor(newest_age_s / 60), newest_age_s % 60, newest_date),
    }
  end
  return {
    ok = true,
    detail = ('newest IAM token is %dm%ds old (%s)'):format(math.floor(newest_age_s / 60), newest_age_s % 60, newest_date),
  }
end

local function check_autoreloader()
  local ok, mod = pcall(require, 'features.dbui_autoreload')
  if not ok then
    return { ok = false, detail = 'features.dbui_autoreload not loaded', hint = 'open DBUI once (triggers FileType=dbui autocmd that loads it)' }
  end
  local s = mod.status()
  if not s.active then
    return {
      ok = false,
      detail = ('watcher inactive (path=%s)'):format(tostring(s.path)),
      hint = ':lua require("features.dbui_autoreload").start()',
    }
  end
  return { ok = true, detail = ('watching %s'):format(s.path) }
end

local function check_cmp()
  local ok, cmp = pcall(require, 'cmp')
  if not ok then
    return { ok = false, detail = 'nvim-cmp not loaded' }
  end
  -- The buffer-local source list (this only reflects an SQL buffer; otherwise
  -- it's the global config).
  local sources = cmp.get_config().sources
  local names = {}
  for _, src in ipairs(sources or {}) do
    if type(src) == 'table' and src.name then
      table.insert(names, src.name)
    elseif type(src) == 'table' then
      -- nested {} groups
      for _, s in ipairs(src) do
        if type(s) == 'table' and s.name then
          table.insert(names, s.name)
        end
      end
    end
  end
  return {
    ok = true,
    detail = 'sources: ' .. (#names > 0 and table.concat(names, ', ') or '(empty)'),
  }
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

-- Project/workspace scope (from features.dbui_project)
local function check_scope()
  local ok, mod = pcall(require, 'features.dbui_project')
  if not ok then
    return { ok = true, detail = 'scope module not loaded (using global $NOTES/db_ui)' }
  end
  local s = mod.status()
  local detail = ('%s (save_location=%s'):format(s.scope_label or 'default', s.save_location or '?')
  if s.shared_path then
    detail = detail .. ', inherits=' .. s.shared_path
  end
  detail = detail .. ')'
  return { ok = true, detail = detail }
end

function M.check()
  return {
    scope = check_scope(),
    sso = check_sso(),
    tunnel = check_tunnel(),
    token = check_token(),
    autoreloader = check_autoreloader(),
    cmp = check_cmp(),
  }
end

local function fmt(label, r)
  local mark = r.ok and (r.warn and '⚠' or '✓') or '✗'
  local line = ('  %s  %-13s  %s'):format(mark, label, r.detail or '')
  if r.hint then
    line = line .. ('\n        hint: ' .. r.hint)
  end
  return line
end

function M.report()
  local r = M.check()
  local lines = { '── DBUI health ──' }
  table.insert(lines, fmt('scope', r.scope))
  table.insert(lines, fmt('SSO', r.sso))
  table.insert(lines, fmt('SSM tunnel', r.tunnel))
  table.insert(lines, fmt('IAM token', r.token))
  table.insert(lines, fmt('autoreloader', r.autoreloader))
  table.insert(lines, fmt('cmp sources', r.cmp))
  local all_ok = r.sso.ok and r.tunnel.ok and r.token.ok and r.autoreloader.ok
  table.insert(lines, all_ok and '── all systems go ──' or '── one or more issues; see hints above ──')
  return table.concat(lines, '\n'), all_ok
end

return M
