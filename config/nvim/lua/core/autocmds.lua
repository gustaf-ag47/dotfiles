local function augroup(name)
  return vim.api.nvim_create_augroup(name, { clear = true })
end

-- Highlight on yank
vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight when yanking (copying) text',
  group = augroup 'highlight-yank',
  callback = function()
    vim.highlight.on_yank()
  end,
})

-- Auto-save
vim.api.nvim_create_autocmd({ 'InsertLeave', 'TextChanged' }, {
  pattern = '*',
  command = 'silent! update',
  desc = 'Auto-save on insert leave or text change',
})

vim.api.nvim_create_autocmd('FocusLost', {
  pattern = '*',
  command = 'silent! wa',
  desc = 'Save all files when Neovim loses focus',
})

vim.api.nvim_create_autocmd('BufWritePost', {
  pattern = '*',
  command = 'echohl ModeMsg | echo "File saved!" | echohl None',
  desc = 'Show feedback when saving a file',
})
