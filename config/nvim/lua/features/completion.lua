-- Completion feature module - isolated and following SRP
-- Responsible only for autocompletion functionality
-- No dependencies on language-specific modules (dependency rule compliance)

local M = {}

-- Completion-related plugins
M.plugins = {
  {
    'hrsh7th/nvim-cmp',
    event = 'InsertEnter',
    dependencies = {
      -- Snippet engine
      {
        'L3MON4D3/LuaSnip',
        build = (function()
          return 'make install_jsregexp'
        end)(),
        dependencies = {
          {
            'rafamadriz/friendly-snippets',
            config = function()
              require('luasnip.loaders.from_vscode').lazy_load()
            end,
          },
        },
      },

      -- Completion sources
      'saadparwaiz1/cmp_luasnip',
      'hrsh7th/cmp-nvim-lsp',
      'hrsh7th/cmp-buffer',
      'hrsh7th/cmp-path',
      'hrsh7th/cmp-cmdline',
      'hrsh7th/cmp-nvim-lsp-signature-help',

      -- Additional completion sources
      'hrsh7th/cmp-emoji',
      'hrsh7th/cmp-calc',
      'hrsh7th/cmp-nvim-lua',

      -- Optional: AI completion
      -- 'hrsh7th/cmp-copilot',
    },
    config = function()
      -- This will be handled by the feature setup
    end,
  },
}

-- Setup completion configuration
M.setup_completion = function()
  local cmp = require('cmp')
  local luasnip = require('luasnip')

  -- Helper function for super tab behavior
  local has_words_before = function()
    local line, col = unpack(vim.api.nvim_win_get_cursor(0))
    return col ~= 0 and vim.api.nvim_buf_get_lines(0, line - 1, line, true)[1]:sub(col, col):match('%s') == nil
  end

  cmp.setup({
    snippet = {
      expand = function(args)
        luasnip.lsp_expand(args.body)
      end,
    },

    completion = {
      completeopt = 'menu,menuone,noinsert',
      keyword_length = 1,
    },

    performance = {
      debounce = 60,
      throttle = 30,
      fetching_timeout = 500,
      confirm_resolve_timeout = 80,
      async_budget = 1,
      max_view_entries = 200,
    },

    mapping = cmp.mapping.preset.insert({
      -- Scroll documentation
      ['<C-b>'] = cmp.mapping.scroll_docs(-4),
      ['<C-f>'] = cmp.mapping.scroll_docs(4),

      -- Trigger completion
      ['<C-Space>'] = cmp.mapping.complete(),

      -- Abort completion
      ['<C-e>'] = cmp.mapping.abort(),

      -- Confirm completion
      ['<CR>'] = cmp.mapping.confirm({ select = false }),

      -- Super Tab behavior
      ['<Tab>'] = cmp.mapping(function(fallback)
        if cmp.visible() then
          cmp.select_next_item()
        elseif luasnip.expand_or_jumpable() then
          luasnip.expand_or_jump()
        elseif has_words_before() then
          cmp.complete()
        else
          fallback()
        end
      end, { 'i', 's' }),

      ['<S-Tab>'] = cmp.mapping(function(fallback)
        if cmp.visible() then
          cmp.select_prev_item()
        elseif luasnip.jumpable(-1) then
          luasnip.jump(-1)
        else
          fallback()
        end
      end, { 'i', 's' }),
    }),

    sources = cmp.config.sources({
      { name = 'nvim_lsp', priority = 1000 },
      { name = 'nvim_lsp_signature_help', priority = 900 },
      { name = 'luasnip', priority = 800 },
    }, {
      { name = 'buffer', priority = 500, keyword_length = 3 },
      { name = 'path', priority = 400 },
      { name = 'calc', priority = 300 },
      { name = 'emoji', priority = 200 },
      { name = 'nvim_lua', priority = 100 },
    }),

    formatting = {
      fields = { 'abbr', 'kind', 'menu' },
      format = function(entry, vim_item)
        -- Kind icons
        local kind_icons = {
          Text = '󰉿',
          Method = '󰆧',
          Function = '󰊕',
          Constructor = '',
          Field = '󰜢',
          Variable = '󰀫',
          Class = '󰠱',
          Interface = '',
          Module = '',
          Property = '󰜢',
          Unit = '󰑭',
          Value = '󰎠',
          Enum = '',
          Keyword = '󰌋',
          Snippet = '',
          Color = '󰏘',
          File = '󰈙',
          Reference = '󰈇',
          Folder = '󰉋',
          EnumMember = '',
          Constant = '󰏿',
          Struct = '󰙅',
          Event = '',
          Operator = '󰆕',
          TypeParameter = '',
        }

        -- Set kind icon
        vim_item.kind = string.format('%s %s', kind_icons[vim_item.kind] or '', vim_item.kind)

        -- Set menu source
        vim_item.menu = ({
          nvim_lsp = '[LSP]',
          nvim_lsp_signature_help = '[Sig]',
          luasnip = '[Snip]',
          buffer = '[Buf]',
          path = '[Path]',
          cmdline = '[Cmd]',
          calc = '[Calc]',
          emoji = '[Emoji]',
          nvim_lua = '[Lua]',
        })[entry.source.name]

        return vim_item
      end,
    },

    window = {
      completion = cmp.config.window.bordered(),
      documentation = cmp.config.window.bordered(),
    },

    experimental = {
      ghost_text = {
        hl_group = 'CmpGhostText',
      },
    },
  })

  -- Command line completion
  cmp.setup.cmdline({ '/', '?' }, {
    mapping = cmp.mapping.preset.cmdline(),
    sources = {
      { name = 'buffer' }
    }
  })

  cmp.setup.cmdline(':', {
    mapping = cmp.mapping.preset.cmdline(),
    sources = cmp.config.sources({
      { name = 'path' }
    }, {
      { name = 'cmdline' }
    })
  })
