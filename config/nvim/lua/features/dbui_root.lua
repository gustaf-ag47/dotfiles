-- Shared DBUI workspace root, independent of the notes vault.
return function()
  return vim.env.DB_UI_ROOT or (vim.env.SYNC or vim.env.HOME .. '/sync') .. '/src/db-ui'
end
