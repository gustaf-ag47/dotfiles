return { -- Collection of various small independent plugins/modules
  'echasnovski/mini.nvim',
  config = function()
    -- Better Around/Inside textobjects
    require('mini.ai').setup { n_lines = 500 }

    -- Add/delete/replace surroundings (brackets, quotes, etc.)
    require('mini.surround').setup()

    -- Split/join function arguments with gS
    -- gS on a single-line call → split args onto separate lines; gS again → join back
    require('mini.splitjoin').setup {
      mappings = { toggle = 'gS', split = '', join = '' },
    }

    -- Operators: gr (replace without yanking), gx (exchange), gs (sort)
    -- gr is the most useful: yank a word, then griw on another to replace without
    -- overwriting the register.
    require('mini.operators').setup()

    -- Animated scope indicator + ii/ai textobjects for the current indent scope
    require('mini.indentscope').setup {
      symbol = '│',
      options = { try_as_border = true },
    }
    -- Disable in non-editing buffers
    vim.api.nvim_create_autocmd('FileType', {
      pattern = {
        'help', 'neo-tree', 'Trouble', 'trouble', 'lazy', 'mason',
        'TelescopePrompt', 'oil', 'dbui', 'toggleterm',
      },
      callback = function() vim.b.miniindentscope_disable = true end,
    })

    -- Git utilities: show_range_history() shows how selected lines evolved in git
    -- Usage: visual select a method body, then :lua MiniGit.show_range_history()
    require('mini.git').setup()
    vim.keymap.set({ 'n', 'x' }, '<leader>gh', MiniGit.show_range_history, { desc = 'Git: line range history' })
    vim.keymap.set({ 'n', 'x' }, '<leader>gG', MiniGit.show_at_cursor,    { desc = 'Git: show at cursor' })

    -- Statusline (keep existing setup)
    local statusline = require 'mini.statusline'
    statusline.setup { use_icons = vim.g.have_nerd_font }

    ---@diagnostic disable-next-line: duplicate-set-field
    statusline.section_location = function()
      return '%2l:%-2v'
    end
  end,
}
