-- DBUI SSO login flow — single keystroke from inside nvim
--
--   :DBUILogin   pops a terminal split, runs the device-code SSO login,
--                refreshes the IAM token on success, autoreloader picks up
--                the new connections.json within ~1s.
--
--   <leader>dL (mnemonic: DB Login) — same as :DBUILogin
--
-- Also runs a passive timer that nags you ~5 minutes before SSO expires so
-- you don't get caught mid-query.

local M = {}

-- Company-specific AWS SSO identifiers are read from the environment so this
-- config stays generic and safe to publish. Set them in local/env/.env
-- (gitignored, synced privately) — see local/env/.env.example. When unset,
-- :DBUILogin reports "not configured" rather than running with placeholders.
local AWS_PROFILE     = vim.env.DBUI_AWS_PROFILE
local AWS_SSO_SESSION = vim.env.DBUI_AWS_SSO_SESSION

local DEFAULTS = {
  -- Login command, assembled from the env-provided profile/session. nil when
  -- unconfigured so M.login() can degrade gracefully instead of erroring.
  sso_login_cmd = (AWS_PROFILE and AWS_SSO_SESSION) and {
    'aws', 'sso', 'login',
    '--profile',     AWS_PROFILE,
    '--sso-session', AWS_SSO_SESSION,
    '--use-device-code',
    '--no-browser',
  } or nil,
  -- Script to run AFTER SSO login succeeds, to mint a fresh IAM token.
  token_refresh_cmd = function()
    local notes = vim.env.NOTES or ((vim.env.SYNC or vim.env.HOME) .. '/Vault')
    return { 'bash', notes .. '/db_ui/prod-db-token.sh' }
  end,
  -- Optional: command to kick the SSM tunnel service after token refresh.
  -- The tunnel is a separate systemd service that fails when SSO expires and
  -- auto-restarts; without an explicit kick the user might wait ~10s for the
  -- next auto-restart cycle. Set to nil to skip.
  tunnel_restart_cmd = { 'systemctl', '--user', 'restart', 'prod-db-tunnel' },
  -- Terminal split height (rows).
  term_height = 14,
  -- How often to poll SSO expiry, ms. 60s is enough.
  watcher_interval_ms = 60 * 1000,
  -- Warn when SSO has this many seconds left.
  warn_threshold_s = 300,
  -- For the SSO-expiry watcher: which start_url to match. From env (see above).
  sso_start_url = vim.env.DBUI_SSO_START_URL,
}

local config = vim.deepcopy(DEFAULTS)
local watcher_timer  ---@type uv.uv_timer_t?
local in_progress = false   -- guards against double :DBUILogin
local in_progress_since = 0 -- epoch seconds when in_progress was set to true
local last_warn_minute = 0  -- so we don't spam

function M.setup(opts)
  config = vim.tbl_deep_extend('force', config, opts or {})
end

-- ---------------------------------------------------------------------------
-- Login flow
-- ---------------------------------------------------------------------------

