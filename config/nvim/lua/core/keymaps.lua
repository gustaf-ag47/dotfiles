local map = vim.keymap.set

local function opts(description, additional_opts)
  return vim.tbl_extend('force', { desc = description, silent = true }, additional_opts or {})
end

-- File operations
map('n', '<leader>w', ':w<CR>', opts 'Save file')
map('n', '<leader>W', ':wa<CR>', opts 'Save all files')
map('n', '<leader>q', ':q<CR>', opts 'Quit')
map('n', '<leader>Q', ':qa!<CR>', opts 'Quit without saving')

-- Window navigation
map('n', '<C-h>', '<C-w>h', opts 'Navigate left window')
map('n', '<C-j>', '<C-w>j', opts 'Navigate down window')
map('n', '<C-k>', '<C-w>k', opts 'Navigate up window')
map('n', '<C-l>', '<C-w>l', opts 'Navigate right window')

-- Window management
map('n', '<leader>sv', '<C-w>v', opts 'Split window vertically')
map('n', '<leader>sh', '<C-w>s', opts 'Split window horizontally')
map('n', '<leader>se', '<C-w>=', opts 'Make splits equal size')
map('n', '<leader>sx', ':close<CR>', opts 'Close current split')

-- Buffer navigation
map('n', '<S-h>', ':bprevious<CR>', opts 'Previous buffer')
map('n', '<S-l>', ':bnext<CR>', opts 'Next buffer')
map('n', '<leader>bd', ':bdelete<CR>', opts 'Delete buffer')

-- Search and replace
map('n', '<leader>h', ':nohlsearch<CR>', opts 'Clear search highlighting')
map('n', '<leader>r', ':%s/<C-r><C-w>//g<Left><Left>', opts 'Replace word under cursor')

-- Text manipulation
map('v', '<', '<gv', opts 'Unindent line')
map('v', '>', '>gv', opts 'Indent line')
map('v', 'J', ":m '>+1<CR>gv=gv", opts 'Move selected lines down')
map('v', 'K', ":m '<-2<CR>gv=gv", opts 'Move selected lines up')
map('v', 'p', '"_dP', opts 'Paste without yanking')

-- Diagnostic navigation
map('n', '[d', vim.diagnostic.goto_prev, opts 'Previous diagnostic')
map('n', ']d', vim.diagnostic.goto_next, opts 'Next diagnostic')
map('n', '<leader>d', vim.diagnostic.open_float, opts 'Show diagnostic message')
map('n', '<leader>ql', vim.diagnostic.setloclist, opts 'Open diagnostic list')

-- Terminal navigation
map('t', '<C-h>', '<C-\\><C-N><C-w>h', opts 'Terminal navigate left')
map('t', '<C-j>', '<C-\\><C-N><C-w>j', opts 'Terminal navigate down')
map('t', '<C-k>', '<C-\\><C-N><C-w>k', opts 'Terminal navigate up')
map('t', '<C-l>', '<C-\\><C-N><C-w>l', opts 'Terminal navigate right')
map('t', '<Esc><Esc>', '<C-\\><C-n>', opts 'Exit terminal mode')

-- File explorer
map('n', '<leader>o', ':Oil<CR>', opts 'Open file explorer')

-- Quickfix navigation
map('n', '[q', ':cprevious<CR>', opts 'Previous quickfix item')
map('n', ']q', ':cnext<CR>', opts 'Next quickfix item')
map('n', '<leader>co', ':copen<CR>', opts 'Open quickfix list')
map('n', '<leader>cc', ':cclose<CR>', opts 'Close quickfix list')

-- Better up/down movement
map('n', 'j', "v:count == 0 ? 'gj' : 'j'", { expr = true, silent = true })
map('n', 'k', "v:count == 0 ? 'gk' : 'k'", { expr = true, silent = true })

-- Centered scrolling
map('n', '<C-d>', '<C-d>zz', opts 'Scroll down and center')
map('n', '<C-u>', '<C-u>zz', opts 'Scroll up and center')
map('n', '<C-f>', '<C-f>zz', opts 'Scroll page down and center')
map('n', '<C-b>', '<C-b>zz', opts 'Scroll page up and center')
map('n', 'n', 'nzzzv', opts 'Next search result and center')
map('n', 'N', 'Nzzzv', opts 'Previous search result and center')

-- Tabs
map('n', '<leader>to', ':tabnew<CR>', opts 'Open new tab')
map('n', '<leader>tx', ':tabclose<CR>', opts 'Close current tab')
map('n', '<leader>tn', ':tabn<CR>', opts 'Next tab')
map('n', '<leader>tp', ':tabp<CR>', opts 'Previous tab')

-- Marks
map('n', "'", '`', opts 'Go to mark exact position')

-- Select all
map('n', '<C-a>', 'gg<S-v>G', opts 'Select all')

-- Save with root permission
map('c', 'w!!', 'w !sudo tee > /dev/null %', opts 'Save with root permission')

-- Toggle options
map('n', '<leader>uw', ':set wrap!<CR>', opts 'Toggle word wrap')
map('n', '<leader>ul', ':set list!<CR>', opts 'Toggle hidden characters')
map('n', '<leader>un', ':set number!<CR>', opts 'Toggle line numbers')
map('n', '<leader>ur', ':set relativenumber!<CR>', opts 'Toggle relative numbers')

-- Increment/decrement
map('n', '+', '<C-a>', opts 'Increment number')
map('n', '-', '<C-x>', opts 'Decrement number')

-- Custom mappings
map('n', '<space><space>x', '<cmd>source %<CR>', opts 'Source current file')
map('n', '<space>x', ':.lua<CR>', opts 'Execute Lua command on current line')
map('v', '<space>x', ':lua<CR>', opts 'Execute Lua command on selected lines')
