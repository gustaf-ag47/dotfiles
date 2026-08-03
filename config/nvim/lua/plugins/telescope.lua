return { -- Fuzzy Finder (files, lsp, etc)
  'nvim-telescope/telescope.nvim',
  cmd = 'Telescope',
  version = '*',
  keys = {
    { '<leader>sh', '<cmd>Telescope help_tags<cr>', desc = 'Help tags' },
    { '<leader>sk', '<cmd>Telescope keymaps<cr>', desc = 'Keymaps' },
    { '<leader>sf', '<cmd>Telescope find_files<cr>', desc = 'Files' },
    { '<leader>ss', '<cmd>Telescope builtin<cr>', desc = 'Telescope pickers' },
    { '<leader>sw', '<cmd>Telescope grep_string<cr>', desc = 'Word under cursor' },
    { '<leader>sg', '<cmd>Telescope live_grep<cr>', desc = 'Grep' },
    { '<leader>sd', '<cmd>Telescope diagnostics<cr>', desc = 'Diagnostics' },
    { '<leader>so', '<cmd>Telescope resume<cr>', desc = 'Resume last' },
    { '<leader>s.', '<cmd>Telescope oldfiles<cr>', desc = 'Recent files' },
    { '<leader>sb', '<cmd>Telescope buffers<cr>', desc = 'Buffers' },
    { '<leader><leader>', '<cmd>Telescope buffers<cr>', desc = 'Buffers' },
  },
  dependencies = {
    'nvim-lua/plenary.nvim',
    { -- If encountering errors, see telescope-fzf-native README for installation instructions
      'nvim-telescope/telescope-fzf-native.nvim',

      -- `build` is used to run some command when the plugin is installed/updated.
      -- This is only run then, not every time Neovim starts up.
      build = 'make',

      -- `cond` is a condition used to determine whether this plugin should be
      -- installed and loaded.
      cond = function()
        return vim.fn.executable 'make' == 1
      end,
    },
    { 'nvim-telescope/telescope-ui-select.nvim' },

    -- Useful for getting pretty icons, but requires a Nerd Font.
    { 'nvim-tree/nvim-web-devicons', enabled = vim.g.have_nerd_font },
  },
  config = function()
    -- Telescope is a fuzzy finder that comes with a lot of different things that
    -- it can fuzzy find! It's more than just a "file finder", it can search
    -- many different aspects of Neovim, your workspace, LSP, and more!
    --
    -- The easiest way to use Telescope, is to start by doing something like:
    --  :Telescope help_tags
    --
    -- After running this command, a window will open up and you're able to
    -- type in the prompt window. You'll see a list of `help_tags` options and
    -- a corresponding preview of the help.
    --
    -- Two important keymaps to use while in Telescope are:
    --  - Insert mode: <c-/>
    --  - Normal mode: ?
    --
    -- This opens a window that shows you all of the keymaps for the current
    -- Telescope picker. This is really useful to discover what Telescope can
    -- do as well as how to actually do it!

    -- [[ Configure Telescope ]]
    -- See `:help telescope` and `:help telescope.setup()`
    require('telescope').setup {
      defaults = {
        -- Ignore generated / dependency dirs so find_files stays fast on large monorepos
        file_ignore_patterns = {
          '^vendor/',
          '^var/',
          '^node_modules/',
          '^%.git/',
          '^public/bundles/',
          '^public/build/',
          '^%.cache/',
          '^docker/mysql/data/',
        },
        vimgrep_arguments = {
          'rg',
          '--color=never',
          '--no-heading',
          '--with-filename',
          '--line-number',
          '--column',
          '--smart-case',
          '--glob',
          '!vendor/*',
          '--glob',
          '!var/*',
          '--glob',
          '!node_modules/*',
        },
      },
      extensions = {
        ['ui-select'] = {
          require('telescope.themes').get_dropdown(),
        },
      },
    }

    -- Enable Telescope extensions if they are installed
    pcall(require('telescope').load_extension, 'fzf')
    pcall(require('telescope').load_extension, 'ui-select')

    -- Additional keymaps that need custom functions
    local builtin = require 'telescope.builtin'

    -- Fuzzy search in current buffer
    vim.keymap.set('n', '<leader>/', function()
      builtin.current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
        winblend = 10,
        previewer = false,
      })
    end, { desc = 'Search in buffer' })

    -- Search in open files
    vim.keymap.set('n', '<leader>s/', function()
      builtin.live_grep {
        grep_open_files = true,
        prompt_title = 'Live Grep in Open Files',
      }
    end, { desc = 'Grep open files' })

    -- Search Neovim config files
    vim.keymap.set('n', '<leader>sn', function()
      builtin.find_files { cwd = vim.fn.stdpath 'config' }
    end, { desc = 'Neovim config' })

    -- Enhanced symbol search keymaps (JetBrains-like "Search Everywhere")

    -- Workspace symbols with common filters
    vim.keymap.set('n', '<leader>lS', function()
      builtin.lsp_dynamic_workspace_symbols {
        symbols = {
          'Class',
          'Function',
          'Method',
          'Constructor',
          'Interface',
          'Module',
          'Struct',
          'Trait',
          'Field',
          'Property',
        },
      }
    end, { desc = 'Workspace symbols (filtered)' })

    -- Search only functions/methods
    vim.keymap.set('n', '<leader>lf', function()
      builtin.lsp_dynamic_workspace_symbols {
        symbols = { 'Function', 'Method' },
      }
    end, { desc = 'Functions/Methods' })

    -- Search only classes/types
    vim.keymap.set('n', '<leader>lc', function()
      builtin.lsp_dynamic_workspace_symbols {
        symbols = { 'Class', 'Interface', 'Struct', 'Enum' },
      }
    end, { desc = 'Classes/Types' })

    -- Search all symbols (like JetBrains Search Everywhere)
    vim.keymap.set('n', '<leader>l/', function()
      builtin.lsp_dynamic_workspace_symbols()
    end, { desc = 'All symbols' })

    -- Symfony monorepo module picker: search across modules/ src/ contexts/
    vim.keymap.set('n', '<leader>sm', function()
      builtin.find_files {
        prompt_title = 'Symfony: modules / src / contexts',
        search_dirs = { 'modules', 'src', 'contexts' },
      }
    end, { desc = 'Symfony module files' })
  end,
}
