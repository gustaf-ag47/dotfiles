# Neovim Keybinding Scanner

Automatically scans your Neovim configuration and generates comprehensive keybinding documentation.

## Features

✅ **Modular Configuration Support** - Works with your clean architecture  
✅ **Multiple Output Formats** - Markdown and JSON  
✅ **Language-Specific Grouping** - Separates Go, Python, SQL keybindings  
✅ **Conflict Detection** - Identifies potential keymap conflicts  
✅ **Cross-Platform** - Works on Linux, macOS, Windows  
✅ **Both Lua and Python Versions** - Use inside Neovim or standalone  

## Quick Start

### Python Script (Standalone)

```bash
# Basic usage
python3 scripts/scan_keybindings.py

# Scan specific config
python3 scripts/scan_keybindings.py ~/.config/nvim

# Generate markdown file
python3 scripts/scan_keybindings.py --format markdown --output keybindings.md

# Generate JSON for processing
python3 scripts/scan_keybindings.py --format json --output keybindings.json

# Verbose output
python3 scripts/scan_keybindings.py --verbose
```

### Inside Neovim

```vim
" Scan and show in buffer
:KeymapScan

" Show JSON format
:KeymapScan json

" Save to file
:KeymapScanToFile markdown keybindings.md
:KeymapScanToFile json keybindings.json
```

## Sample Output

### Summary
```
Found 230 keybindings:
  features: 66 keybindings
  lang:python: 22 keybindings  
  lang:go: 42 keybindings
  lang:sql: 26 keybindings
  plugins: 66 keybindings
  utils: 8 keybindings
```

### Markdown Documentation
```markdown
# Neovim Keybinding Reference

## Global Keybindings
| Mode | Key | Command | Description | Module |
|------|-----|---------|-------------|--------|
| `n` | `<leader>ff` | `<cmd>Telescope find_files<cr>` | Find files | features |

## GO Keybindings  
| Mode | Key | Command | Description |
|------|-----|---------|-------------|
| `n` | `<leader>gr` | `<cmd>GoRun<cr>` | Go run |
| `n` | `<leader>gb` | `<cmd>GoBuild<cr>` | Go build |

## PYTHON Keybindings
| Mode | Key | Command | Description |
|------|-----|---------|-------------|
| `n` | `<leader>pr` | `<cmd>!python %<cr>` | Run Python file |
| `n` | `<leader>pv` | `<cmd>VenvSelect<cr>` | Select Python venv |
```

## What It Detects

The scanner recognizes various keybinding patterns:

```lua
-- Standard vim.keymap.set with description
vim.keymap.set('n', '<leader>ff', '<cmd>Telescope find_files<cr>', { desc = 'Find files' })

-- Local map function calls  
map('n', '<leader>gb', '<cmd>GoBuild<cr>', { desc = 'Go build' })

-- Simple keymaps without descriptions
vim.keymap.set('n', '<C-h>', '<C-w>h')

-- Function-based keymaps
vim.keymap.set('n', '<leader>pr', function()
  vim.cmd('!python ' .. vim.fn.expand('%'))
end, { desc = 'Run Python file' })
```

## Integration with Your Architecture

The scanner respects your modular architecture:

```
lua/
├── core/           → Global keybindings
├── features/       → Feature-specific keybindings  
├── lang/
│   ├── go.lua     → Go keybindings (isolated)
│   ├── python.lua → Python keybindings (isolated)
│   └── sql.lua    → SQL keybindings (isolated)
└── plugins/        → Plugin keybindings
```

Each module's keybindings are:
- ✅ **Properly Categorized** - By language/feature
- ✅ **Context-Aware** - Buffer-local vs global
- ✅ **Conflict-Free** - Language isolation prevents conflicts

## Advanced Usage

### JSON Output for Processing
```bash
# Generate JSON and process with jq
python3 scripts/scan_keybindings.py --format json | jq '.summary'

# Extract only Go keybindings
python3 scripts/scan_keybindings.py --format json | jq '.grouped.by_module["lang:go"]'

# Find all leader key mappings
python3 scripts/scan_keybindings.py --format json | jq '.grouped.by_leader'
```

### Automation
```bash
# Add to your dotfiles update script
python3 scripts/scan_keybindings.py --output docs/keybindings.md

# Generate for multiple configs
for config in ~/.config/nvim ~/.config/lvim; do
  python3 scripts/scan_keybindings.py "$config" --output "${config}/keybindings.md"
done
```

## Benefits for Your Modular Setup

1. **Documentation**: Auto-generated docs stay in sync with code
2. **Onboarding**: New team members can quickly see all keybindings  
3. **Conflict Detection**: Prevents accidental keymap conflicts
4. **Reference**: Quick lookup of language-specific shortcuts
5. **Maintenance**: Easy to see which modules define what keys

## Requirements

- **Python Version**: Python 3.6+
- **Neovim Version**: 0.7+ (for Lua version)
- **Dependencies**: None (uses only standard library)

## Output Formats

### Markdown
- ✅ Human-readable documentation
- ✅ GitHub/GitLab compatible
- ✅ Great for wikis and README files

### JSON  
- ✅ Machine-readable for processing
- ✅ Integration with other tools
- ✅ API-friendly format

The scanner perfectly complements your modular architecture by providing visibility into the isolated keybinding system without breaking the clean separation of concerns! 🚀