local function run_token_refresh()
  local cmd = type(config.token_refresh_cmd) == 'function'
              and config.token_refresh_cmd() or config.token_refresh_cmd

  -- Preflight: the refresh command's first element should be an executable
  -- or a readable script. If neither, surface a clear error rather than
  -- letting jobstart fail silently with code 127.
  local first = cmd[1] or ''
  local resolved = vim.fn.executable(first) == 1 and first or nil
  if not resolved and vim.fn.filereadable(first) == 1 then resolved = first end
  -- Also check arg-1 if first is 'bash' (the default form: { 'bash', '/path/to/script.sh' })
  if first == 'bash' and cmd[2] then
    if vim.fn.filereadable(cmd[2]) == 0 then
      vim.notify(
        ('[DBUI] Token refresh script %s not found. Configure features.dbui_sso with token_refresh_cmd.'):format(cmd[2]),
        vim.log.levels.ERROR)
      in_progress = false

      in_progress_since = 0
      return
    end
  end

  vim.notify('[DBUI] SSO login succeeded — refreshing IAM token…', vim.log.levels.INFO)
  vim.fn.jobstart(cmd, {
    stdout_buffered = true,
    stderr_buffered = true,
    on_exit = function(_, code)
      vim.schedule(function()
        if code == 0 then
          vim.notify(
            '[DBUI] IAM token refreshed. autoreloader will rebind buffers shortly.',
            vim.log.levels.INFO)
          -- Also kick the tunnel service so the user doesn't wait for the
          -- next systemd auto-restart cycle.
          if config.tunnel_restart_cmd then
            vim.fn.jobstart(config.tunnel_restart_cmd, {
              on_exit = function(_, tcode)
                vim.schedule(function()
                  if tcode == 0 then
                    vim.notify('[DBUI] SSM tunnel restarted.', vim.log.levels.INFO)
                  else
                    vim.notify(
                      ('[DBUI] Tunnel restart exited %d (it auto-restarts on its own; should recover within ~10s).'):format(tcode),
                      vim.log.levels.WARN)
                  end
                end)
              end,
            })
          end
        elseif code == 127 then
          vim.notify(
            ('[DBUI] Token refresh command not found (exit 127): %s'):format(
              table.concat(cmd, ' ')),
            vim.log.levels.ERROR)
        else
          vim.notify(
            ('[DBUI] Token refresh exited %d. Run `%s` manually to diagnose.'):format(
              code, table.concat(cmd, ' ')),
            vim.log.levels.ERROR)
        end
        in_progress = false

        in_progress_since = 0
      end)
    end,
  })
end

function M.login()
  -- Not configured: no AWS profile/session in the environment. Nothing to run.
  if not config.sso_login_cmd then
    vim.notify(
      '[DBUI] SSO login not configured. Set DBUI_AWS_PROFILE and '
      .. 'DBUI_AWS_SSO_SESSION in local/env/.env (see local/env/.env.example).',
      vim.log.levels.WARN)
    return
  end

  if in_progress then
    -- Self-heal: if in_progress has been true for >10 minutes, something
    -- went sideways (user killed the terminal, on_exit never fired, etc.).
    -- Reset and proceed.
    local stale_after = 10 * 60
    if in_progress_since > 0 and (os.time() - in_progress_since) > stale_after then
      vim.notify(
        '[DBUI] login was marked in-progress for >10 min — auto-resetting and retrying.',
        vim.log.levels.WARN)
      in_progress = false

      in_progress_since = 0
      in_progress_since = 0
    else
      vim.notify(
        '[DBUI] login already in progress. Run :DBUIAbortLogin to reset if it\'s stuck.',
        vim.log.levels.WARN)
      return
    end
  end

  -- Preflight: confirm the aws binary exists. Otherwise spawning the terminal
  -- shows a vague "command not found" deep in the term split.
  if vim.fn.executable(config.sso_login_cmd[1]) == 0 then
    vim.notify(
      ('[DBUI] `%s` not in $PATH. Install the AWS CLI v2 (or override config.sso_login_cmd).'):format(
        config.sso_login_cmd[1]),
      vim.log.levels.ERROR)
    return
  end

  in_progress = true
  in_progress_since = os.time()

  -- Remember where we came from so we can return there.
  local return_win = vim.api.nvim_get_current_win()

  -- Open a horizontal terminal split at the bottom.
  vim.cmd(('botright %dsplit'):format(config.term_height))
  vim.cmd('enew')  -- fresh buffer in the new split

  local term_buf = vim.api.nvim_get_current_buf()
  vim.bo[term_buf].buflisted = false
  vim.bo[term_buf].buftype = ''  -- normal buf so termopen can attach

  vim.notify(
    '[DBUI] Opening browser-less SSO login. Watch the terminal below for a ' ..
    'device-code URL, open it in your browser, approve, then return here — ' ..
    'token refresh runs automatically.',
    vim.log.levels.INFO)

  local job_id = vim.fn.termopen(config.sso_login_cmd, {
    on_exit = function(_, code, _)
      vim.schedule(function()
        if code == 0 then
          vim.defer_fn(function()
            if vim.api.nvim_buf_is_valid(term_buf) then
              for _, w in ipairs(vim.fn.win_findbuf(term_buf)) do
                pcall(vim.api.nvim_win_close, w, true)
              end
              pcall(vim.api.nvim_buf_delete, term_buf, { force = true })
            end
          end, 1500)
          run_token_refresh()
        else
          vim.notify(
            ('[DBUI] SSO login exited %d. Terminal kept open for diagnostics.'):format(code),
            vim.log.levels.ERROR)
          in_progress = false

          in_progress_since = 0
        end
      end)
    end,
  })
  if job_id <= 0 then
    vim.notify('[DBUI] failed to spawn login terminal', vim.log.levels.ERROR)
    in_progress = false

    in_progress_since = 0
    return
  end

  -- Return cursor to the original window so the user can keep working.
  -- The terminal updates in the background. To interact with it (rare — the
  -- whole flow is browser-side), use <C-w>j then `i`.
  if vim.api.nvim_win_is_valid(return_win) then
    pcall(vim.api.nvim_set_current_win, return_win)
  end
