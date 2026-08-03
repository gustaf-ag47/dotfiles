-- Centralized notification API — all vim.notify calls should go through here.
--
-- This wrapper ensures:
--   1. Notifications issued during startup are vim.schedule-wrapped (avoids "Press ENTER" prompts)
--   2. Consistent formatting and level handling across the codebase
--   3. Single point to add telemetry, filtering, or output redirection later
--
-- Usage:
--   local notify = require('core.notify')
--   notify.info('some message')
--   notify.warn('a warning', { title = 'context' })
--   notify.error('an error')
--   notify.success('done!')
--   notify.raw('custom message', vim.log.levels.DEBUG, { opts })  -- raw vim.notify
--
-- At startup, all calls are vim.schedule-wrapped. After UI is ready, calls are immediate.

local M = {}

-- Detect if we're in the startup phase (before VimEnter)
local in_startup = true
vim.api.nvim_create_autocmd('VimEnter', {
  callback = function()
    in_startup = false
  end,
  once = true,
})

-- Helper: wrap a notification call in vim.schedule if in startup
local function schedule_if_startup(f)
  if in_startup then
    vim.schedule(f)
  else
    f()
  end
end

-- Raw vim.notify call (schedule-wrapped if in startup)
function M.raw(message, level, opts)
  schedule_if_startup(function()
    vim.notify(message, level, opts)
  end)
end

-- Convenience shortcuts
function M.info(message, opts)
  M.raw(message, vim.log.levels.INFO, opts or {})
end

function M.warn(message, opts)
  M.raw(message, vim.log.levels.WARN, opts or {})
end

function M.error(message, opts)
  M.raw(message, vim.log.levels.ERROR, opts or {})
end

function M.debug(message, opts)
  M.raw(message, vim.log.levels.DEBUG, opts or {})
end

-- "Success" is less common but nice for SSO login, test results, etc.
-- Uses INFO level since there's no SUCCESS level.
function M.success(message, opts)
  local merged = opts or {}
  merged.title = merged.title or 'Success'
  M.raw(message, vim.log.levels.INFO, merged)
end

return M
