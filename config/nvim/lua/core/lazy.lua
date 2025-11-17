local M = {}

function M.setup()
  -- Bootstrap lazy.nvim
  local lazypath = vim.fn.stdpath 'data' .. '/lazy/lazy.nvim'
  if not vim.loop.fs_stat(lazypath) then
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

  -- Load modular system and collect plugin specifications
  local modules = require('core.modules')
  local module_plugins = modules.setup()
  
  -- Configure lazy.nvim with both modular and traditional plugins
  local plugin_specs = {
    { import = 'plugins' }, -- Traditional plugin directory
  }
  
  -- Add modular plugin specifications
  vim.list_extend(plugin_specs, module_plugins)
  
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
