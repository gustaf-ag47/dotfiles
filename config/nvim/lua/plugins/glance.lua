-- Enhanced preview for LSP locations (definitions, references, implementations)
-- Provides a beautiful floating window with preview of the target location

return {
  'DNLHC/glance.nvim',
  cmd = 'Glance',
  event = 'LspAttach',
  build = function()
    vim.fn.system { 'python3', vim.fn.expand '$DOTFILES' .. '/bin/nvim-patch-plugins', 'glance' }
  end,
  config = function()
    local glance = require 'glance'
    local actions = glance.actions

    glance.setup {
      -- Height of the glance window
      height = 18,
      -- Z-index of the glance window
      zindex = 45,
      -- Auto-detach on buffer change
      detach = function()
        return vim.bo.filetype == 'neo-tree'
      end,
      -- Preview window configuration
      preview_win_opts = {
        cursorline = true,
        number = true,
        wrap = true,
      },
      -- Border style
      border = {
        enable = true,
        top_char = '─',
        bottom_char = '─',
      },
      -- List configuration
      list = {
        position = 'right', -- 'left' or 'right'
        width = 0.33, -- 33% of available width
      },
      -- Theme (uses your colorscheme)
      theme = {
        enable = true,
        mode = 'auto', -- 'brighten' or 'darken' or 'auto'
      },
      -- Mappings
      mappings = {
        list = {
          ['j'] = actions.next,
          ['k'] = actions.previous,
          ['<Down>'] = actions.next,
          ['<Up>'] = actions.previous,
          ['<Tab>'] = actions.next_location,
          ['<S-Tab>'] = actions.previous_location,
          ['<C-u>'] = actions.preview_scroll_win(5),
          ['<C-d>'] = actions.preview_scroll_win(-5),
          ['v'] = actions.jump_vsplit,
          ['s'] = actions.jump_split,
          ['t'] = actions.jump_tab,
          ['<CR>'] = actions.jump,
          ['o'] = actions.jump,
          ['l'] = actions.open_fold,
          ['h'] = actions.close_fold,
          ['<leader>l'] = actions.enter_win 'preview',
          ['q'] = actions.close,
          ['Q'] = actions.close,
          ['<Esc>'] = actions.close,
          ['<C-q>'] = actions.quickfix,
        },
        preview = {
          ['Q'] = actions.close,
          ['<Tab>'] = actions.next_location,
          ['<S-Tab>'] = actions.previous_location,
          ['<leader>l'] = actions.enter_win 'list',
        },
      },
      -- Hooks
      hooks = {
        -- Before opening glance
        before_open = function(results, open, jump, method)
          -- If only one result, jump directly instead of opening glance
          if #results == 1 then
            jump(results[1])
          else
            open(results)
          end
        end,
      },
      -- Fold icons
      folds = {
        fold_closed = '',
        fold_open = '',
        folded = true,
      },
      -- Indent guides
      indent_lines = {
        enable = true,
        icon = '│',
      },
      -- Window bar
      winbar = {
        enable = true,
      },
      -- Use Trouble.nvim for quickfix if available
      use_trouble_qf = true,
    }
  end,
  keys = {
    { 'gD', '<cmd>Glance definitions<CR>', desc = 'Glance definitions' },
    { 'gR', '<cmd>Glance references<CR>', desc = 'Glance references' },
    { 'gY', '<cmd>Glance type_definitions<CR>', desc = 'Glance type definitions' },
    { 'gM', '<cmd>Glance implementations<CR>', desc = 'Glance implementations' },
  },
}
