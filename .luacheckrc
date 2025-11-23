-- Luacheck configuration for Neovim dotfiles
std = "luajit"

-- Global variables that are okay to use
globals = {
    "vim",  -- Neovim global API
}

-- Ignore specific warnings
ignore = {
    "212",  -- Unused argument (common in callbacks)
    "213",  -- Unused loop variable (common in config files)
    "631",  -- Line is too long (we prioritize readability)
}

-- Don't report unused function arguments
-- self = false

-- Exclude external dependencies
exclude_files = {
    "config/nvim/lazy-lock.json",
    "**/plugin/**",
    "**/lua/external/**",
}