end

-- ---------------------------------------------------------------------------
-- Proactive expiry watcher
-- ---------------------------------------------------------------------------

local function read_expiry_seconds_left()
  local cache_dir = vim.env.HOME .. '/.aws/sso/cache'
  for _, f in ipairs(vim.fn.glob(cache_dir .. '/*.json', false, true)) do
    local raw = table.concat(vim.fn.readfile(f), '\n')
    local ok, data = pcall(vim.json.decode, raw)
    if ok and data.startUrl == config.sso_start_url and data.expiresAt then
      local y, mo, d, h, mi, s = data.expiresAt:match(
        '^(%d+)-(%d+)-(%d+)T(%d+):(%d+):(%d+)Z?$')
      if y then
        local t = os.time({ year=y, month=mo, day=d, hour=h, min=mi, sec=s,
                            isdst=false })
        local now_utc = os.time(os.date('!*t'))
        return t - now_utc, data.expiresAt
      end
    end
  end
  return nil, nil
end

local function watcher_tick()
  if in_progress then return end
  local secs, iso = read_expiry_seconds_left()
  if not secs then return end
  if secs <= 0 then
    -- Only nag once per minute boundary
    local this_minute = os.time() / 60
    if math.floor(this_minute) ~= last_warn_minute then
      last_warn_minute = math.floor(this_minute)
      vim.notify(
        ('[DBUI] AWS SSO expired (%s). Run :DBUILogin to keep querying prod.'):format(iso),
        vim.log.levels.WARN)
    end
  elseif secs < config.warn_threshold_s then
    -- Approaching expiry: warn once every 60s
    local this_minute = math.floor(os.time() / 60)
    if this_minute ~= last_warn_minute then
      last_warn_minute = this_minute
      vim.notify(
        ('[DBUI] AWS SSO expires in %dm%ds. :DBUILogin to refresh.'):format(
          math.floor(secs/60), secs%60),
        vim.log.levels.WARN)
    end
  end
end

function M.start_watcher()
  if watcher_timer then return end
  watcher_timer = vim.uv.new_timer()
  watcher_timer:start(
    config.watcher_interval_ms,                -- first tick after one interval
    config.watcher_interval_ms,                -- repeat interval
    vim.schedule_wrap(watcher_tick))
  vim.api.nvim_create_autocmd('VimLeavePre', {
    once = true,
    callback = function() M.stop_watcher() end,
  })
end

function M.stop_watcher()
  if watcher_timer then
    pcall(function() watcher_timer:stop() end)
    if watcher_timer and not watcher_timer:is_closing() then
      pcall(function() watcher_timer:close() end)
    end
    watcher_timer = nil
  end
end

-- Recover from a stuck `in_progress = true` state (e.g., user killed the term
-- split manually without the on_exit ever firing).
function M.abort()
  in_progress = false

  in_progress_since = 0
  in_progress_since = 0
  vim.notify('[DBUI] SSO login state reset.', vim.log.levels.INFO)
end

-- For :DBUIHealth integration
function M.status()
  local secs, iso = read_expiry_seconds_left()
  return {
    watcher_active = watcher_timer ~= nil,
    in_progress = in_progress,
    sso_expires_in_s = secs,
    sso_expires_at = iso,
  }
end

return M
