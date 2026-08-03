-- Multiple persistent terminals

return {
  'akinsho/toggleterm.nvim',
  version = '*',
  cmd = 'ToggleTerm',
  keys = {
    { '<C-\\>', '<cmd>ToggleTerm<cr>', desc = 'Toggle terminal' },
    { '<C-\\>', '<cmd>ToggleTerm<cr>', mode = 't', desc = 'Toggle terminal' },
  },
  opts = {
    size = function(term)
      if term.direction == 'horizontal' then
        return 15
      elseif term.direction == 'vertical' then
        return vim.o.columns * 0.4
      end
    end,
    open_mapping = [[<C-\>]],
    direction = 'horizontal',
    shade_filetypes = {},
    shade_terminals = true,
    shading_factor = 2,
    start_in_insert = true,
    insert_mappings = true,
    persist_size = true,
    close_on_exit = true,
    shell = vim.o.shell,
    float_opts = {
      border = 'curved',
    },
  },
}
