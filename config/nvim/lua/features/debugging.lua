-- Debugging feature module - isolated and following SRP
-- Responsible only for debugging functionality (DAP)
-- No dependencies on language-specific modules (dependency rule compliance)

local M = {}

-- Debug-related plugins
M.plugins = {
  {
    'mfussenegger/nvim-dap',
    dependencies = {
      -- Debug UI
      {
        'rcarriga/nvim-dap-ui',
        dependencies = {
          'nvim-neotest/nvim-nio',
        },
      },
      
      -- Virtual text for debugging
      'theHamsta/nvim-dap-virtual-text',
      
      -- Mason integration for debug adapters
      'jay-babu/mason-nvim-dap.nvim',
    },
    config = function()
      -- This will be handled by the feature setup
    end,
  },
}

-- Setup debug UI
M.setup_dap_ui = function()
  local dap = require('dap')
  local dapui = require('dapui')
  
  -- Configure DAP UI
  dapui.setup({
    icons = { expanded = '▾', collapsed = '▸', current_frame = '▸' },
    mappings = {
      expand = { '<CR>', '<2-LeftMouse>' },
      open = 'o',
      remove = 'd',
      edit = 'e',
      repl = 'r',
      toggle = 't',
    },
    element_mappings = {},
    expand_lines = vim.fn.has('nvim-0.7') == 1,
    layouts = {
      {
        elements = {
          { id = 'scopes', size = 0.25 },
          'breakpoints',
          'stacks',
          'watches',
        },
        size = 40,
        position = 'left',
      },
      {
        elements = {
          'repl',
          'console',
        },
        size = 0.25,
        position = 'bottom',
      },
    },
    controls = {
      enabled = true,
      element = 'repl',
      icons = {
        pause = '',
        play = '',
        step_into = '',
        step_over = '',
        step_out = '',
        step_back = '',
        run_last = '↻',
        terminate = '□',
      },
    },
    floating = {
      max_height = nil,
      max_width = nil,
      border = 'single',
      mappings = {
        close = { 'q', '<Esc>' },
      },
    },
    windows = { indent = 1 },
    render = {
      max_type_length = nil,
      max_value_lines = 100,
    },
  })
  
  -- Auto-open/close DAP UI
  dap.listeners.after.event_initialized['dapui_config'] = function()
    dapui.open()
  end
  dap.listeners.before.event_terminated['dapui_config'] = function()
    dapui.close()
  end
  dap.listeners.before.event_exited['dapui_config'] = function()
    dapui.close()
  end
end

-- Setup virtual text for debugging
M.setup_virtual_text = function()
  require('nvim-dap-virtual-text').setup({
    enabled = true,
    enabled_commands = true,
    highlight_changed_variables = true,
    highlight_new_as_changed = false,
    show_stop_reason = true,
    commented = false,
    only_first_definition = true,
    all_references = false,
    clear_on_continue = false,
    display_callback = function(variable, buf, stackframe, node, options)
      if options.virt_text_pos == 'inline' then
        return ' = ' .. variable.value
      else
        return variable.name .. ' = ' .. variable.value
      end
    end,
    virt_text_pos = vim.fn.has('nvim-0.10') == 1 and 'inline' or 'eol',
    all_frames = false,
    virt_lines = false,
    virt_text_win_col = nil,
  })
end

