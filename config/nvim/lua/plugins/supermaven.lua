-- Supermaven: fast AI inline ghost-text completion
-- Free tier, 1M token context window, ~250ms latency
-- Use Alt+l to accept (avoids Tab conflict with nvim-cmp)

return {
  {
    'supermaven-inc/supermaven-nvim',
    enabled = true,
    event = 'InsertEnter',
    config = function()
      require('supermaven-nvim').setup {
        keymaps = {
          accept_suggestion = '<M-l>', -- Alt+l — no conflict with cmp Tab
          clear_suggestion = '<C-]>',
          accept_word = '<M-w>',
        },
        ignore_filetypes = { 'TelescopePrompt', 'oil', 'dbui', 'help' },
        color = {
          suggestion_color = '#9399b2',
          cterm = 244,
        },
        log_level = 'off',
        disable_inline_completion = false,
        disable_keymaps = false,
      }

      local lifecycle = require 'supermaven-nvim.binary.binary_handler'
      lifecycle.open_popup = function() end
      lifecycle.show_activation_message = function() end

      -- Memory-leak guards. See docs/nvim-memory-leak.md (13 GB nvim, 2026-09-26).
      --
      -- Upstream writes the WHOLE buffer to sm-agent's stdin on every edit via
      -- uv.write() and never checks the result. When sm-agent stops draining
      -- stdin, libuv queues every payload in nvim's heap forever: reproduced at
      -- ~6.5 KB queued per keystroke on a 6 KB file (linear in buffer size).
      -- Guard 1: if the stdin write queue passes a cap, the agent is wedged —
      -- SIGKILL it, close the pipes (frees the queue) and start a fresh one.
      local max_queue = (vim.g.supermaven_max_write_queue_mb or 16) * 1024 * 1024
      local orig_send_json = lifecycle.send_json
      lifecycle.send_json = function(self, msg)
        local stdin = self.stdin
        if not stdin or stdin:is_closing() then
          return -- mid-restart; drop
        end
        if stdin:get_write_queue_size() > max_queue then
          local queued = stdin:get_write_queue_size()
          -- SIGKILL only: upstream's exit callback then reaps + clears
          -- self.handle (closing it here would leave a zombie).
          if self.handle then
            pcall(self.handle.kill, self.handle, 9)
          end
          for _, pipe in ipairs { self.stdin, self.stdout, self.stderr } do
            if pipe and not pipe:is_closing() then
              pipe:close() -- cancels + frees the pending writes
            end
          end
          self.changed_document_list = {}
          self.state_map = {}
          self.last_state = nil
          vim.defer_fn(function()
            if self.handle == nil then
              self:start_binary()
            end -- else check_process() restarts it on the next poll
          end, 500)
          vim.schedule(function()
            vim.notify(
              ('sm-agent stopped reading stdin (%d KB queued) — restarted it'):format(math.floor(queued / 1024)),
              vim.log.levels.WARN,
              { title = 'supermaven' }
            )
          end)
          return
        end
        return orig_send_json(self, msg)
      end

      -- Guard 2: only real file buffers, and not huge ones. Upstream runs on
      -- CursorMoved/TextChanged in EVERY buffer (terminals, scratch, logs) and
      -- serialises the full text each time (its own cap is 10 MB).
      local max_bytes = 1024 * 1024
      local orig_on_update = lifecycle.on_update
      lifecycle.on_update = function(self, buffer, file_name, event_type)
        if not vim.api.nvim_buf_is_valid(buffer) or vim.bo[buffer].buftype ~= '' then
          return
        end
        if vim.api.nvim_buf_get_offset(buffer, vim.api.nvim_buf_line_count(buffer)) > max_bytes then
          return
        end
        return orig_on_update(self, buffer, file_name, event_type)
      end
    end,
  },
}
