-- General editor options
local opt = vim.opt

-- UI related
opt.breakindent = true -- Enable break indent
opt.cursorline = true -- Highlight current line
opt.laststatus = 3 -- Global statusline
opt.number = true -- Show line numbers
opt.relativenumber = true -- Show relative line numbers
opt.scrolloff = 10 -- Lines of context
opt.sidescrolloff = 8 -- Columns of context
opt.signcolumn = 'yes' -- Always show sign column
opt.splitbelow = true -- Force split below
opt.splitright = true -- Force split right
opt.termguicolors = true -- True color support
opt.wrap = true -- Disable line wrap
opt.showmode = false -- Don't show mode in command line
opt.cmdheight = 0 -- Hide command line unless needed
opt.pumheight = 10 -- Maximum number of items in popup menu
opt.conceallevel = 2 -- Show text normally

-- Editor behavior
opt.confirm = true -- Confirm before closing unsaved buffers
opt.expandtab = true -- Use spaces instead of tabs
opt.shiftround = true -- Round indent to multiple of shiftwidth
opt.shiftwidth = 2 -- Size of indent
opt.softtabstop = 2 -- Number of spaces tabs count for in insert mode
opt.tabstop = 2 -- Number of spaces tabs count for
opt.smartindent = true -- Insert indents automatically
opt.virtualedit = 'block' -- Allow cursor to move where there is no text in visual block mode
opt.formatoptions = 'jcroqlnt' -- tcqj
opt.grepformat = '%f:%l:%c:%m'
opt.grepprg = 'rg --vimgrep'

-- Search related
opt.hlsearch = true -- Highlight search results
opt.ignorecase = true -- Ignore case in search patterns
opt.smartcase = true -- Override ignorecase if search contains capitals
opt.inccommand = 'split' -- Preview substitutions live
opt.incsearch = true -- Show search matches while typing
opt.infercase = true -- Adjust case in insert completion mode

-- Project-local config: load .nvim.lua from project root on startup.
-- First encounter prompts to view + :trust the file (content-hashed, secure).
opt.exrc = true

-- File handling
opt.backup = false -- Don't create backup files
opt.swapfile = false -- Don't create swap files
opt.undofile = true -- Persistent undo
opt.undolevels = 10000 -- Maximum number of changes that can be undone
opt.writebackup = false -- Don't write backup files
opt.autowrite = true -- Auto write when possible
opt.autoread = true -- Auto read when file changes

-- System integration
-- Always use OSC 52 for copy so yanked text reaches the terminal's clipboard,
-- whether local or over SSH/nested tmux. Paste falls back to Neovim's internal
-- register because OSC 52 paste does not work inside tmux (tmux intercepts the
-- response, causing a 10s timeout). Use Ctrl+Shift+V to paste from the
-- terminal's clipboard into the session.
--
-- Custom copy: Neovim 0.11 removed DCS passthrough from vim.ui.clipboard.osc52,
-- breaking the nested-tmux chain (nvim → inner tmux → SSH → outer tmux → Alacritty).
-- We restore it: when inside tmux, wrap OSC 52 in DCS so allow-passthrough
-- unwraps it and passes raw OSC 52 to the outer tmux, which set-clipboard
-- forwards to Alacritty.
local function osc52_copy(reg)
  local clipboard = reg == '+' and 'c' or 'p'
  return function(lines)
    local s = table.concat(lines, '\n')
    local encoded = vim.base64.encode(s)
    local seq = string.format('\027]52;%s;%s\027\\', clipboard, encoded)
    if vim.env.TMUX then
      seq = '\027Ptmux;' .. seq:gsub('\027', '\027\027') .. '\027\\'
    end
    vim.api.nvim_chan_send(2, seq)
  end
end
local function paste()
  return { vim.fn.split(vim.fn.getreg('"'), '\n'), vim.fn.getregtype('"') }
end
vim.g.clipboard = {
  name = 'OSC 52',
  copy = {
    ['+'] = osc52_copy('+'),
    ['*'] = osc52_copy('*'),
  },
  paste = {
    ['+'] = paste,
    ['*'] = paste,
  },
}
opt.clipboard = 'unnamedplus' -- Use system clipboard
opt.mouse = 'a' -- Enable mouse support
opt.completeopt = 'menu,menuone,noselect' -- Better completion experience
opt.wildmode = 'longest:full,full' -- Command-line completion mode
opt.wildignore = { -- Ignore files matching these patterns
  '*/node_modules/*',
  '*/venv/*',
  '*.pyc',
  '*_build/*',
  '**/coverage/*',
  '**/dist/*',
  '**/target/*',
  '**/.git/*',
}

-- Performance
opt.timeoutlen = 300 -- Time to wait for mapped sequence to complete (in milliseconds)
opt.updatetime = 250 -- Faster completion
opt.redrawtime = 1500 -- Time in milliseconds for redrawing the display
opt.ttimeoutlen = 10 -- Time in milliseconds to wait for a key code sequence
-- NOTE: lazyredraw removed - causes issues with plugins like noice.nvim
opt.synmaxcol = 240 -- Maximum column in which to search for syntax items

-- Visual indicators
opt.list = true -- Show invisible characters
opt.listchars = {
  tab = '» ', -- Tab characters
  trail = '·', -- Trailing spaces
  nbsp = '␣', -- Non-breaking spaces
  extends = '›', -- Line continues beyond right
  precedes = '‹', -- Line continues beyond left
}
opt.shortmess:append { W = true, I = true, c = true, C = true }
opt.spelllang = { 'en' } -- Languages for spell checking

-- Folding (using treesitter for better folding)
opt.foldmethod = 'expr'
opt.foldexpr = 'v:lua.vim.treesitter.foldexpr()'
opt.foldtext = ''
opt.foldlevel = 99 -- Start with all folds open
opt.foldlevelstart = 99 -- Start with all folds open

-- Session and view options
opt.sessionoptions = {
  'buffers',
  'curdir',
  'tabpages',
  'winsize',
  'help',
  'globals',
  'skiprtp',
}
opt.viewoptions = {
  'cursor',
  'folds',
  'slash',
  'unix',
}

-- Window behavior
opt.winminwidth = 5 -- Minimum window width
opt.winminheight = 1 -- Minimum window height
opt.pumblend = 10 -- Popup menu transparency
opt.pumheight = 10 -- Maximum number of items to show in popup menu

-- Better diffing
opt.diffopt = {
  'algorithm:patience', -- Better diff algorithm
  'indent-heuristic', -- Better indent heuristic
  'linematch:60', -- Better line matching
}

-- Shell
opt.shell = vim.env.SHELL or 'bash' -- Shell to use for ! commands and :terminal

-- Project-local config (nvim 0.9+): read .nvim.lua / .nvimrc / .exrc from cwd
-- and parent dirs if they appear in the trust list (managed via :trust).
-- Used by dadbod.lua to let projects AUGMENT vim.g.dbs with repo-only DBs
-- without ever putting credentials in the dotfiles.
opt.exrc = true