-- Setup debug keymaps
M.setup_keymaps = function()
  local dap = require('dap')
  local dapui = require('dapui')
  
  -- Debug session control
  vim.keymap.set('n', '<F5>', dap.continue, { desc = 'Debug: Start/Continue' })
  vim.keymap.set('n', '<F1>', dap.step_into, { desc = 'Debug: Step Into' })
  vim.keymap.set('n', '<F2>', dap.step_over, { desc = 'Debug: Step Over' })
  vim.keymap.set('n', '<F3>', dap.step_out, { desc = 'Debug: Step Out' })
  vim.keymap.set('n', '<F7>', dapui.toggle, { desc = 'Debug: See last session result' })
  
  -- Breakpoints
  vim.keymap.set('n', '<leader>db', dap.toggle_breakpoint, { desc = 'Debug: Toggle Breakpoint' })
  vim.keymap.set('n', '<leader>dB', function()
    dap.set_breakpoint(vim.fn.input('Breakpoint condition: '))
  end, { desc = 'Debug: Set Conditional Breakpoint' })
  vim.keymap.set('n', '<leader>dlp', function()
    dap.set_breakpoint(nil, nil, vim.fn.input('Log point message: '))
  end, { desc = 'Debug: Set Log Point' })
  
  -- Debug UI
  vim.keymap.set('n', '<leader>du', dapui.toggle, { desc = 'Debug: Toggle UI' })
  vim.keymap.set('n', '<leader>de', dapui.eval, { desc = 'Debug: Evaluate Expression' })
  vim.keymap.set('v', '<leader>de', dapui.eval, { desc = 'Debug: Evaluate Selection' })
  
  -- REPL
  vim.keymap.set('n', '<leader>dr', dap.repl.open, { desc = 'Debug: Open REPL' })
  vim.keymap.set('n', '<leader>dl', dap.run_last, { desc = 'Debug: Run Last' })
  
  -- Session management
  vim.keymap.set('n', '<leader>dt', dap.terminate, { desc = 'Debug: Terminate' })
  vim.keymap.set('n', '<leader>dc', dap.clear_breakpoints, { desc = 'Debug: Clear Breakpoints' })
  
  -- Frames and variables
  vim.keymap.set('n', '<leader>df', dap.focus_frame, { desc = 'Debug: Focus Frame' })
  vim.keymap.set('n', '<leader>dh', function()
    require('dap.ui.widgets').hover()
  end, { desc = 'Debug: Hover Variables' })
  vim.keymap.set('n', '<leader>ds', function()
    local widgets = require('dap.ui.widgets')
    widgets.centered_float(widgets.scopes)
  end, { desc = 'Debug: Scopes' })
end

-- Setup debug signs
M.setup_signs = function()
  local signs = {
    DapBreakpoint = { text = '●', texthl = 'DapBreakpoint', linehl = '', numhl = '' },
    DapBreakpointCondition = { text = '◆', texthl = 'DapBreakpointCondition', linehl = '', numhl = '' },
    DapLogPoint = { text = '◆', texthl = 'DapLogPoint', linehl = '', numhl = '' },
    DapStopped = { text = '▶', texthl = 'DapStopped', linehl = 'DapStoppedLine', numhl = '' },
    DapBreakpointRejected = { text = '○', texthl = 'DapBreakpointRejected', linehl = '', numhl = '' },
  }
  
  for name, sign in pairs(signs) do
    vim.fn.sign_define(name, sign)
  end
  
  -- Highlight groups
  vim.api.nvim_set_hl(0, 'DapBreakpoint', { fg = '#e51400' })
  vim.api.nvim_set_hl(0, 'DapBreakpointCondition', { fg = '#f79000' })
  vim.api.nvim_set_hl(0, 'DapLogPoint', { fg = '#61afef' })
  vim.api.nvim_set_hl(0, 'DapStopped', { fg = '#98c379' })
  vim.api.nvim_set_hl(0, 'DapStoppedLine', { bg = '#2e3440' })
  vim.api.nvim_set_hl(0, 'DapBreakpointRejected', { fg = '#888888' })
end

-- Register debug adapter for a language
M.register_adapter = function(language, adapter_config)
  local dap = require('dap')
  dap.adapters[language] = adapter_config
end

-- Register debug configuration for a language
M.register_configuration = function(language, configurations)
  local dap = require('dap')
  if not dap.configurations[language] then
    dap.configurations[language] = {}
  end
  
  for _, config in ipairs(configurations) do
    table.insert(dap.configurations[language], config)
  end
end

-- Setup Mason DAP integration
M.setup_mason_dap = function()
  require('mason-nvim-dap').setup {
    automatic_installation = true,
    handlers = {},
    ensure_installed = {
      -- Add default debug adapters here
    },
  }
end

-- Setup debugging feature module
M.setup = function()
  -- Setup debug signs and highlighting
  M.setup_signs()
  
  -- Setup debug UI
  M.setup_dap_ui()
  
  -- Setup virtual text
  M.setup_virtual_text()
  
  -- Setup debug keymaps
  M.setup_keymaps()
  
  -- Setup Mason DAP integration
  M.setup_mason_dap()
end

return M