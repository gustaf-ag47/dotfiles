-- Anki integration for Obsidian vault
-- Telescope picker, sync command, stats, and syntax highlighting for %%anki%% blocks

local vault_path = vim.fn.expand('~/sync/Vault')
local anki_script = vault_path .. '/_scripts/anki.py'

-- Highlight %%anki%% blocks in markdown
local function setup_anki_highlights()
  local ns = vim.api.nvim_create_namespace('anki_blocks')

  vim.api.nvim_set_hl(0, 'AnkiDelimiter', { fg = '#7aa2f7', bold = true })
  vim.api.nvim_set_hl(0, 'AnkiFieldKey', { fg = '#bb9af7', bold = true })
  vim.api.nvim_set_hl(0, 'AnkiFieldValue', { fg = '#9ece6a' })
  vim.api.nvim_set_hl(0, 'AnkiBlock', { bg = '#1a1b26' })

  local function highlight_buffer(buf)
    buf = buf or vim.api.nvim_get_current_buf()
    vim.api.nvim_buf_clear_namespace(buf, ns, 0, -1)

    local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
    local in_block = false

    for lnum, line in ipairs(lines) do
      if line:match('^%%%%anki%%%%') then
        in_block = true
        vim.api.nvim_buf_add_highlight(buf, ns, 'AnkiDelimiter', lnum - 1, 0, -1)
      elseif line:match('^%%%%end%%%%') and in_block then
        vim.api.nvim_buf_add_highlight(buf, ns, 'AnkiDelimiter', lnum - 1, 0, -1)
        in_block = false
      elseif in_block then
        vim.api.nvim_buf_add_highlight(buf, ns, 'AnkiBlock', lnum - 1, 0, -1)
        local key_end = line:find(':')
        if key_end then
          vim.api.nvim_buf_add_highlight(buf, ns, 'AnkiFieldKey', lnum - 1, 0, key_end)
          vim.api.nvim_buf_add_highlight(buf, ns, 'AnkiFieldValue', lnum - 1, key_end, -1)
        end
      end
    end
  end

  vim.api.nvim_create_autocmd({ 'BufEnter', 'TextChanged', 'TextChangedI' }, {
    pattern = '*.md',
    callback = function(ev)
      highlight_buffer(ev.buf)
    end,
    group = vim.api.nvim_create_augroup('AnkiHighlight', { clear = true }),
  })
end

-- Telescope picker: browse all flashcards in the vault
local function anki_picker()
  local pickers = require('telescope.pickers')
  local finders = require('telescope.finders')
  local conf = require('telescope.config').values
  local actions = require('telescope.actions')
  local action_state = require('telescope.actions.state')
  local previewers = require('telescope.previewers')
  local Job = require('plenary.job')

  local entries = {}
  local rg_results = {}

  Job:new({
    command = 'rg',
    args = { '--no-heading', '-n', '%%anki%%', vault_path, '--glob', '*.md' },
    on_stdout = function(_, line)
      table.insert(rg_results, line)
    end,
  }):sync(5000)

  local parsed_files = {}
  for _, line in ipairs(rg_results) do
    local file, lnum = line:match('^(.+):(%d+):')
    if file and not parsed_files[file] then
      parsed_files[file] = true
      local f = io.open(file, 'r')
      if f then
        local content = f:read('*a')
        f:close()
        -- Track line numbers of each %%anki%% occurrence
        local current_line = 0
        local block_starts = {}
        for l in content:gmatch('[^\n]*\n?') do
          current_line = current_line + 1
          if l:match('^%%%%anki%%%%') then
            table.insert(block_starts, current_line)
          end
        end

        local block_idx = 1
        for block in content:gmatch('%%%%anki%%%%(.-)\n%%%%end%%%%') do
          local front = block:match('front:%s*(.-)\n') or '(no front)'
          local card_type = block:match('type:%s*(%w+)') or 'basic'
          local tags = block:match('tags:%s*(.-)\n') or ''
          local back = block:match('back:%s*(.-)\n') or ''
          local rel_path = file:gsub(vim.pesc(vault_path) .. '/', '')
          local start_line = block_starts[block_idx] or 1

          table.insert(entries, {
            display = string.format('[%s] %s', card_type, front:sub(1, 80)),
            front = front,
            back = back,
            card_type = card_type,
            tags = tags,
            file = file,
            lnum = start_line,
            rel_path = rel_path,
          })
          block_idx = block_idx + 1
        end
      end
    end
  end

  pickers.new({}, {
    prompt_title = 'Anki Flashcards (' .. #entries .. ' cards)',
    finder = finders.new_table({
      results = entries,
      entry_maker = function(entry)
        return {
          value = entry,
          display = entry.display,
          ordinal = entry.front .. ' ' .. entry.tags .. ' ' .. entry.rel_path,
          filename = entry.file,
          lnum = entry.lnum,
        }
      end,
    }),
    sorter = conf.generic_sorter({}),
    previewer = previewers.new_buffer_previewer({
      title = 'Flashcard Preview',
      define_preview = function(self, entry, _)
        local card = entry.value
        local preview_lines = {
          '  Type: ' .. card.card_type,
          '  Tags: ' .. card.tags,
          '  File: ' .. card.rel_path,
          '',
          '── Front ──────────────────────────',
          '',
          '  ' .. card.front,
          '',
          '── Back ───────────────────────────',
          '',
          '  ' .. card.back,
        }
        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, preview_lines)
      end,
    }),
    attach_mappings = function(prompt_bufnr, _)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection then
          vim.cmd('edit ' .. vim.fn.fnameescape(selection.value.file))
          vim.api.nvim_win_set_cursor(0, { selection.value.lnum, 0 })
          vim.cmd('normal! zz')
        end
      end)
      return true
    end,
  }):find()
