return {
  'stevearc/oil.nvim',
  ---@module 'oil'
  ---@type oil.SetupOpts
  opts = {
    -- Show hidden files (dot files) by default
    view_options = {
      show_hidden = true,
    },
    -- Configure keymaps
    keymaps = {
      ["g."] = "actions.toggle_hidden",
      ["<C-h>"] = false, -- Disable default keymap to avoid conflicts
      ["<M-h>"] = "actions.toggle_hidden", -- Alternative toggle keymap
    },
    -- Use trash instead of permanent deletion
    delete_to_trash = true,
    -- Skip confirmation for simple operations
    skip_confirm_for_simple_edits = false,
    -- Restore window options to previous values when leaving oil buffer
    restore_win_options = true,
    -- Window-local options to use for oil buffers
    win_options = {
      wrap = false,
      signcolumn = "no",
      cursorcolumn = false,
      foldcolumn = "0",
      spell = false,
      list = false,
      conceallevel = 3,
      concealcursor = "nvic",
    },
  },
  -- Optional dependencies
  dependencies = { { 'echasnovski/mini.icons', opts = {} } },
  -- dependencies = { "nvim-tree/nvim-web-devicons" }, -- use if prefer nvim-web-devicons
}
