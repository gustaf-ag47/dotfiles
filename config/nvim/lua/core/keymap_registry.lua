-- Keymap registry - provides centralized VIEWING without violating architecture
-- This module OBSERVES keymaps but doesn't DEFINE them
-- Each language module still owns and defines its own keybindings

local M = {}

-- Registry to track keymaps for documentation/conflict detection
M.registry = {
  global = {},
  by_filetype = {},
  by_module = {},
}

-- Register a keymap (called by modules when they set keymaps)
M.register = function(opts)
  local entry = {
    lhs = opts.lhs,
    rhs = opts.rhs or opts.callback,
    desc = opts.desc or '',
    mode = opts.mode or 'n',
    module = opts.module or 'unknown',
    filetype = opts.filetype,
    buffer = opts.buffer,
    created_at = os.time(),
  }

  -- Store in appropriate registry
  if opts.filetype then
    M.registry.by_filetype[opts.filetype] = M.registry.by_filetype[opts.filetype] or {}
    table.insert(M.registry.by_filetype[opts.filetype], entry)
  elseif opts.buffer then
    -- Buffer-local keymap
    local bufnr = opts.buffer == true and vim.api.nvim_get_current_buf() or opts.buffer
    M.registry.by_module[opts.module] = M.registry.by_module[opts.module] or {}
    table.insert(M.registry.by_module[opts.module], entry)
  else
    -- Global keymap
    table.insert(M.registry.global, entry)
  end
end

-- Enhanced keymap setter that automatically registers
M.set = function(mode, lhs, rhs, opts)
  opts = opts or {}

  -- Set the actual keymap
  vim.keymap.set(mode, lhs, rhs, opts)

  -- Register for tracking
  M.register({
    lhs = lhs,
    rhs = rhs,
    desc = opts.desc,
    mode = mode,
    module = opts.module,
    filetype = opts.filetype,
    buffer = opts.buffer,
  })
end

-- Show all keymaps by category
M.show_all = function()
  print('=== Global Keymaps ===')
  for _, map in ipairs(M.registry.global) do
    print(string.format('  %s: %s -> %s (%s)', map.mode, map.lhs, map.desc, map.module))
  end

  print('\n=== By Filetype ===')
  for ft, maps in pairs(M.registry.by_filetype) do
    print(string.format('  %s:', ft))
    for _, map in ipairs(maps) do
      print(string.format('    %s: %s -> %s', map.mode, map.lhs, map.desc))
    end
  end

  print('\n=== By Module ===')
  for module, maps in pairs(M.registry.by_module) do
    print(string.format('  %s:', module))
    for _, map in ipairs(maps) do
      print(string.format('    %s: %s -> %s', map.mode, map.lhs, map.desc))
    end
  end
end

-- Show keymaps for specific filetype
M.show_for_filetype = function(filetype)
  local maps = M.registry.by_filetype[filetype] or {}
  print(string.format('=== Keymaps for %s ===', filetype))
  for _, map in ipairs(maps) do
    print(string.format('  %s: %s -> %s (%s)', map.mode, map.lhs, map.desc, map.module))
  end
end

-- Detect keymap conflicts
M.check_conflicts = function()
  local conflicts = {}
  local seen = {}

  -- Check global conflicts
  for _, map in ipairs(M.registry.global) do
    local key = map.mode .. ':' .. map.lhs
    if seen[key] then
      table.insert(conflicts, {
        key = key,
        first = seen[key],
        second = map,
      })
    else
      seen[key] = map
    end
  end

  if #conflicts > 0 then
    print('❌ Keymap conflicts detected:')
    for _, conflict in ipairs(conflicts) do
      print(string.format('  %s: %s vs %s',
        conflict.key, conflict.first.module, conflict.second.module))
    end
  else
    print('✅ No keymap conflicts detected')
  end

  return conflicts
end

-- Export keymap documentation
M.export_docs = function(format)
  format = format or 'markdown'

  if format == 'markdown' then
    local lines = { '# Keybinding Reference', '' }

    -- Global keymaps
    table.insert(lines, '## Global Keybindings')
    table.insert(lines, '')
    table.insert(lines, '| Mode | Key | Description | Module |')
    table.insert(lines, '|------|-----|-------------|--------|')

    for _, map in ipairs(M.registry.global) do
      table.insert(lines, string.format('| %s | `%s` | %s | %s |',
        map.mode, map.lhs, map.desc, map.module))
    end

    -- Language-specific keymaps
    for ft, maps in pairs(M.registry.by_filetype) do
      table.insert(lines, '')
      table.insert(lines, string.format('## %s Keybindings', ft:upper()))
      table.insert(lines, '')
      table.insert(lines, '| Mode | Key | Description |')
      table.insert(lines, '|------|-----|-------------|')

      for _, map in ipairs(maps) do
        table.insert(lines, string.format('| %s | `%s` | %s |',
          map.mode, map.lhs, map.desc))
      end
    end

    return table.concat(lines, '\n')
  end
end

-- Create user commands for keymap management
M.create_commands = function()
  vim.api.nvim_create_user_command('KeymapShow', function(opts)
    if opts.args == '' then
      M.show_all()
    else
      M.show_for_filetype(opts.args)
    end
  end, {
    nargs = '?',
    complete = function()
      return vim.tbl_keys(M.registry.by_filetype)
    end,
    desc = 'Show keymaps (optionally for specific filetype)'
  })

  vim.api.nvim_create_user_command('KeymapConflicts', function()
    M.check_conflicts()
  end, { desc = 'Check for keymap conflicts' })

  vim.api.nvim_create_user_command('KeymapDocs', function(opts)
    local docs = M.export_docs(opts.args)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(docs, '\n'))
    vim.api.nvim_buf_set_option(buf, 'filetype', 'markdown')
    vim.api.nvim_set_current_buf(buf)
  end, {
    nargs = '?',
    complete = function() return { 'markdown' } end,
    desc = 'Generate keymap documentation'
  })
end

return M