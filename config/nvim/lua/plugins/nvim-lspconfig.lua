-- LSP configuration is now handled by the modular system
-- See: lua/features/lsp.lua for LSP feature configuration
-- See: lua/lang/go.lua for Go-specific LSP configuration

return {
  -- This file is preserved for any legacy or non-modular plugin configurations
  -- All LSP, completion, and debugging functionality is now in the modular system:
  -- - features/lsp.lua - Core LSP functionality
  -- - features/completion.lua - Autocompletion
  -- - features/debugging.lua - DAP debugging
  -- - lang/go.lua - Go language support
}