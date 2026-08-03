-- HTTP client with JetBrains/VS Code-compatible .http file support
-- Environments defined in http-client.env.json at project root.
-- Secrets in http-client.private.env.json (gitignored).

return {
  'mistweaverco/kulala.nvim',
  ft = { 'http', 'rest' },
  keys = {
    -- Trigger lazy-load on leader+R in http buffers
    { '<leader>R', ft = 'http', desc = '+HTTP' },
  },
  opts = {
    split_direction = 'vertical',
    default_view = 'body',
    default_env = 'local',
    global_keymaps = false,
    ui = {
      show_variable_info_text = 'float',
    },
  },
  config = function(_, opts)
    local k = require 'kulala'
    k.setup(opts)

    -- Auto-install kulala-core binary if missing (required since v5 breaking change)
    local backend = require 'kulala.backend'
    if vim.fn.executable(backend.get_bin_path()) ~= 1 then
      vim.notify('kulala: installing kulala-core...', vim.log.levels.INFO)
      backend.install 'latest'
    end

    -- Register buffer-local keymaps for http/rest files
    vim.api.nvim_create_autocmd('FileType', {
      pattern = { 'http', 'rest' },
      callback = function(ev)
        local map = function(lhs, rhs, desc)
          vim.keymap.set('n', lhs, rhs, { buffer = ev.buf, silent = true, desc = desc })
        end
        map('<leader>Rr', k.run, 'HTTP: Send request')
        map('<leader>Ra', k.run_all, 'HTTP: Send all')
        map('<leader>Rb', k.scratchpad, 'HTTP: Scratchpad')
        map('<leader>Re', k.set_selected_env, 'HTTP: Select env')
        map('<leader>Ri', k.inspect, 'HTTP: Inspect')
        map('<leader>Rc', k.copy, 'HTTP: Copy as cURL')
        map('<leader>Rn', k.jump_next, 'HTTP: Next request')
        map('<leader>Rp', k.jump_prev, 'HTTP: Prev request')
        map('<leader>Rq', k.close, 'HTTP: Close response')
        map('<leader>Rl', k.replay, 'HTTP: Replay last')
        map('<leader>Rf', k.search, 'HTTP: Find request')
        map('<leader>Ru', k.manage_auth, 'HTTP: Manage auth')

        local wk_ok, wk = pcall(require, 'which-key')
        if wk_ok then
          wk.add { { '<leader>R', group = 'HTTP', icon = '', buffer = ev.buf } }
        end
      end,
    })
  end,
}
