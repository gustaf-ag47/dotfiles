-- Lazygit integration - full git TUI in a floating window
-- Requires lazygit to be installed on the system

return {
  'kdheepak/lazygit.nvim',
  cmd = { 'LazyGit', 'LazyGitConfig', 'LazyGitCurrentFile', 'LazyGitFilter', 'LazyGitFilterCurrentFile' },
  dependencies = { 'nvim-lua/plenary.nvim' },
  keys = {
    { '<leader>Gg', '<cmd>LazyGit<cr>', desc = 'LazyGit' },
    { '<leader>Gf', '<cmd>LazyGitFilterCurrentFile<cr>', desc = 'LazyGit file commits' },
  },
}
