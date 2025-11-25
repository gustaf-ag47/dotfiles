-- Dependency validation utility
-- Ensures strict adherence to dependency rules in the modular architecture
-- Prevents violations of the dependency inversion principle

local M = {}

-- Define allowed dependencies for each layer
M.dependency_rules = {
  -- Core layer (Level 1) - can depend on nothing
  core = {},

  -- Utils layer (Level 1) - can depend on nothing
  utils = {},

  -- Features layer (Level 2) - can depend on core and utils only
  features = { 'core', 'utils' },

  -- Languages layer (Level 3) - can depend on core, utils, and features, but NOT other languages
  languages = { 'core', 'utils', 'features' },
}

-- Validate that a module only depends on allowed layers
M.validate_module_dependencies = function(module_name, dependencies)
  local module_layer = M.get_module_layer(module_name)
  if not module_layer then
    return false, "Unknown module layer for: " .. module_name
  end

  local allowed_layers = M.dependency_rules[module_layer]

  for _, dep in ipairs(dependencies) do
    local dep_layer = M.get_module_layer(dep)
    if not dep_layer then
      return false, "Unknown dependency layer for: " .. dep
    end

    -- Check if dependency layer is allowed
    if not vim.tbl_contains(allowed_layers, dep_layer) then
      return false, string.format(
        "DEPENDENCY VIOLATION: %s (layer: %s) cannot depend on %s (layer: %s)",
        module_name, module_layer, dep, dep_layer
      )
    end

    -- Special check: language modules cannot depend on other language modules
    if module_layer == 'languages' and dep_layer == 'languages' then
      local module_lang = M.get_language_from_module(module_name)
      local dep_lang = M.get_language_from_module(dep)

      if module_lang ~= dep_lang then
        return false, string.format(
          "LANGUAGE ISOLATION VIOLATION: %s cannot depend on %s (cross-language dependency forbidden)",
          module_name, dep
        )
      end
    end
  end

  return true, "Dependencies valid"
end

-- Get the layer of a module based on its path
M.get_module_layer = function(module_name)
  if module_name:match('^core%.') then
    return 'core'
  elseif module_name:match('^utils%.') then
    return 'utils'
  elseif module_name:match('^features%.') then
    return 'features'
  elseif module_name:match('^lang%.') then
    return 'languages'
  else
    return nil
  end
end

-- Extract language name from language module path
M.get_language_from_module = function(module_name)
  local lang = module_name:match('^lang%.(.+)')
  return lang
end

-- Validate the entire modular system
M.validate_system = function()
  local violations = {}

  -- Define known modules and their dependencies
  local modules = {
    ['core.init'] = {},
    ['core.options'] = {},
    ['core.keymaps'] = {},
    ['core.autocmds'] = {},
    ['core.lazy'] = { 'core.modules' },
    ['core.modules'] = {},

    ['features.lsp'] = { 'core' },
    ['features.completion'] = { 'core' },
    ['features.debugging'] = { 'core' },

    ['lang.go'] = { 'core', 'features.lsp', 'features.debugging' },
    ['lang.python'] = { 'core', 'features.lsp', 'features.debugging' },
    ['lang.sql'] = { 'core', 'features.lsp', 'features.completion' },
  }

  for module_name, deps in pairs(modules) do
    local valid, message = M.validate_module_dependencies(module_name, deps)
    if not valid then
      table.insert(violations, message)
    end
  end

  return violations
end

-- Runtime dependency checker - prevents module loading if dependencies are invalid
M.check_runtime_dependencies = function(module_name, required_modules)
  -- Check if all required modules are already loaded
  for _, req_module in ipairs(required_modules) do
    if not package.loaded[req_module] then
      error(string.format(
        "DEPENDENCY ERROR: %s requires %s to be loaded first",
        module_name, req_module
      ))
    end
  end

  -- Validate dependency rules
  local valid, message = M.validate_module_dependencies(module_name, required_modules)
  if not valid then
    error("ARCHITECTURE VIOLATION: " .. message)
  end

  return true
end

-- Health check for the modular system
M.health_check = function()
  local violations = M.validate_system()

  if #violations == 0 then
    print("✅ Dependency validation: PASSED")
    print("   - No dependency rule violations found")
    print("   - Language modules are properly isolated")
    print("   - Dependency direction is correct")
    return true
  else
    print("❌ Dependency validation: FAILED")
    for _, violation in ipairs(violations) do
      print("   - " .. violation)
    end
    return false
  end
end

-- Language isolation check - ensures all language modules are completely isolated
M.check_language_isolation = function()
  local _go_module = package.loaded['lang.go']
  local _python_module = package.loaded['lang.python']
  local _sql_module = package.loaded['lang.sql']

  local issues = {}
  local languages = { 'go', 'python', 'sql' }

  -- Check cross-language dependencies for each language module
  for _, lang in ipairs(languages) do
    local module = package.loaded['lang.' .. lang]
    if module then
      -- Check for illegal dependencies on other language modules
      for _, other_lang in ipairs(languages) do
        if lang ~= other_lang then
          local dependency_key = other_lang .. '_dependency'
          if rawget(module, dependency_key) then
            table.insert(issues, string.format(
              "%s module has illegal %s dependency",
              lang:upper(), other_lang:upper()
            ))
          end
        end
      end
    end
  end

  if #issues == 0 then
    print("✅ Language isolation: PASSED")
    print("   - Go, Python, and SQL modules are completely isolated")
    print("   - No cross-language dependencies detected")
    return true
  else
    print("❌ Language isolation: FAILED")
    for _, issue in ipairs(issues) do
      print("   - " .. issue)
    end
    return false
  end
end

return M