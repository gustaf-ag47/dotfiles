-- Module loader for features and languages
-- Core -> Features -> Languages (dependency direction)

local M = {}

-- Module registry - tracks loaded modules
M.registry = {
  loaded = {},
  failed = {},
}

-- Safe module loader with error handling
M.safe_require = function(module_name)
  local ok, module = pcall(require, module_name)
  if ok then
    M.registry.loaded[module_name] = module
    return module
  else
    M.registry.failed[module_name] = true
    vim.schedule(function()
      vim.notify(string.format('Failed to load module "%s": %s', module_name, module), vim.log.levels.WARN, { title = 'Module Loader' })
    end)
    return nil
  end
end

-- Load feature modules (LSP, completion, debugging, etc.)
M.load_features = function()
  local features = {
    'lsp',
    'completion',
    'debugging',
  }

  for _, feature in ipairs(features) do
    local module_name = 'features.' .. feature
    local module = M.safe_require(module_name)

    if module then
      -- Collect plugins from feature modules
      if module.plugins then
        for _, plugin in ipairs(module.plugins) do
          table.insert(M.plugin_specs, plugin)
        end
      end
    end
  end
end

-- Load language modules (Go, Python, SQL, etc.)
M.load_languages = function()
  local languages = {
    'go',
    'python',
    'sql',
    'rust',
    'typescript',
    'dotenv',
    'php',
    'twig',
    'vimfony',
    -- Add more languages as needed
  }

  for _, lang in ipairs(languages) do
    local module_name = 'lang.' .. lang
    local module = M.safe_require(module_name)

    if module then
      -- Collect plugins from language modules
      if module.plugins then
        for _, plugin in ipairs(module.plugins) do
          table.insert(M.plugin_specs, plugin)
        end
      end
    end
  end
end

-- Plugin specification collector
M.plugin_specs = {}

-- Collect all plugin specifications from modules
M.collect_plugins = function()
  M.plugin_specs = {}

  -- Load features first (they provide base functionality)
  M.load_features()

  -- Load languages second (they depend on features)
  M.load_languages()

  return M.plugin_specs
end

-- Setup all modules after plugins are loaded
M.setup_modules = function()
  -- Setup features first (they provide base functionality)
  for name, module in pairs(M.registry.loaded) do
    if name:match '^features%.' and type(module.setup) == 'function' then
      local ok, err = pcall(module.setup)
      if not ok then
        vim.schedule(function()
          vim.notify(string.format('Failed to setup feature "%s": %s', name, err), vim.log.levels.ERROR, { title = 'Module Loader' })
        end)
      end
    end
  end

  -- Setup languages second (they depend on features)
  for name, module in pairs(M.registry.loaded) do
    if name:match '^lang%.' and type(module.setup) == 'function' then
      local ok, err = pcall(module.setup)
      if not ok then
        vim.schedule(function()
          vim.notify(string.format('Failed to setup language "%s": %s', name, err), vim.log.levels.ERROR, { title = 'Module Loader' })
        end)
      end
    end
  end

  -- Register cross-module dependencies
  M.register_cross_dependencies()
end

-- Register cross-module dependencies after all modules are loaded
M.register_cross_dependencies = function()
  for name, module in pairs(M.registry.loaded) do
    if name:match '^lang%.' then
      -- Register LSP configurations if available
      if module.lsp_config then
        local lsp_module = M.registry.loaded['features.lsp']
        if lsp_module and lsp_module.register_server then
          for server_name, config in pairs(module.lsp_config) do
            lsp_module.register_server(server_name, config)
          end
        end
      end

      -- Register debug configurations if available
      if module.debug_config then
        local debug_module = M.registry.loaded['features.debugging']
        if debug_module then
          if module.debug_config.adapters then
            for adapter_name, adapter_config in pairs(module.debug_config.adapters) do
              debug_module.register_adapter(adapter_name, adapter_config)
            end
          end
          if module.debug_config.configurations then
            for lang_name, configurations in pairs(module.debug_config.configurations) do
              debug_module.register_configuration(lang_name, configurations)
            end
          end
        end
      end
    end
  end
end

-- Initialize the module system (collects plugins only)
M.setup = function()
  -- Collect all plugin specifications from modules
  local plugins = M.collect_plugins()

  -- Setup modules after plugins are loaded via autocmd
  vim.api.nvim_create_autocmd('User', {
    pattern = 'LazyDone',
    callback = function()
      M.setup_modules()
    end,
    once = true,
  })

  return plugins
end

return M
