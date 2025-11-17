return { -- Fuzzy Finder (files, lsp, etc)
    'nvim-telescope/telescope.nvim',
    event = 'VimEnter',
    branch = '0.1.x',
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
      -- Get telescope config for vimgrep_arguments
      local telescopeConfig = require('telescope.config')
      local vimgrep_arguments = { unpack(telescopeConfig.values.vimgrep_arguments) }
      
      -- Add flags to search hidden files
      table.insert(vimgrep_arguments, "--hidden")
      -- Exclude .git directory
      table.insert(vimgrep_arguments, "--glob")
      table.insert(vimgrep_arguments, "!**/.git/*")

      require('telescope').setup {
        defaults = {
          -- Configure ripgrep to search hidden files
          vimgrep_arguments = vimgrep_arguments,
          mappings = {
            i = { 
              ['<c-enter>'] = 'to_fuzzy_refine',
              ['<C-h>'] = 'which_key', -- Show help for current picker
            },
          },
          -- Show hidden files in previews
          file_ignore_patterns = {
            "%.git/",
            "node_modules/",
            "%.DS_Store",
          },
        },
        pickers = {
          find_files = {
            -- Show hidden files by default
            hidden = true,
            -- Use ripgrep with hidden files
            find_command = { 'rg', '--files', '--hidden', '--glob', '!**/.git/*' },
          },
          live_grep = {
            -- Additional arguments for live_grep (already configured in defaults)
            additional_args = function()
              return { "--hidden", "--glob", "!**/.git/*" }
            end,
          },
          grep_string = {
            -- Additional arguments for grep_string
            additional_args = function()
              return { "--hidden", "--glob", "!**/.git/*" }
            end,
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

      -- See `:help telescope.builtin`
      local builtin = require 'telescope.builtin'
      vim.keymap.set('n', '<leader>sH', builtin.help_tags, { desc = '[S]earch [H]elp' })
      vim.keymap.set('n', '<leader>sk', builtin.keymaps, { desc = '[S]earch [K]eymaps' })
      vim.keymap.set('n', '<leader>sf', builtin.find_files, { desc = '[S]earch [F]iles' })
      vim.keymap.set('n', '<leader>ss', builtin.builtin, { desc = '[S]earch [S]elect Telescope' })
      vim.keymap.set('n', '<leader>sw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
      vim.keymap.set('n', '<leader>sg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
      vim.keymap.set('n', '<leader>sd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })
      vim.keymap.set('n', '<leader>sr', builtin.resume, { desc = '[S]earch [R]esume' })
      vim.keymap.set('n', '<leader>so', builtin.oldfiles, { desc = '[S]earch [O]ld files (recent)' })
      vim.keymap.set('n', '<leader><leader>', builtin.buffers, { desc = '[ ] Find existing buffers' })

      -- Slightly advanced example of overriding default behavior and theme
      vim.keymap.set('n', '<leader>/', function()
        -- You can pass additional configuration to Telescope to change the theme, layout, etc.
        builtin.current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
          winblend = 10,
          previewer = false,
        })
      end, { desc = '[/] Fuzzily search in current buffer' })

      -- It's also possible to pass additional configuration options.
      --  See `:help telescope.builtin.live_grep()` for information about particular keys
      vim.keymap.set('n', '<leader>s/', function()
        builtin.live_grep {
          grep_open_files = true,
          prompt_title = 'Live Grep in Open Files',
        }
      end, { desc = '[S]earch [/] in Open Files' })

      -- Shortcut for searching your Neovim configuration files
      vim.keymap.set('n', '<leader>sn', function()
        builtin.find_files { cwd = vim.fn.stdpath 'config' }
      end, { desc = '[S]earch [N]eovim files' })

      -- Additional keymaps for hidden file operations
      vim.keymap.set('n', '<leader>sh', function()
        builtin.find_files { hidden = true, no_ignore = true }
      end, { desc = '[S]earch [H]idden files (all)' })

      -- Search git files (including hidden)
      vim.keymap.set('n', '<leader>sG', function()
        builtin.git_files { show_untracked = true }
      end, { desc = '[S]earch [G]it files (with untracked)' })

      -- Search home dotfiles specifically
      vim.keymap.set('n', '<leader>s.', function()
        builtin.find_files { 
          cwd = vim.fn.expand('~'),
          hidden = true,
          search_dirs = { vim.fn.expand('~') },
          prompt_title = 'Search Dotfiles',
          find_command = { 'fd', '--type', 'f', '--hidden', '--follow', '--exclude', '.git' }
        }
      end, { desc = '[S]earch [.] dotfiles in home' })
    end,
  }
