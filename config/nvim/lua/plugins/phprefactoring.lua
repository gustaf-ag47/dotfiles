-- PHP-specific refactoring operations missing from phpactor:
-- change method signature, pull members up/down, extract class, introduce parameter
-- Uses tree-sitter AST transforms — works without LSP

return {
  {
    'adibhanna/phprefactoring.nvim',
    ft = 'php',
    dependencies = { 'nvim-treesitter/nvim-treesitter' },
    opts = {},
    keys = {
      -- These complement phpactor code actions (which handle extract method/var/const)
      { '<leader>Prs', '<cmd>PhpRefactoring ChangeSignature<cr>', ft = 'php', desc = 'Change method signature' },
      { '<leader>Pru', '<cmd>PhpRefactoring PullMembersUp<cr>', ft = 'php', desc = 'Pull members up' },
      { '<leader>Prd', '<cmd>PhpRefactoring PushMembersDown<cr>', ft = 'php', desc = 'Push members down' },
      { '<leader>Prx', '<cmd>PhpRefactoring ExtractClass<cr>', ft = 'php', desc = 'Extract class' },
      { '<leader>Prp', '<cmd>PhpRefactoring IntroduceParameter<cr>', ft = 'php', desc = 'Introduce parameter' },
      { '<leader>Prr', '<cmd>PhpRefactoring RenameVariable<cr>', ft = 'php', desc = 'Rename variable (local)' },
    },
  },
}
