local M = {}

function M.setup()
  -- Bootstrap lazy.nvim
  local lazypath = vim.fn.stdpath 'data' .. '/lazy/lazy.nvim'
  if not vim.uv.fs_stat(lazypath) then
    local lazyrepo = 'https://github.com/folke/lazy.nvim.git'
    vim.fn.system {
      'git',
      'clone',
      '--filter=blob:none',
      '--branch=stable',
      lazyrepo,
      lazypath,
    }
  end
  vim.opt.rtp:prepend(lazypath)

  -- Collect plugins and register the LazyDone setup hook
  local modules = require('core.modules')
  local module_plugins = modules.setup()

  -- Build plugin list: start with imports, then add module plugins
  local plugin_specs = {
    { import = 'plugins' },
  }
  for _, plugin in ipairs(module_plugins) do
    table.insert(plugin_specs, plugin)
  end

  -- Configure lazy.nvim
  require('lazy').setup(plugin_specs, {
    ui = {
      icons = vim.g.have_nerd_font and {} or {
        cmd = '⌘',
        config = '🛠',
        event = '📅',
        ft = '📂',
        init = '⚙',
        keys = '🗝',
        plugin = '🔌',
        runtime = '💻',
        require = '🌙',
        source = '📄',
        start = '🚀',
        task = '📌',
        lazy = '💤 ',
      },
    },
  })
end

M.setup()

return M
