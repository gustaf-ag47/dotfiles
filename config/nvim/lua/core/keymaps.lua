local map = vim.keymap.set

local function opts(description, additional_opts)
  return vim.tbl_extend('force', { desc = description, silent = true }, additional_opts or {})
end

-- ╭──────────────────────────────────────────────────────────╮
-- │ File Operations                                          │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<leader>ww', ':w<CR>', opts 'Save file')
map('n', '<leader>wa', ':wa<CR>', opts 'Save all files')
map('n', '<leader>qq', ':q<CR>', opts 'Quit')
map('n', '<leader>qa', ':qa!<CR>', opts 'Quit all without saving')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Window Management                                        │
-- ╰──────────────────────────────────────────────────────────╯
-- NOTE: <C-h/j/k/l> navigation handled by vim-tmux-navigator plugin
map('n', '<leader>wv', '<C-w>v', opts 'Split vertical')
map('n', '<leader>ws', '<C-w>s', opts 'Split horizontal')
map('n', '<leader>we', '<C-w>=', opts 'Equalize splits')
map('n', '<leader>wx', ':close<CR>', opts 'Close split')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Buffer Navigation                                        │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<S-h>', ':bprevious<CR>', opts 'Previous buffer')
map('n', '<S-l>', ':bnext<CR>', opts 'Next buffer')
map('n', '<leader>bd', ':bdelete<CR>', opts 'Delete buffer')
map('n', '<leader>bo', ':%bd|e#|bd#<CR>', opts 'Close other buffers')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Search                                                   │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<Esc>', ':nohlsearch<CR>', opts 'Clear search highlighting')
map('n', '<leader>sr', ':%s/<C-r><C-w>//g<Left><Left>', opts 'Replace word under cursor')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Text Manipulation                                        │
-- ╰──────────────────────────────────────────────────────────╯
map('v', '<', '<gv', opts 'Unindent line')
map('v', '>', '>gv', opts 'Indent line')
map('v', 'J', ":m '>+1<CR>gv=gv", opts 'Move lines down')
map('v', 'K', ":m '<-2<CR>gv=gv", opts 'Move lines up')
map('v', 'p', '"_dP', opts 'Paste without yanking')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Diagnostics (x prefix)                                   │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '[d', vim.diagnostic.goto_prev, opts 'Previous diagnostic')
map('n', ']d', vim.diagnostic.goto_next, opts 'Next diagnostic')
map('n', '[e', function()
  vim.diagnostic.goto_prev { severity = vim.diagnostic.severity.ERROR }
end, opts 'Previous error')
map('n', ']e', function()
  vim.diagnostic.goto_next { severity = vim.diagnostic.severity.ERROR }
end, opts 'Next error')
map('n', '<leader>xd', vim.diagnostic.open_float, opts 'Show diagnostic')
map('n', '<leader>xq', vim.diagnostic.setloclist, opts 'Diagnostic loclist')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Terminal                                                 │
-- ╰──────────────────────────────────────────────────────────╯
map('t', '<C-h>', '<C-\\><C-N><C-w>h', opts 'Navigate left')
map('t', '<C-j>', '<C-\\><C-N><C-w>j', opts 'Navigate down')
map('t', '<C-k>', '<C-\\><C-N><C-w>k', opts 'Navigate up')
map('t', '<C-l>', '<C-\\><C-N><C-w>l', opts 'Navigate right')
map('t', '<Esc><Esc>', '<C-\\><C-n>', opts 'Exit terminal mode')

-- ╭──────────────────────────────────────────────────────────╮
-- │ File Explorer                                            │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '-', ':Oil<CR>', opts 'Open file explorer')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Quickfix                                                 │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '[q', ':cprevious<CR>', opts 'Previous quickfix')
map('n', ']q', ':cnext<CR>', opts 'Next quickfix')
map('n', '<leader>xo', ':copen<CR>', opts 'Open quickfix')
map('n', '<leader>xc', ':cclose<CR>', opts 'Close quickfix')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Movement                                                 │
-- ╰──────────────────────────────────────────────────────────╯
map('n', 'j', "v:count == 0 ? 'gj' : 'j'", { expr = true, silent = true })
map('n', 'k', "v:count == 0 ? 'gk' : 'k'", { expr = true, silent = true })
map('n', '<C-d>', '<C-d>zz', opts 'Scroll down centered')
map('n', '<C-u>', '<C-u>zz', opts 'Scroll up centered')
map('n', '<C-f>', '<C-f>zz', opts 'Page down centered')
map('n', '<C-b>', '<C-b>zz', opts 'Page up centered')
map('n', 'n', 'nzzzv', opts 'Next search centered')
map('n', 'N', 'Nzzzv', opts 'Prev search centered')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Tabs (gt/gT are default, these are extras)               │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<leader><Tab>n', ':tabnew<CR>', opts 'New tab')
map('n', '<leader><Tab>x', ':tabclose<CR>', opts 'Close tab')
map('n', '<leader><Tab>]', ':tabn<CR>', opts 'Next tab')
map('n', '<leader><Tab>[', ':tabp<CR>', opts 'Prev tab')

-- ╭──────────────────────────────────────────────────────────╮
-- │ UI Toggles (u prefix)                                    │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<leader>uw', ':set wrap!<CR>', opts 'Toggle wrap')
map('n', '<leader>ul', ':set list!<CR>', opts 'Toggle list chars')
map('n', '<leader>un', ':set number!<CR>', opts 'Toggle line numbers')
map('n', '<leader>ur', ':set relativenumber!<CR>', opts 'Toggle relative numbers')
map('n', '<leader>us', ':set spell!<CR>', opts 'Toggle spell')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Misc                                                     │
-- ╰──────────────────────────────────────────────────────────╯
map('n', "'", '`', opts 'Go to mark (exact)')
map('n', '<C-a>', 'gg<S-v>G', opts 'Select all')
map('c', 'w!!', 'w !sudo tee > /dev/null %', opts 'Sudo save')
map('n', 'g+', '<C-a>', opts 'Increment number')
map('n', 'g-', '<C-x>', opts 'Decrement number')

-- ╭──────────────────────────────────────────────────────────╮
-- │ Lua Execution                                            │
-- ╰──────────────────────────────────────────────────────────╯
map('n', '<leader>xx', '<cmd>source %<CR>', opts 'Source file')
map('n', '<leader>xl', ':.lua<CR>', opts 'Execute Lua line')
map('v', '<leader>xl', ':lua<CR>', opts 'Execute Lua selection')
