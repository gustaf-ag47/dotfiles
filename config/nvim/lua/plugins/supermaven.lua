-- Supermaven: fast AI inline ghost-text completion
-- Free tier, 1M token context window, ~250ms latency
-- Use Alt+l to accept (avoids Tab conflict with nvim-cmp)

return {
  {
    'supermaven-inc/supermaven-nvim',
    enabled = true,
    event = 'InsertEnter',
    opts = {
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
    },
  },
}
