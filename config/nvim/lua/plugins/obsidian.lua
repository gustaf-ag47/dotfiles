return {
  'epwalsh/obsidian.nvim',
  version = '*',
  lazy = true,
  ft = 'markdown',
  -- Only activate for files inside the Obsidian vault
  cond = function()
    local vault = vim.fn.resolve(vim.fn.expand '~/sync/Vault')
    local cwd = vim.fn.resolve(vim.fn.getcwd())
    return vim.startswith(cwd, vault)
  end,
  dependencies = {
    'nvim-lua/plenary.nvim',
  },
  opts = {
    workspaces = {
      {
        name = 'personal',
        path = '~/sync/Vault',
      },
    },

    templates = {
      folder = '_templates',
      date_format = '%Y-%m-%d',
      time_format = '%H:%M',
    },

    daily_notes = {
      folder = 'Journal/Daily',
      date_format = '%Y-%m-%d',
      template = 'daily-note.md',
    },

    note_id_func = function(title)
      if title then
        return title:gsub(' ', '-'):gsub('[^A-Za-z0-9-]', ''):lower()
      end
      return tostring(os.time())
    end,

    -- Put new notes in Inbox for triage
    new_notes_location = 'notes_subdir',
    notes_subdir = 'Inbox',

    attachments = {
      img_folder = 'Attachments',
    },

    ui = {
      enable = false, -- render-markdown.nvim handles this
    },
  },
  config = function(_, opts)
    require('obsidian').setup(opts)

    local vault = vim.fn.expand(vim.env.NOTES or '~/sync/Vault')

    -- `reading` (dotfiles bin/reading) owns books.json, kosync and zathura's D-Bus.
    local function reading(args)
      local out = vim.fn.systemlist(vim.list_extend({ 'reading' }, args))
      if vim.v.shell_error ~= 0 then
        vim.notify(table.concat(out, '\n'), vim.log.levels.WARN)
        return nil
      end
      return out
    end

    -- :BookNew [query] - pick a Calibre book, create its zettel-literature note in
    -- 30 Knowledge/Sources with file_path filled in (progress stays in kosync).
    vim.api.nvim_create_user_command('BookNew', function(cmd)
      local query = cmd.args ~= '' and cmd.args or vim.fn.input 'Book (title/author): '
      if query == '' then
        return
      end
      local rows = reading { 'search', query } or {}
      if #rows == 0 then
        vim.notify('No Calibre book matches "' .. query .. '"', vim.log.levels.WARN)
        return
      end
      vim.ui.select(rows, {
        prompt = 'Literature note for',
        format_item = function(row)
          local _, title, author = unpack(vim.split(row, '\t'))
          return title .. (author ~= '' and ('  -  ' .. author) or '')
        end,
      }, function(row)
        if not row then
          return
        end
        local path = reading { 'note', 'new', vim.split(row, '\t')[1] }
        if path and path[1] then
          vim.cmd('edit ' .. vim.fn.fnameescape(path[1]))
        end
      end)
    end, { nargs = '?', desc = 'Create a literature note for a Calibre book' })

    local function in_vault(buf)
      local name = vim.fn.resolve(vim.api.nvim_buf_get_name(buf))
      return vim.startswith(name, vim.fn.resolve(vault))
    end

    -- Page under the cursor: "p. 46", "p.46" or "pp. 46-48" (first page).
    local function cited_page()
      local line, col = vim.api.nvim_get_current_line(), vim.fn.col '.'
      local best
      for s, num, e in line:gmatch '()pp?%.%s*(%d+)()' do
        if not best or (s <= col and col <= e) then
          best = tonumber(num)
        end
        if s <= col and col <= e then
          break
        end
      end
      return best
    end

    vim.api.nvim_create_autocmd('FileType', {
      pattern = 'markdown',
      group = vim.api.nvim_create_augroup('reading-zathura', { clear = true }),
      callback = function(ev)
        if not in_vault(ev.buf) then
          return
        end
        local note = function()
          return vim.api.nvim_buf_get_name(ev.buf)
        end
        vim.keymap.set('n', '<leader>zp', function()
          local out = reading { 'page', '--note', note() }
          if out and out[1] then
            vim.api.nvim_put({ 'p. ' .. out[1] }, 'c', true, true)
          end
        end, { buffer = ev.buf, desc = 'Reading: insert page cite from zathura' })
        vim.keymap.set('n', '<leader>zg', function()
          local page = cited_page()
          if not page then
            vim.notify('No "p. N" on this line', vim.log.levels.WARN)
            return
          end
          reading { 'goto', tostring(page), '--note', note() }
        end, { buffer = ev.buf, desc = 'Reading: jump zathura to the cited page' })
      end,
    })
  end,
}
