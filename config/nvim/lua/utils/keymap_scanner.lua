-- Keybinding scanner for Neovim configuration
-- Automatically extracts and documents all keybindings from the modular config

local M = {}

-- Patterns to match different keymap definitions
M.patterns = {
  -- vim.keymap.set('n', '<leader>ff', '<cmd>Telescope find_files<cr>', { desc = 'Find files' })
  standard = "vim%.keymap%.set%s*%(%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]?([^'\"]*)['\"]?%s*,%s*{.-desc%s*=%s*['\"]([^'\"]*)['\"]",
  
  -- map('n', '<leader>ff', '<cmd>Telescope find_files<cr>', { desc = 'Find files' })
  local_map = "map%s*%(%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]?([^'\"]*)['\"]?%s*,%s*{.-desc%s*=%s*['\"]([^'\"]*)['\"]",
  
  -- Simple without options
  simple = "vim%.keymap%.set%s*%(%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]([^'\"]*)['\"]",
  
  -- Function-based
  function_based = "vim%.keymap%.set%s*%(%s*['\"]([^'\"]+)['\"]%s*,%s*['\"]([^'\"]+)['\"]%s*,%s*function%s*%(%)(.-)end",
}

-- File types to scan
M.file_types = {
  '.lua$',
}

-- Directories to scan in order of priority
M.scan_dirs = {
  'lua/core',
  'lua/features', 
  'lua/lang',
  'lua/plugins',
  'lua/utils',
}

-- Extract keybindings from a single line
M.extract_from_line = function(line, file_path, line_number)
  local keybindings = {}
  
  -- Try each pattern
  for pattern_name, pattern in pairs(M.patterns) do
    for mode, key, command, desc in line:gmatch(pattern) do
      table.insert(keybindings, {
        mode = mode,
        key = key,
        command = command,
        desc = desc or '',
        file = file_path,
        line = line_number,
        pattern = pattern_name,
      })
    end
  end
  
  -- Special handling for complex patterns
  if line:match("vim%.keymap%.set") and #keybindings == 0 then
    -- Handle more complex cases
    local mode_match = line:match("vim%.keymap%.set%s*%(%s*['\"]([^'\"]+)['\"]")
    local key_match = line:match("vim%.keymap%.set%s*%([^,]+,%s*['\"]([^'\"]+)['\"]")
    
    if mode_match and key_match then
      -- Extract description from comments or nearby context
      local desc_match = line:match("desc%s*=%s*['\"]([^'\"]*)['\"]") or 
                        line:match("%-%-(.*)") or ''
      
      table.insert(keybindings, {
        mode = mode_match,
        key = key_match,
        command = '(complex)',
        desc = desc_match:gsub('^%s*', ''),
        file = file_path,
        line = line_number,
        pattern = 'complex',
      })
    end
  end
  
  return keybindings
end

-- Scan a single file for keybindings
M.scan_file = function(file_path)
  local keybindings = {}
  local file = io.open(file_path, 'r')
  
  if not file then
    return keybindings
  end
  
  local line_number = 0
  for line in file:lines() do
    line_number = line_number + 1
    local extracted = M.extract_from_line(line, file_path, line_number)
    for _, kb in ipairs(extracted) do
      table.insert(keybindings, kb)
    end
  end
  
  file:close()
  return keybindings
end

-- Get all Lua files in a directory recursively
M.get_lua_files = function(dir_path)
  local files = {}
  local handle = io.popen('find "' .. dir_path .. '" -name "*.lua" 2>/dev/null')
  
  if handle then
    for file in handle:lines() do
      table.insert(files, file)
    end
    handle:close()
  end
  
  return files
end

