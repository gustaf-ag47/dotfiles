return {
  'stevearc/oil.nvim',
  ---@module 'oil'
  ---@type oil.SetupOpts
  lazy = false,
  dependencies = {
    'nvim-tree/nvim-web-devicons',
    'refractalize/oil-git-status.nvim',
  },
  config = function(_, opts)
    require('oil').setup(opts)
    -- oil-git-status must be set up after oil so require("oil.config").win_options is populated
    require('oil-git-status').setup()
    -- oil_preview is the confirmation dialog shown before applying file operations.
    -- It has buftype=nofile, so :w raises E382. Set acwrite so BufWriteCmd fires,
    -- then simulate 'y' (confirm) — re-calling oil.save() would fail because
    -- mutation_in_progress is already true at this point.
    vim.api.nvim_create_autocmd('FileType', {
      pattern = 'oil_preview',
      callback = function(args)
        vim.bo[args.buf].buftype = 'acwrite'
        -- Neovim requires a buffer name before BufWriteCmd fires on acwrite buffers
        vim.api.nvim_buf_set_name(args.buf, 'oil://confirmation')
        vim.api.nvim_create_autocmd('BufWriteCmd', {
          buffer = args.buf,
          callback = function()
            -- Schedule so :w finishes before 'y' is fed, otherwise the key
            -- lands in command mode rather than the buffer's normal mode.
            vim.schedule(function()
              vim.api.nvim_feedkeys('y', 'n', false)
            end)
            vim.bo[args.buf].modified = false
          end,
        })
      end,
    })
  end,
  opts = {
    skip_confirm_for_simple_edits = true,
    view_options = {
      show_hidden = true,
    },
    win_options = {
      -- Make room for the git-status sign column
      signcolumn = 'yes:2',
    },
  },
  keys = {
    { '-', '<cmd>Oil<cr>', desc = 'Open parent directory (oil)' },
  },
}