end

-- Setup snippet configuration
M.setup_snippets = function()
  local luasnip = require('luasnip')

  -- Snippet configuration
  luasnip.config.setup({
    history = true,
    updateevents = 'TextChanged,TextChangedI',
    enable_autosnippets = true,
    ext_opts = {
      [require('luasnip.util.types').choiceNode] = {
        active = {
          virt_text = { { '●', 'Orange' } },
        },
      },
    },
  })

  -- Load snippets from friendly-snippets
  require('luasnip.loaders.from_vscode').lazy_load()

  -- Load custom snippets if they exist
  local custom_snippets_path = vim.fn.stdpath('config') .. '/snippets'
  if vim.fn.isdirectory(custom_snippets_path) == 1 then
    require('luasnip.loaders.from_vscode').lazy_load({ paths = { custom_snippets_path } })
  end

  -- Snippet keymaps
  vim.keymap.set({ 'i', 's' }, '<C-k>', function()
    if luasnip.expand_or_jumpable() then
      luasnip.expand_or_jump()
    end
  end, { desc = 'Expand or jump snippet' })

  vim.keymap.set({ 'i', 's' }, '<C-j>', function()
    if luasnip.jumpable(-1) then
      luasnip.jump(-1)
    end
  end, { desc = 'Jump back in snippet' })

  vim.keymap.set('i', '<C-l>', function()
    if luasnip.choice_active() then
      luasnip.change_choice(1)
    end
  end, { desc = 'Change snippet choice' })
end

-- Add completion source
M.add_source = function(source_config)
  local cmp = require('cmp')
  local config = cmp.get_config()
  table.insert(config.sources, source_config)
  cmp.setup(config)
end

-- Setup completion feature module
M.setup = function()
  -- Setup completion engine
  M.setup_completion()

  -- Setup snippets
  M.setup_snippets()

  -- Setup completion highlighting
  vim.api.nvim_set_hl(0, 'CmpGhostText', { link = 'Comment', default = true })
end

return M