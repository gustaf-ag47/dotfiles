-- Database UI: vim-dadbod + dadbod-ui + dadbod-completion
-- Connections defined per-project in .nvim.lua via vim.g.dbs (no credentials in dotfiles).
-- Global toggle: <leader>du  |  In SQL buffers: <leader>e executes, \w saves query.

return {
  { 'tpope/vim-dadbod', lazy = true },

  { 'kristijanhusak/vim-dadbod-completion', lazy = true },

  {
    'kristijanhusak/vim-dadbod-ui',
    dependencies = { 'tpope/vim-dadbod', 'kristijanhusak/vim-dadbod-completion' },
    -- Only commands that REQUIRE vim-dadbod-ui to be loaded go in `cmd =`.
    -- DBUIHealth / DBUILogin / DBUIAutoReloadStatus are registered in init()
    -- and don't need the plugin loaded — putting them in cmd= here would cause
    -- lazy.nvim's stub-deletion-on-first-trigger to wipe them out.
    -- IMPORTANT: only commands that REQUIRE the plugin to be loaded belong here.
    -- Custom commands registered in init() (DBUIReload, DBUIHealth, DBUILogin,
    -- DBUIAbortLogin, DBUIAutoReloadStatus) MUST NOT be listed because lazy.nvim
    -- creates stub commands for each entry in `cmd`, and when ANY stub fires, it
    -- DELETES ALL stubs in this list. Stubs registered with the same name as our
    -- init-registered commands get deleted along with them, leaving the command
    -- unbound until the next restart. (Found this the hard way — see the doc/06
    -- iteration log for the symptom of "DBUIReload silently doesn't exist".)
    cmd = { 'DBUI', 'DBUIToggle', 'DBUIAddConnection', 'DBUIFindBuffer' },
    keys = {
      { '<leader>du', '<cmd>DBUIToggle<cr>', desc = 'DB: Toggle UI' },
      { '<leader>da', '<cmd>DBUIAddConnection<cr>', desc = 'DB: Add connection' },
      { '<leader>df', '<cmd>DBUIFindBuffer<cr>', desc = 'DB: Find buffer' },
      { '<leader>dr', '<cmd>DBUIReload<cr>', desc = 'DB: Reload connections (re-read token)' },
      { '<leader>dL', '<cmd>DBUILogin<cr>', desc = 'DB: AWS SSO login + token refresh' },
      { '<leader>dh', '<cmd>DBUIHealth<cr>', desc = 'DB: Health check' },
    },
    init = function()
      -- vim-dadbod's MySQL adapter hardcodes the `mysql` client name. On Arch
      -- that's a MariaDB symlink that prints a "Deprecated program name … use
      -- '/usr/bin/mariadb' instead" warning on every call, polluting query
      -- output. Prepend our shim dir (config/nvim/bin/mysql → exec mariadb) to
      -- nvim's PATH so dadbod resolves the quiet wrapper instead. Scoped to nvim.
      pcall(function()
        local shim_dir = vim.fn.stdpath 'config' .. '/bin'
        if vim.fn.isdirectory(shim_dir) == 1 and not (':' .. vim.env.PATH .. ':'):find(':' .. vim.pesc(shim_dir) .. ':', 1, false) then
          vim.env.PATH = shim_dir .. ':' .. vim.env.PATH
        end
      end)

      -- Register :checkhealth provider for DBUI
      pcall(function()
        vim.health.register_report('dbui', function()
          require('features.dbui_checkhealth').check()
        end)
      end)

      -- Must be set before the plugin loads.
      -- Default save_location is the global $NOTES/db_ui. The project module
      -- (features.dbui_project) takes over on VimEnter/DirChanged and switches
      -- this to a workspace-/project-specific dir based on cwd.
      local notes = os.getenv 'NOTES' or (os.getenv 'SYNC' or os.getenv 'HOME') .. '/Vault'
      vim.g.db_ui_save_location = notes .. '/db_ui'

      -- Project-aware scope switcher: drawer auto-switches based on cwd so
      -- you only see DBs relevant to the workspace/project you're in.
      pcall(function()
        -- Workspace definitions (paths, git-remote patterns, connection names)
        -- are personal/company-specific, so they live in a gitignored private
        -- module kept on disk and synced via Syncthing — never committed. See
        -- config/nvim/lua/dbui_private.lua.example for the shape. Falls back to
        -- an empty workspace list when absent so the public config still loads.
        local ok_priv, priv = pcall(require, 'dbui_private')
        require('features.dbui_project').setup {
          workspaces = (ok_priv and priv.workspaces) or {},
        }
      end)

      -- :DBUIReload — force a re-read of connections.json (e.g. after refresh-prod-token.sh
      -- rotates the IAM token). dadbod-ui caches the connection instance for the whole
      -- session, so :DBUIClose + :DBUIToggle keeps the STALE token. reset_state drops the
      -- cached instance; reopening repopulates from connections.json with the fresh token.
      vim.api.nvim_create_user_command('DBUIReload', function()
        -- Order matters! reset_state THEN close THEN open. With close-then-reset,
        -- dadbod-ui keeps the OLD populated dbs from the pre-close state (because
        -- close's s:init() walks through the existing instance) and a subsequent
        -- :DBUI doesn't re-populate. Verified empirically against the project-
        -- aware scope feature where vim.g.dbs gets rewritten between calls.
        vim.fn['db_ui#reset_state']()
        pcall(vim.cmd, 'DBUIClose')
        vim.cmd 'DBUI'
        vim.notify('DBUI reloaded — connections.json re-read', vim.log.levels.INFO)
      end, { desc = 'Reload DBUI connections (re-read connections.json / refreshed token)' })

      -- Auto-reload on connections.json change (RDS IAM token rotation, etc.)
      -- Watcher starts the first time DBUI is opened and lives until VimLeavePre.
      local autoreload_started = false
      vim.api.nvim_create_autocmd('FileType', {
        pattern = 'dbui',
        callback = function()
          if autoreload_started then
            return
          end
          autoreload_started = true
          local ok, mod = pcall(require, 'features.dbui_autoreload')
          if ok then
            mod.start()
          end
        end,
      })
      vim.api.nvim_create_user_command('DBUIAutoReloadStatus', function()
        local ok, mod = pcall(require, 'features.dbui_autoreload')
        if not ok then
          return vim.notify('autoreload module not loaded', vim.log.levels.WARN)
        end
        local s = mod.status()
        vim.notify(vim.inspect(s), vim.log.levels.INFO)
      end, { desc = 'Show DBUI auto-reload watcher status' })

      -- :DBUIHealth — single command that probes every layer:
      --   SSO valid? tunnel up? token fresh? autoreloader active? cmp wired?
      -- Returns a multi-line report with ✓/⚠/✗ marks and remediation hints.
      vim.api.nvim_create_user_command('DBUIHealth', function()
        local ok, mod = pcall(require, 'features.dbui_health')
        if not ok then
          return vim.notify('features.dbui_health failed to load: ' .. tostring(mod), vim.log.levels.ERROR)
        end
        local report, _ = mod.report()
        -- Multi-line output: print to :messages so it persists; vim.notify
        -- would flash and disappear. Each line is also visible immediately.
        for line in report:gmatch '[^\n]+' do
          vim.api.nvim_echo({ { line } }, true, {})
        end
      end, { desc = 'Show DBUI health (SSO, tunnel, token, autoreloader, cmp)' })

      -- :DBUILogin (and <leader>dL) — pops a terminal split, runs the SSO
      -- device-code login, on success refreshes the IAM token, autoreloader
      -- picks up the new connections.json. Avoids the context switch out of
      -- nvim to do `aws sso login && prod-db-token.sh && :DBUIReload`.
      vim.api.nvim_create_user_command('DBUILogin', function()
        local ok, mod = pcall(require, 'features.dbui_sso')
        if not ok then
          return vim.notify('features.dbui_sso failed to load: ' .. tostring(mod), vim.log.levels.ERROR)
        end
        mod.login()
      end, { desc = 'AWS SSO login + IAM token refresh (in-editor terminal split)' })

      -- Recovery hatch for when in_progress state gets stuck (e.g., user
      -- killed the terminal split manually without on_exit ever firing).
      vim.api.nvim_create_user_command('DBUIAbortLogin', function()
        pcall(function()
          require('features.dbui_sso').abort()
        end)
      end, { desc = 'Reset stuck SSO-login state' })

      vim.keymap.set('n', '<leader>dL', '<cmd>DBUILogin<cr>', { desc = 'DB: AWS SSO login + token refresh' })

      -- Proactive SSO expiry watcher. Polls ~/.aws/sso/cache/*.json every 60s.
      -- Nags via vim.notify when SSO has <5 min left or has expired.
      vim.schedule(function()
        local ok, mod = pcall(require, 'features.dbui_sso')
        if ok then
          mod.start_watcher()
        end
      end)

      vim.g.db_ui_use_nerd_fonts = 1
      vim.g.db_ui_winwidth = 35
      vim.g.db_ui_win_position = 'left'
      vim.g.db_ui_show_database_icon = 1
      vim.g.db_ui_disable_progress_bar = 1 -- jittery on slow networks (Aurora over SSM)

      -- Do NOT auto-execute on :w — dangerous for DML. Use <leader>e explicitly.
      vim.g.db_ui_execute_on_save = 0
      -- Do NOT auto-run table helpers on expand — saves unwanted DB round-trips.
      vim.g.db_ui_auto_execute_table_helpers = 0

      -- ----------------------------------------------------------------------
      -- Prod DML/DDL guard (extracted to features/dbui_dml_guard.lua so the
      -- parser is unit-testable from the regression suite without a DB).
      -- See that module's header for the full parsing rationale.
      -- ----------------------------------------------------------------------
      pcall(function()
        require('features.dbui_dml_guard').setup {
          -- substring match on lowercased connection name
          prod_tags = { 'prod' },
        }
      end)

      -- ----------------------------------------------------------------------
      -- Drawer filter: dadbod-ui MERGES every connection source (g:dbs +
      -- connections.json + env) into one drawer, so there's no clean way to
      -- "hide" entries from the file at runtime without swapping g:db_ui_save_location
      -- (which loses saved-query subdirs) or rewriting the file (race vs.
      -- prod-db-token.service). Instead of providing a broken :DBUIScope, prefer:
      --   * Press `/` in the drawer — vim's built-in incremental search jumps you
      --     to the next matching connection name. Works flawlessly.
      --   * Press `H` on a connection — shows which source it came from.
      --   * `:bn` / `:bp` cycle open query buffers (drawer is just a buffer too).
      -- ----------------------------------------------------------------------

      -- MySQL table helpers (appended to built-in Count/Indexes/FK/PK)
      vim.g.db_ui_table_helpers = {
        mysql = {
          List = 'SELECT * FROM `{table}` LIMIT 200',
          Count = 'SELECT COUNT(*) AS total FROM `{table}`',
          Describe = 'DESCRIBE `{table}`',
          ['Show Create'] = 'SHOW CREATE TABLE `{table}`',
          -- {last_query} is the previous query — Explain without retyping
          Explain = 'EXPLAIN {last_query}',
          ['Table Status'] = "SHOW TABLE STATUS LIKE '{table}'",
        },
      }

      -- NOTE: cmp source wiring for SQL/mysql buffers (sql_dadbod +
      -- vim-dadbod-completion + the context-aware entry_filter that hides Field
      -- and Function items after FROM/JOIN/INTO/UPDATE/TABLE/USING) lives in
      -- lua/lang/sql.lua. That autocmd is the one that wins on the
      -- FileType={sql,mysql,plsql} event because it fires last in the lazy load
      -- order. An earlier cmp.setup.buffer here was silently overridden by it.

      -- SQL buffer keymaps: execute query, save query
      vim.api.nvim_create_autocmd('FileType', {
        pattern = { 'sql', 'mysql', 'plsql' },
        callback = function(ev)
          local opts = { buffer = ev.buf, silent = true }
          -- Execute query under cursor (normal) or selection (visual) via DBUI plug
          vim.keymap.set('n', '<leader>e', '<Plug>(DBUI_ExecuteQuery)', opts)
          vim.keymap.set('v', '<leader>e', '<Plug>(DBUI_ExecuteQuery)', opts)
          -- Save query permanently to db_ui_save_location
          vim.keymap.set('n', '<leader>W', '<Plug>(DBUI_SaveQuery)', opts)
          -- Edit bind parameters (for :variable syntax)
          vim.keymap.set('n', '<leader>be', '<Plug>(DBUI_EditBindParameters)', opts)
        end,
      })
    end,
  },
}
