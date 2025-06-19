print 'http.lua loaded'
vim.api.nvim_buf_set_keymap(0, 'n', '<leader>p', "<cmd>lua require('kulala').run()<cr>", { noremap = true, silent = true, desc = 'Execute the request' })

vim.api.nvim_buf_set_keymap(
  0,
  'n',
  '<leader>i',
  "<cmd>lua require('kulala').inspect()<cr>",
  { noremap = true, silent = true, desc = 'Inspect the current request' }
)
