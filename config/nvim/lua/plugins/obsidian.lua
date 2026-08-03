return {
  'epwalsh/obsidian.nvim',
  version = '*',
  lazy = true,
  ft = 'markdown',
  -- Only activate for files inside the Obsidian vault
  cond = function()
    local vault = vim.fn.resolve(vim.fn.expand('~/sync/Vault'))
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

    local vault = vim.fn.expand('~/sync/Vault')
    local books_dir = vault .. '/PARA/3_RESOURCES/Books'

    -- :BookNew — create a new literature note in Books/
    vim.api.nvim_create_user_command('BookNew', function()
      local title = vim.fn.input('Book title: ')
      if title == '' then return end

      local slug = title:gsub('%s+', '-'):gsub('[^%w-]', ''):lower()
      local filepath = books_dir .. '/' .. slug .. '.md'

      if vim.fn.filereadable(filepath) == 1 then
        vim.notify('Book note already exists: ' .. slug .. '.md', vim.log.levels.WARN)
        vim.cmd('edit ' .. vim.fn.fnameescape(filepath))
        return
      end

      vim.cmd('edit ' .. vim.fn.fnameescape(filepath))
      -- Trigger Templater if available, otherwise insert template via ObsidianTemplate
      vim.defer_fn(function()
        vim.cmd('ObsidianTemplate zettel-literature')
      end, 100)
    end, { desc = 'Create new book/literature note' })
  end,
}