end

-- Sync flashcards to Anki via anki.py
local function anki_sync()
  vim.notify('Syncing flashcards to Anki...', vim.log.levels.INFO)
  vim.fn.jobstart({ 'python', anki_script }, {
    env = { NOTES = vault_path },
    stdout_buffered = true,
    stderr_buffered = true,
    on_stdout = function(_, data)
      if data and data[1] ~= '' then
        vim.schedule(function()
          vim.notify(table.concat(data, '\n'), vim.log.levels.INFO, { title = 'Anki Sync' })
        end)
      end
    end,
    on_stderr = function(_, data)
      if data and data[1] ~= '' then
        vim.schedule(function()
          vim.notify(table.concat(data, '\n'), vim.log.levels.ERROR, { title = 'Anki Sync' })
        end)
      end
    end,
    on_exit = function(_, code)
      vim.schedule(function()
        if code == 0 then
          vim.notify('Syncing to AnkiWeb...', vim.log.levels.INFO, { title = 'Anki Sync' })
          vim.fn.jobstart({ 'curl', '-s', '-X', 'POST', 'http://localhost:8765', '-d', '{"action":"sync","version":6}' }, {
            stdout_buffered = true,
            on_exit = function(_, sync_code)
              vim.schedule(function()
                if sync_code == 0 then
                  vim.notify('Synced to AnkiWeb!', vim.log.levels.INFO, { title = 'Anki Sync' })
                else
                  vim.notify('AnkiWeb sync failed', vim.log.levels.ERROR, { title = 'Anki Sync' })
                end
              end)
            end,
          })
        else
          vim.notify('Anki sync failed (exit ' .. code .. ')', vim.log.levels.ERROR, { title = 'Anki Sync' })
        end
      end)
    end,
  })
end

-- Count flashcards in current buffer and vault
local function anki_stats()
  local buf_content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\n')
  local buf_count = 0
  for _ in buf_content:gmatch('%%%%anki%%%%') do
    buf_count = buf_count + 1
  end

  local Job = require('plenary.job')
  local vault_count = 0
  local file_count = 0

  Job:new({
    command = 'rg',
    args = { '--count', '%%anki%%', vault_path, '--glob', '*.md' },
    on_stdout = function(_, line)
      local count = line:match(':(%d+)$')
      if count then
        vault_count = vault_count + tonumber(count)
        file_count = file_count + 1
      end
    end,
  }):sync(5000)

  local buf_name = vim.fn.expand('%:t')
  vim.notify(
    string.format('Buffer (%s): %d cards\nVault: %d cards across %d files', buf_name, buf_count, vault_count, file_count),
    vim.log.levels.INFO,
    { title = 'Anki Stats' }
  )
end

-- Return as a virtual local plugin (no dir needed — lazy.nvim loads this file via import)
return {
  'anki-nvim',
  virtual = true,
  ft = 'markdown',
  dependencies = {
    'nvim-telescope/telescope.nvim',
    'nvim-lua/plenary.nvim',
  },
  config = function()
    setup_anki_highlights()

    vim.api.nvim_create_user_command('AnkiSync', anki_sync, { desc = 'Sync flashcards to Anki via AnkiConnect' })
    vim.api.nvim_create_user_command('AnkiStats', anki_stats, { desc = 'Show flashcard statistics' })
    vim.api.nvim_create_user_command('AnkiBrowse', anki_picker, { desc = 'Browse flashcards with Telescope' })

    -- Keymaps under <leader>K for Anki (Knowledge)
    local map = vim.keymap.set
    map('n', '<leader>Kb', anki_picker, { desc = 'Browse flashcards' })
    map('n', '<leader>Ks', anki_sync, { desc = 'Sync to Anki' })
    map('n', '<leader>Ki', anki_stats, { desc = 'Flashcard stats' })
  end,
}
