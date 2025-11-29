-- Flash.nvim - Navigate with search labels
-- Quick jumping around the buffer with minimal keystrokes

-- Filetypes where flash should be disabled (tree/special buffers)
local disabled_filetypes = {
  'dbui',
  'dbout',
  'neo-tree',
  'NvimTree',
  'oil',
  'Trouble',
  'lazy',
  'mason',
  'notify',
  'toggleterm',
  'TelescopePrompt',
}

-- Check if flash should be enabled in current buffer
local function flash_enabled()
  local ft = vim.bo.filetype
  for _, disabled in ipairs(disabled_filetypes) do
    if ft == disabled then
      return false
    end
  end
  return true
end

return {
  'folke/flash.nvim',
  event = 'VeryLazy',
  opts = {
    labels = 'asdfghjklqwertyuiopzxcvbnm',
    search = {
      multi_window = true,
      forward = true,
      wrap = true,
      mode = 'exact',
      incremental = false,
    },
    jump = {
      jumplist = true,
      pos = 'start',
      history = false,
      register = false,
      nohlsearch = true,
      autojump = false,
    },
    label = {
      uppercase = true,
      exclude = '',
      current = true,
      after = true,
      before = false,
      style = 'overlay',
      reuse = 'lowercase',
      rainbow = {
        enabled = false,
      },
    },
    highlight = {
      backdrop = true,
      matches = true,
      priority = 5000,
      groups = {
        match = 'FlashMatch',
        current = 'FlashCurrent',
        backdrop = 'FlashBackdrop',
        label = 'FlashLabel',
      },
    },
    modes = {
      search = {
        enabled = false, -- Don't integrate with default search
      },
      char = {
        enabled = true,
        jump_labels = true,
        multi_line = true,
        autohide = false,
        keys = { 'f', 'F', 't', 'T', ';', ',' },
        char_actions = function(motion)
          return {
            [';'] = 'next',
            [','] = 'prev',
            [motion:lower()] = 'next',
            [motion:upper()] = 'prev',
          }
        end,
        highlight = { backdrop = true },
      },
      treesitter = {
        labels = 'asdfghjklqwertyuiopzxcvbnm',
        jump = { pos = 'range' },
        search = { incremental = false },
        label = { before = true, after = true, style = 'inline' },
        highlight = {
          backdrop = false,
          matches = false,
        },
      },
      treesitter_search = {
        jump = { pos = 'range' },
        search = { multi_window = true, wrap = true, incremental = false },
        remote_op = { restore = true },
        label = { before = true, after = true, style = 'inline' },
      },
    },
  },
  keys = {
    {
      's',
      mode = { 'n', 'x', 'o' },
      function()
        if flash_enabled() then
          require('flash').jump()
        else
          -- Fallback to native behavior
          vim.api.nvim_feedkeys('s', 'n', false)
        end
      end,
      desc = 'Flash: Jump',
    },
    {
      'S',
      mode = { 'n', 'x', 'o' },
      function()
        if flash_enabled() then
          require('flash').treesitter()
        else
          vim.api.nvim_feedkeys('S', 'n', false)
        end
      end,
      desc = 'Flash: Treesitter',
    },
    {
      'r',
      mode = 'o',
      function()
        if flash_enabled() then
          require('flash').remote()
        else
          vim.api.nvim_feedkeys('r', 'n', false)
        end
      end,
      desc = 'Flash: Remote',
    },
    {
      'R',
      mode = { 'o', 'x' },
      function()
        if flash_enabled() then
          require('flash').treesitter_search()
        else
          vim.api.nvim_feedkeys('R', 'n', false)
        end
      end,
      desc = 'Flash: Treesitter Search',
    },
    {
      '<c-s>',
      mode = { 'c' },
      function()
        require('flash').toggle()
      end,
      desc = 'Flash: Toggle in Search',
    },
  },
}
