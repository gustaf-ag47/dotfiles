-- Code outline and structure view (like JetBrains Structure panel)
-- Shows classes, functions, methods in a tree view
-- Works with both LSP and Treesitter

return {
  'stevearc/aerial.nvim',
  dependencies = {
    'nvim-treesitter/nvim-treesitter',
    'nvim-tree/nvim-web-devicons',
  },
  event = { 'BufReadPre', 'BufNewFile' },
  config = function()
    require('aerial').setup({
      -- Priority of backends (LSP preferred, Treesitter fallback)
      backends = { 'lsp', 'treesitter', 'markdown', 'man' },

      -- Layout configuration
      layout = {
        -- Position: 'prefer_right', 'prefer_left', 'right', 'left', 'float'
        default_direction = 'prefer_right',
        -- Where to place the aerial window
        placement = 'edge',
        -- Maximum width as % of columns or fixed columns
        max_width = { 40, 0.2 },
        min_width = 30,
        -- Preserve window size when switching between buffers
        preserve_equality = false,
      },

      -- Attach mode: 'window' or 'global'
      attach_mode = 'global',

      -- Close aerial when leaving the source buffer
      close_automatic_events = { 'unfocus' },

      -- Filter symbols by kind
      filter_kind = false, -- Show all symbols

      -- Highlight the symbol under cursor
      highlight_on_hover = true,
      highlight_on_jump = 300,

      -- Icons for different symbol kinds
      icons = {}, -- Uses nvim-web-devicons by default

      -- Show guides (lines connecting symbols)
      show_guides = true,
      guides = {
        mid_item = '├ ',
        last_item = '└ ',
        nested_top = '│ ',
        whitespace = '  ',
      },

      -- Keymaps within aerial window
      keymaps = {
        ['?'] = 'actions.show_help',
        ['g?'] = 'actions.show_help',
        ['<CR>'] = 'actions.jump',
        ['<2-LeftMouse>'] = 'actions.jump',
        ['<C-v>'] = 'actions.jump_vsplit',
        ['<C-s>'] = 'actions.jump_split',
        ['p'] = 'actions.scroll',
        ['<C-j>'] = 'actions.down_and_scroll',
        ['<C-k>'] = 'actions.up_and_scroll',
        ['{'] = 'actions.prev',
        ['}'] = 'actions.next',
        ['[['] = 'actions.prev_up',
        [']]'] = 'actions.next_up',
        ['q'] = 'actions.close',
        ['o'] = 'actions.tree_toggle',
        ['O'] = 'actions.tree_toggle_recursive',
        ['l'] = 'actions.tree_open',
        ['L'] = 'actions.tree_open_recursive',
        ['h'] = 'actions.tree_close',
        ['H'] = 'actions.tree_close_recursive',
        ['zr'] = 'actions.tree_increase_fold_level',
        ['zR'] = 'actions.tree_open_all',
        ['zm'] = 'actions.tree_decrease_fold_level',
        ['zM'] = 'actions.tree_close_all',
        ['zx'] = 'actions.tree_sync_folds',
        ['zX'] = 'actions.tree_sync_folds',
      },

      -- Automatically open aerial when entering supported buffers
      open_automatic = false,

      -- Update delay for symbols
      update_events = 'TextChanged,InsertLeave',

      -- Navigation options
      nav = {
        border = 'rounded',
        max_height = 0.9,
        min_height = { 10, 0.1 },
        max_width = 0.5,
        min_width = { 0.2, 20 },
        win_opts = {
          cursorline = true,
          winblend = 10,
        },
        autojump = false,
        preview = false,
        keymaps = {
          ['<CR>'] = 'actions.jump',
          ['<Esc>'] = 'actions.close',
          ['<C-c>'] = 'actions.close',
          ['q'] = 'actions.close',
          ['<Tab>'] = 'actions.next_mode',
          ['<S-Tab>'] = 'actions.prev_mode',
          ['o'] = 'actions.tree_toggle',
          ['h'] = 'actions.parent',
          ['l'] = 'actions.leaf',
          ['j'] = 'actions.next',
          ['k'] = 'actions.prev',
          ['J'] = 'actions.next_sibling',
          ['K'] = 'actions.prev_sibling',
        },
      },
    })

    -- Load Telescope extension
    pcall(function()
      require('telescope').load_extension('aerial')
    end)
  end,
  keys = {
    { '<leader>a', '<cmd>AerialToggle<CR>', desc = 'Toggle code outline' },
    { '<leader>A', '<cmd>AerialNavToggle<CR>', desc = 'Toggle aerial nav' },
    { '[a', '<cmd>AerialPrev<CR>', desc = 'Previous aerial symbol' },
    { ']a', '<cmd>AerialNext<CR>', desc = 'Next aerial symbol' },
    -- Telescope integration
    {
      '<leader>sa',
      '<cmd>Telescope aerial<CR>',
      desc = 'Search symbols (aerial)',
    },
  },
}
