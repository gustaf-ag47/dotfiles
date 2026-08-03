local function augroup(name)
  return vim.api.nvim_create_augroup(name, { clear = true })
end

-- Private per-project config loader.
-- Looks for $NOTES/nvim-projects/<cwd-basename>.lua and sources it silently.
-- $NOTES is already private/synced — no need for .nvim.lua files in project dirs.
-- This runs AFTER LazyDone so plugins are available inside project configs.
vim.api.nvim_create_autocmd('User', {
  pattern = 'LazyDone',
  once = true,
  group = augroup 'project-config',
  callback = function()
    local notes = os.getenv('NOTES') or (os.getenv('HOME') .. '/sync/Vault')
    local name = vim.fn.fnamemodify(vim.fn.getcwd(), ':t')
    local config = notes .. '/nvim-projects/' .. name .. '.lua'
    if vim.fn.filereadable(config) == 1 then
      local ok, err = pcall(dofile, config)
      if not ok then
        -- vim.schedule so the error notification lands AFTER UI is ready;
        -- raw vim.notify during LazyDone’s cmdline-mode tick forces a
        -- “Press ENTER” prompt.
        vim.schedule(function()
          vim.notify('nvim-projects/' .. name .. '.lua: ' .. err, vim.log.levels.ERROR, { title = 'project config' })
        end)
      end
    end
  end,
})

-- Highlight on yank
vim.api.nvim_create_autocmd('TextYankPost', {
  desc = 'Highlight when yanking (copying) text',
  group = augroup 'highlight-yank',
  callback = function()
    vim.hl.on_yank()
  end,
})

-- Auto-save
vim.api.nvim_create_autocmd({ 'InsertLeave', 'TextChanged' }, {
  pattern = '*',
  command = 'silent! update',
  desc = 'Auto-save on insert leave or text change',
})

vim.api.nvim_create_autocmd('FocusLost', {
  pattern = '*',
  command = 'silent! wa',
  desc = 'Save all files when Neovim loses focus',
})

vim.api.nvim_create_autocmd('BufWritePost', {
  pattern = '*',
  command = 'echohl ModeMsg | echo "File saved!" | echohl None',
  desc = 'Show feedback when saving a file',
})

-- Go to last position when reopening file
vim.api.nvim_create_autocmd('BufReadPost', {
  group = augroup 'last-position',
  callback = function(event)
    local exclude = { 'gitcommit' }
    local buf = event.buf
    if vim.tbl_contains(exclude, vim.bo[buf].filetype) or vim.b[buf].last_loc then
      return
    end
    vim.b[buf].last_loc = true
    local mark = vim.api.nvim_buf_get_mark(buf, '"')
    local lcount = vim.api.nvim_buf_line_count(buf)
    if mark[1] > 0 and mark[1] <= lcount then
      pcall(vim.api.nvim_win_set_cursor, 0, mark)
    end
  end,
})

-- Resize splits when terminal resizes
vim.api.nvim_create_autocmd('VimResized', {
  group = augroup 'resize-splits',
  callback = function()
    local current_tab = vim.fn.tabpagenr()
    vim.cmd('tabdo wincmd =')
    vim.cmd('tabnext ' .. current_tab)
  end,
})

-- Close help/qf/man with q
vim.api.nvim_create_autocmd('FileType', {
  group = augroup 'close-with-q',
  pattern = {
    'help',
    'qf',
    'man',
    'notify',
    'lspinfo',
    'spectre_panel',
    'startuptime',
    'checkhealth',
  },
  callback = function(event)
    vim.bo[event.buf].buflisted = false
    vim.keymap.set('n', 'q', '<cmd>close<cr>', { buffer = event.buf, silent = true })
  end,
})

-- Terminal: enter insert mode immediately, no line numbers
vim.api.nvim_create_autocmd('TermOpen', {
  group = augroup 'terminal-open',
  callback = function()
    vim.opt_local.number = false
    vim.opt_local.relativenumber = false
    vim.opt_local.signcolumn = 'no'
    vim.cmd('startinsert')
  end,
})

-- Check for external file changes on focus
vim.api.nvim_create_autocmd({ 'FocusGained', 'TermClose', 'TermLeave' }, {
  group = augroup 'checktime',
  callback = function()
    if vim.o.buftype ~= 'nofile' then
      vim.cmd('checktime')
    end
  end,
})
