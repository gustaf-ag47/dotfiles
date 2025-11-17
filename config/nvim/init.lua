local g = vim.g
g.mapleader = ' '
g.maplocalleader = ' '
g.have_nerd_font = true

-- Early filetype detection for .env files to prevent shell linting
vim.filetype.add {
  filename = {
    ['.env'] = 'dotenv',
    ['.env.local'] = 'dotenv',
    ['.env.development'] = 'dotenv',
    ['.env.production'] = 'dotenv',
    ['.env.staging'] = 'dotenv',
    ['.env.test'] = 'dotenv',
  },
  pattern = {
    ['%.env%..*'] = 'dotenv',
  },
}

require 'core'
