-- AI coding assistant: chat, inline transforms, test generation
-- Backend: Claude (Anthropic API key via ANTHROPIC_API_KEY env var)
-- Pairs with supermaven.lua for inline ghost-text completion

return {
  {
    'olimorris/codecompanion.nvim',
    dependencies = {
      'nvim-lua/plenary.nvim',
      'nvim-treesitter/nvim-treesitter',
    },
    event = 'VeryLazy',
    opts = {
      adapters = {
        anthropic = function()
          return require('codecompanion.adapters').extend('anthropic', {
            schema = {
              model = { default = 'claude-sonnet-4-6' },
            },
          })
        end,
      },
      strategies = {
        chat = { adapter = 'anthropic' },
        inline = { adapter = 'anthropic' },
        cmd = { adapter = 'anthropic' },
      },
      display = {
        chat = {
          window = { layout = 'vertical', width = 0.35 },
        },
        diff = { provider = 'mini_diff' },
      },
    },
    keys = {
      { '<leader>ac', '<cmd>CodeCompanionChat Toggle<cr>', desc = 'AI: Chat toggle', mode = { 'n', 'v' } },
      { '<leader>aa', '<cmd>CodeCompanionActions<cr>', desc = 'AI: Actions', mode = { 'n', 'v' } },
      { '<leader>ai', '<cmd>CodeCompanion<cr>', desc = 'AI: Inline prompt', mode = { 'n', 'v' } },
      { '<leader>at', '<cmd>CodeCompanion /test<cr>', desc = 'AI: Generate tests', mode = { 'n', 'v' } },
      { '<leader>ae', '<cmd>CodeCompanion /explain<cr>', desc = 'AI: Explain', mode = { 'n', 'v' } },
      { '<leader>af', '<cmd>CodeCompanion /fix<cr>', desc = 'AI: Fix', mode = { 'n', 'v' } },
      { 'ga', '<cmd>CodeCompanionChat Add<cr>', desc = 'AI: Add to chat', mode = 'v' },
    },
  },
}
