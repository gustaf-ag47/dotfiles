return {
  'yetone/avante.nvim',
  event = 'VeryLazy',
  version = false, -- set this if you want to always pull the latest change
  opts = {
    provider = 'claude',
    -- Disable auto_suggestions to avoid copilot requirement
    -- auto_suggestions_provider = 'copilot',
    providers = {
      claude = {
        endpoint = 'https://api.anthropic.com',
        model = 'claude-sonnet-4-20250514',
        extra_request_body = {
          temperature = 0,
          max_tokens = 4096,
        },
      },
    },
  },
  -- if you want to build from source then do `make BUILD_FROM_SOURCE=true`
  build = 'make',
  dependencies = {
    'stevearc/dressing.nvim',
    'nvim-lua/plenary.nvim',
    'MunifTanjim/nui.nvim',
    'hrsh7th/nvim-cmp', -- autocompletion for avante commands and mentions
    'nvim-tree/nvim-web-devicons',
    {
      -- support for image pasting
      'HakonHarnes/img-clip.nvim',
      event = 'VeryLazy',
      opts = {
        default = {
          embed_image_as_base64 = false,
          prompt_for_file_name = false,
          drag_and_drop = {
            insert_mode = true,
          },
          use_absolute_path = true,
        },
      },
    },
    -- (render-markdown.nvim spec is canonical in plugins/markdown-render.lua,
    -- which already includes Avante in its ft list so it loads here too.
    -- Don't re-declare here — lazy.nvim merging is order-dependent.)
  },
}
