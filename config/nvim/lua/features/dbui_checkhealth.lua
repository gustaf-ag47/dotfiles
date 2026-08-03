-- DBUI checkhealth integration — register with vim.health for :checkhealth
--
-- Provides a health check provider so `:checkhealth` shows DBUI status.
-- Complements the custom :DBUIHealth command.

local M = {}

function M.check()
  vim.health.start('DBUI (Dadbod UI automation)')

  -- Scope detection
  local proj_status = require('features.dbui_project').status()
  if proj_status and proj_status.workspace then
    vim.health.ok(string.format('Scope: %s/%s', proj_status.workspace, proj_status.project or '(shared)'))
  else
    vim.health.warn('Workspace/project scope not detected')
  end

  -- Autoreloader
  local ar_status = require('features.dbui_autoreload').status()
  if ar_status and ar_status.watcher_count and ar_status.watcher_count > 0 then
    vim.health.ok(string.format('Autoreloader: %d watcher(s) active', ar_status.watcher_count))
  else
    vim.health.info('Autoreloader: not yet active (fires on first DB draw)')
  end

  -- SSO
  local sso_status = require('features.dbui_sso').status()
  if sso_status then
    if sso_status.watcher_active then
      local mins_left = math.floor((sso_status.sso_expires_in_s or 0) / 60)
      if mins_left > 5 then
        vim.health.ok(string.format('SSO: valid, ~%d min left', mins_left))
      elseif mins_left > 0 then
        vim.health.warn(string.format('SSO: expiring soon (~%d min)', mins_left))
      else
        vim.health.error('SSO: expired — run :DBUILogin')
      end
    else
      vim.health.info('SSO watcher not yet started')
    end
  end

  -- DML Guard
  local guard_ok, guard_module = pcall(require, 'features.dbui_dml_guard')
  if guard_ok then
    vim.health.ok('DML guard: installed')
  else
    vim.health.error('DML guard: failed to load')
  end

  vim.health.start('DBUI Dependencies')

  -- vim-dadbod
  if vim.fn.executable('mysql') == 1 then
    vim.health.ok('MySQL CLI: found')
  else
    vim.health.warn('MySQL CLI: not in PATH (some operations may be limited)')
  end

  -- AWS CLI (for SSO)
  if vim.fn.executable('aws') == 1 then
    vim.health.ok('AWS CLI: found')
  else
    vim.health.error('AWS CLI: required for :DBUILogin (SSO flow)')
  end

  -- Refresh script
  local notes = vim.env.NOTES or ((vim.env.SYNC or vim.env.HOME) .. '/Vault')
  local token_script = notes .. '/db_ui/prod-db-token.sh'
  if vim.fn.filereadable(token_script) == 1 then
    vim.health.ok('Token refresh script: found')
  else
    vim.health.warn(string.format('Token refresh script: not found at %s', token_script))
  end
end

return M
