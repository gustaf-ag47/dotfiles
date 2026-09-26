-- Memory guard feature module
-- Samples this Neovim server's RSS once a minute and warns when it crosses a
-- threshold, so a runaway heap can't silently grow to 13 GB again.
-- Background: docs/nvim-memory-leak.md
--
-- Warns (vim.notify + a line in stdpath('log')/nvim.log) the first time RSS
-- exceeds `threshold_mb`, then again each time it grows by another `step_mb`.
-- Knobs: vim.g.memguard_threshold_mb (default 2048), vim.g.memguard_step_mb
-- (default 1024), vim.g.memguard_disable = true to switch it off.
-- :MemGuard prints the current sample on demand.

local M = {}

local INTERVAL_MS = 60 * 1000

local timer = nil
local next_warn_kb = nil

local function rss_kb()
  local f = io.open('/proc/self/status', 'r')
  if not f then
    return nil
  end
  local status = f:read '*a'
  f:close()
  return tonumber(status:match 'VmRSS:%s*(%d+)')
end

-- One-line snapshot of the usual suspects, for the log.
local function snapshot(kb)
  local sm = package.loaded['supermaven-nvim.binary.binary_handler']
  local sm_state = 'not loaded'
  if sm then
    local n = 0
    for _ in pairs(sm.state_map or {}) do
      n = n + 1
    end
    sm_state = ('running=%s states=%d'):format(tostring(sm.handle ~= nil), n)
  end
  local write_q = 'n/a'
  if sm and sm.stdin and sm.stdin.get_write_queue_size then
    local ok, q = pcall(sm.stdin.get_write_queue_size, sm.stdin)
    write_q = ok and (q .. 'B') or 'n/a'
  end
  return ('rss=%dMB lua=%dMB bufs=%d supermaven[%s stdin_queue=%s]'):format(
    math.floor(kb / 1024),
    math.floor(collectgarbage 'count' / 1024),
    #vim.api.nvim_list_bufs(),
    sm_state,
    write_q
  )
end

local function log_line(msg)
  local f = io.open(vim.fn.stdpath 'log' .. '/nvim.log', 'a')
  if f then
    f:write(('WRN %s memguard.%d %s\n'):format(os.date '%Y-%m-%dT%H:%M:%S', vim.fn.getpid(), msg))
    f:close()
  end
end

local function tick()
  local kb = rss_kb()
  if not kb then
    return
  end
  local threshold_kb = (vim.g.memguard_threshold_mb or 2048) * 1024
  local step_kb = (vim.g.memguard_step_mb or 1024) * 1024
  next_warn_kb = next_warn_kb or threshold_kb
  if kb < next_warn_kb then
    return
  end
  next_warn_kb = kb + step_kb
  local msg = snapshot(kb)
  log_line(msg)
  vim.notify(('Neovim memory is high: %s\nRestart this nvim; see docs/nvim-memory-leak.md'):format(msg), vim.log.levels.WARN, { title = 'memguard' })
end

M.setup = function()
  if vim.g.memguard_disable or timer or vim.fn.has 'linux' == 0 then
    return
  end
  timer = vim.uv.new_timer()
  timer:start(INTERVAL_MS, INTERVAL_MS, vim.schedule_wrap(tick))
  timer:unref() -- never keep the loop alive on its own

  vim.api.nvim_create_user_command('MemGuard', function()
    local kb = rss_kb()
    print(kb and snapshot(kb) or 'memguard: /proc/self/status unavailable')
  end, { desc = 'Show Neovim memory usage (memguard)' })
end

return M
