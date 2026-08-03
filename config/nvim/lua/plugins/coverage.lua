-- Gutter coverage visualization — loads coverage.out produced by neotest-golang
-- After a `make test-unit` or neotest run, coverage glyphs appear automatically.

return {
  'andythigpen/nvim-coverage',
  dependencies = { 'nvim-lua/plenary.nvim' },
  ft = { 'go' },
  keys = {
    { '<leader>gcl', function() require('coverage').load(true) end,  desc = 'Coverage: load & show' },
    { '<leader>gch', function() require('coverage').hide() end,      desc = 'Coverage: hide' },
    { '<leader>gcs', function() require('coverage').summary() end,   desc = 'Coverage: summary' },
    { '<leader>gct', function() require('coverage').toggle() end,    desc = 'Coverage: toggle' },
  },
  config = function()
    require('coverage').setup {
      auto_reload = true,
      auto_reload_timeout_ms = 500,
      lang = {
        go = {
          coverage_file = vim.fn.getcwd() .. '/coverage.out',
        },
      },
      signs = {
        covered   = { hl = 'CoverageCovered',   text = '▎' },
        uncovered = { hl = 'CoverageUncovered',  text = '▎' },
        partial   = { hl = 'CoveragePartial',    text = '▎' },
      },
    }
  end,
}
