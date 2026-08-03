-- Neo-tree is a Neovim plugin to browse the file system
-- https://github.com/nvim-neo-tree/neo-tree.nvim

return {
  'nvim-neo-tree/neo-tree.nvim',
  branch = 'v3.x',
  dependencies = {
    'nvim-lua/plenary.nvim',
    'nvim-tree/nvim-web-devicons',
    'MunifTanjim/nui.nvim',
  },
  cmd = 'Neotree',
  keys = {
    { '\\', ':Neotree reveal<CR>', desc = 'NeoTree reveal', silent = true },
  },
  opts = {
    close_if_last_window = true,
    sources = { 'filesystem', 'buffers', 'git_status', 'document_symbols' },
    source_selector = {
      winbar = true,
      sources = {
        { source = 'filesystem', display_name = ' Files' },
        { source = 'buffers', display_name = '󰓩 Buffers' },
        { source = 'git_status', display_name = ' Git' },
        { source = 'document_symbols', display_name = '󰅩 Symbols' },
      },
    },
    filesystem = {
      filtered_items = {
        hide_dotfiles = false,
        hide_gitignored = true,
        hide_by_name = { 'vendor', 'var', 'node_modules', '.git' },
        never_show = { '.DS_Store' },
      },
      follow_current_file = { enabled = true },
      group_empty_dirs = true,
      use_libuv_file_watcher = true,
      window = {
        mappings = {
          ['\\'] = 'close_window',
        },
      },
    },
  },
}
