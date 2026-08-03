-- Vimfony: Symfony-specific LSP (routes, services, Doctrine, translations)
-- Install: go install github.com/shinyvision/vimfony@latest
--          or download binary from https://github.com/shinyvision/vimfony/releases
-- Only activates when the binary is found in PATH.

local M = {}

M.lsp_config = {
  vimfony = {
    cmd = { 'vimfony' },
    filetypes = { 'php', 'yaml', 'twig', 'xml' },
    root_markers = { 'composer.json', '.git' },
    init_options = {
      -- Path to the Symfony dev container dump (warmup required: bin/console cache:warmup)
      container_xml_path = 'var/cache/dev/App_KernelDevDebugContainer.xml',
      vendor_dir = 'vendor',
    },
  },
}

M.setup = function()
  if vim.fn.executable('vimfony') == 0 then
    -- Binary not installed — skip silently.
    -- Install: go install github.com/shinyvision/vimfony@latest
    return
  end

  local capabilities = vim.lsp.protocol.make_client_capabilities()
  local ok, cmp_nvim_lsp = pcall(require, 'cmp_nvim_lsp')
  if ok then
    capabilities = vim.tbl_deep_extend('force', capabilities, cmp_nvim_lsp.default_capabilities())
  end

  vim.lsp.config('vimfony', vim.tbl_deep_extend('force',
    M.lsp_config.vimfony,
    { capabilities = capabilities }
  ))
  vim.lsp.enable('vimfony')
end

return M
