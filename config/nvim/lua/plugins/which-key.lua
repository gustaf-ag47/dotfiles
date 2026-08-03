return { -- Useful plugin to show you pending keybinds.
  'folke/which-key.nvim',
  event = 'VimEnter', -- Sets the loading event to 'VimEnter'
  opts = {
    -- delay between pressing a key and opening which-key (milliseconds)
    -- this setting is independent of vim.opt.timeoutlen
    delay = 0,
    icons = {
      -- set icon mappings to true if you have a Nerd Font
      mappings = vim.g.have_nerd_font,
      -- If you are using a Nerd Font: set icons.keys to an empty table which will use the
      -- default which-key.nvim defined Nerd Font icons, otherwise define a string table
      keys = vim.g.have_nerd_font and {} or {
        Up = '<Up> ',
        Down = '<Down> ',
        Left = '<Left> ',
        Right = '<Right> ',
        C = '<C-…> ',
        M = '<M-…> ',
        D = '<D-…> ',
        S = '<S-…> ',
        CR = '<CR> ',
        Esc = '<Esc> ',
        ScrollWheelDown = '<ScrollWheelDown> ',
        ScrollWheelUp = '<ScrollWheelUp> ',
        NL = '<NL> ',
        BS = '<BS> ',
        Space = '<Space> ',
        Tab = '<Tab> ',
        F1 = '<F1>',
        F2 = '<F2>',
        F3 = '<F3>',
        F4 = '<F4>',
        F5 = '<F5>',
        F6 = '<F6>',
        F7 = '<F7>',
        F8 = '<F8>',
        F9 = '<F9>',
        F10 = '<F10>',
        F11 = '<F11>',
        F12 = '<F12>',
      },
    },

    -- Document existing key chains
    spec = {
      -- Core groups (always visible)
      { '<leader>b', group = 'Buffer' },
      { '<leader>d', group = 'Debug' },
      { '<leader>q', group = 'Quit/Session' },
      { '<leader>s', group = 'Search' },
      { '<leader>u', group = 'UI Toggle' },
      { '<leader>w', group = 'Window/Save' },
      { '<leader>x', group = 'Diagnostics' },
      { '<leader><Tab>', group = 'Tabs' },

      -- LSP groups (buffer-local when LSP attached)
      { '<leader>c', group = 'Code', mode = { 'n', 'x' } },
      { '<leader>l', group = 'LSP' },

      -- Global tool groups (always relevant)
      { '<leader>T', group = 'Test' },
      { '<leader>G', group = 'Git' },
      { '<leader>R', group = 'REST' },
      { '<leader>S', desc = 'Search & Replace' },
      { '<leader>K', group = 'Knowledge/Anki' },

      -- NOTE: Language-specific groups (Go, Rust, TypeScript, PHP, etc.)
      -- are registered buffer-locally in each lang module's FileType autocmd
      -- via require('which-key').add() so they only appear for relevant filetypes.

      -- Quick actions (single key after leader)
      { '<leader>a', desc = 'Add to Harpoon' },
      { '<leader>H', desc = 'Harpoon menu' },
      { '<leader>/', desc = 'Search in buffer' },
      { '<leader>1', desc = 'Harpoon 1', hidden = true },
      { '<leader>2', desc = 'Harpoon 2', hidden = true },
      { '<leader>3', desc = 'Harpoon 3', hidden = true },
      { '<leader>4', desc = 'Harpoon 4', hidden = true },
      { '<leader>5', desc = 'Harpoon 5', hidden = true },
    },
  },
}