-- Scan entire configuration
M.scan_config = function(config_path)
  config_path = config_path or vim.fn.stdpath('config')
  local all_keybindings = {}
  
  print("Scanning Neovim configuration at: " .. config_path)
  
  for _, scan_dir in ipairs(M.scan_dirs) do
    local full_path = config_path .. '/' .. scan_dir
    local files = M.get_lua_files(full_path)
    
    print(string.format("Scanning %s (%d files)", scan_dir, #files))
    
    for _, file_path in ipairs(files) do
      local keybindings = M.scan_file(file_path)
      for _, kb in ipairs(keybindings) do
        -- Add module information
        kb.module = M.detect_module(file_path)
        table.insert(all_keybindings, kb)
      end
    end
  end
  
  return all_keybindings
end

-- Detect module type from file path
M.detect_module = function(file_path)
  if file_path:match('/core/') then
    return 'core'
  elseif file_path:match('/features/') then
    return 'features'
  elseif file_path:match('/lang/') then
    local lang = file_path:match('/lang/([^/]+)%.lua$')
    return 'lang:' .. (lang or 'unknown')
  elseif file_path:match('/plugins/') then
    return 'plugins'
  elseif file_path:match('/utils/') then
    return 'utils'
  else
    return 'other'
  end
end

-- Group keybindings by various criteria
M.group_keybindings = function(keybindings)
  local grouped = {
    by_module = {},
    by_mode = {},
    by_leader = {},
    global = {},
    language_specific = {},
  }
  
  for _, kb in ipairs(keybindings) do
    -- By module
    grouped.by_module[kb.module] = grouped.by_module[kb.module] or {}
    table.insert(grouped.by_module[kb.module], kb)
    
    -- By mode
    grouped.by_mode[kb.mode] = grouped.by_mode[kb.mode] or {}
    table.insert(grouped.by_mode[kb.mode], kb)
    
    -- By leader key usage
    if kb.key:match('<leader>') then
      local suffix = kb.key:match('<leader>(.*)')
      grouped.by_leader[suffix] = grouped.by_leader[suffix] or {}
      table.insert(grouped.by_leader[suffix], kb)
    end
    
    -- Global vs language-specific
    if kb.module:match('^lang:') then
      table.insert(grouped.language_specific, kb)
    else
      table.insert(grouped.global, kb)
    end
  end
  
  return grouped
end

-- Generate markdown documentation
M.generate_markdown = function(keybindings, grouped)
  local lines = {
    '# Neovim Keybinding Reference',
    '',
    'Auto-generated from configuration scan.',
    '',
    '## Summary',
    '',
    string.format('- **Total keybindings**: %d', #keybindings),
    string.format('- **Global keybindings**: %d', #grouped.global),
    string.format('- **Language-specific keybindings**: %d', #grouped.language_specific),
    '',
  }
  
  -- Global keybindings
  table.insert(lines, '## Global Keybindings')
  table.insert(lines, '')
  table.insert(lines, '| Mode | Key | Command | Description | Module | File |')
  table.insert(lines, '|------|-----|---------|-------------|--------|------|')
  
  for _, kb in ipairs(grouped.global) do
    local file_name = kb.file:match('([^/]+)$') or kb.file
    table.insert(lines, string.format('| `%s` | `%s` | `%s` | %s | %s | %s:%d |',
      kb.mode, kb.key, kb.command, kb.desc, kb.module, file_name, kb.line))
  end
  
  -- Language-specific keybindings
  local languages = {}
  for _, kb in ipairs(grouped.language_specific) do
    local lang = kb.module:match('^lang:(.+)')
    if lang then
      languages[lang] = languages[lang] or {}
      table.insert(languages[lang], kb)
    end
  end
  
  for lang, kbs in pairs(languages) do
    table.insert(lines, '')
    table.insert(lines, string.format('## %s Keybindings', lang:upper()))
    table.insert(lines, '')
    table.insert(lines, '| Mode | Key | Command | Description |')
    table.insert(lines, '|------|-----|---------|-------------|')
    
    for _, kb in ipairs(kbs) do
      table.insert(lines, string.format('| `%s` | `%s` | `%s` | %s |',
        kb.mode, kb.key, kb.command, kb.desc))
    end
  end
  
  -- Leader key reference
  table.insert(lines, '')
  table.insert(lines, '## Leader Key Reference')
  table.insert(lines, '')
  table.insert(lines, '| Suffix | Key | Description | Module |')
  table.insert(lines, '|--------|-----|-------------|--------|')
  
  local leader_keys = {}
  for suffix, kbs in pairs(grouped.by_leader) do
    table.insert(leader_keys, {suffix = suffix, kb = kbs[1]})
  end
  
  table.sort(leader_keys, function(a, b) return a.suffix < b.suffix end)
  
  for _, entry in ipairs(leader_keys) do
    local kb = entry.kb
    table.insert(lines, string.format('| `%s` | `<leader>%s` | %s | %s |',
      entry.suffix, entry.suffix, kb.desc, kb.module))
  end
  
  return table.concat(lines, '\n')
end

-- Generate JSON output
M.generate_json = function(keybindings, grouped)
  local json_data = {
    summary = {
      total = #keybindings,
      global = #grouped.global,
      language_specific = #grouped.language_specific,
      generated_at = os.date('%Y-%m-%d %H:%M:%S'),
    },
    keybindings = keybindings,
    grouped = grouped,
  }
  
  -- Simple JSON serialization (for complex data, you'd want a proper JSON library)
  local function to_json(data, indent)
    indent = indent or 0
    local spaces = string.rep('  ', indent)
    
    if type(data) == 'table' then
      if #data > 0 then
        -- Array
        local items = {}
        for _, v in ipairs(data) do
          table.insert(items, to_json(v, indent + 1))
        end
        return '[\n' .. spaces .. '  ' .. table.concat(items, ',\n' .. spaces .. '  ') .. '\n' .. spaces .. ']'
      else
        -- Object
        local items = {}
        for k, v in pairs(data) do
          local key = string.format('"%s"', k)
          table.insert(items, key .. ': ' .. to_json(v, indent + 1))
        end
        return '{\n' .. spaces .. '  ' .. table.concat(items, ',\n' .. spaces .. '  ') .. '\n' .. spaces .. '}'
      end
    elseif type(data) == 'string' then
      return string.format('"%s"', data:gsub('"', '\\"'))
    elseif type(data) == 'number' then
      return tostring(data)
    else
      return 'null'
    end
  end
  
  return to_json(json_data)
end

-- Main function to scan and generate documentation
M.generate_docs = function(output_format, output_file)
  output_format = output_format or 'markdown'
  
  -- Scan configuration
  local keybindings = M.scan_config()
  local grouped = M.group_keybindings(keybindings)
  
  -- Generate output
  local content
  if output_format == 'markdown' then
    content = M.generate_markdown(keybindings, grouped)
  elseif output_format == 'json' then
    content = M.generate_json(keybindings, grouped)
  else
    error('Unsupported output format: ' .. output_format)
  end
  
  -- Write to file or return
  if output_file then
    local file = io.open(output_file, 'w')
    if file then
      file:write(content)
      file:close()
      print(string.format('Documentation written to: %s', output_file))
    else
      error('Could not write to file: ' .. output_file)
    end
  else
    return content
  end
end

-- Create user commands
M.create_commands = function()
  vim.api.nvim_create_user_command('KeymapScan', function(opts)
    local format = opts.args ~= '' and opts.args or 'markdown'
    local content = M.generate_docs(format)
    
    -- Create new buffer with content
    local buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, '\n'))
    
    if format == 'markdown' then
      vim.api.nvim_buf_set_option(buf, 'filetype', 'markdown')
    elseif format == 'json' then
      vim.api.nvim_buf_set_option(buf, 'filetype', 'json')
    end
    
    vim.api.nvim_set_current_buf(buf)
  end, {
    nargs = '?',
    complete = function() return { 'markdown', 'json' } end,
    desc = 'Scan configuration and show keybindings'
  })
  
  vim.api.nvim_create_user_command('KeymapScanToFile', function(opts)
    local args = vim.split(opts.args, ' ')
    local format = args[1] or 'markdown'
    local filename = args[2] or ('keybindings.' .. format)
    
    M.generate_docs(format, filename)
  end, {
    nargs = '*',
    desc = 'Scan configuration and save keybindings to file'
  })
end

-- Initialize the scanner
M.setup = function()
  M.create_commands()
end

return M