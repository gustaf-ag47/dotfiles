# Complete Keybinding Reference

This document contains ALL keybindings for your development environment across all tools.

## 🪟 Hyprland (Window Manager)

### Basic Window Management
| Keybinding | Action |
|------------|--------|
| `Super + Enter` | Open terminal |
| `Super + Shift + Q` | Kill active window |
| `Super + P` | Toggle floating/pseudo |
| `Super + J` | Toggle split direction |
| `Super + F` | Fullscreen (keep bar) |
| `Super + Shift + F` | Fullscreen (no bar) |

### Application Launchers
| Keybinding | Action |
|------------|--------|
| `Super + Space` | Application launcher (wofi) |
| `Super + R` | File manager |
| `Super + B` | PDF launcher |
| `Super + A` | Screenshot/capture |
| `Super + S` | Screenshot |

### System Controls
| Keybinding | Action |
|------------|--------|
| `Super + Ctrl + Q` | Power menu |
| `Super + Ctrl + Shift + L` | Lock screen |
| `Brightness Up/Down` | Screen brightness |
| `Super + F5` / `Super + Shift + F5` | Keyboard backlight |
| `Volume Up/Down/Mute` | Audio controls |
| `XF86AudioPlay/Pause/Next/Prev` | Media controls |

### **NEW** Productivity Tools
| Keybinding | Action |
|------------|--------|
| `Super + V` | Clipboard manager |
| `Super + Shift + V` | Clipboard history (cliphist) |
| `Super + C` | **Popup calculator (compact)** |
| `Super + Shift + C` | **Terminal calculator (full-featured)** |

### Focus & Movement
| Keybinding | Action |
|------------|--------|
| `Super + h/j/k/l` | Move focus (vim-style) |
| `Super + Ctrl + h/l` | Move window left/right |
| `Super + Ctrl + j/k` | Move workspace between monitors |

### Workspaces
| Keybinding | Action |
|------------|--------|
| `Super + 1-9,0` | Switch to workspace 1-10 |
| `Super + Shift + 1-9,0` | Move window to workspace 1-10 |

---

## 📺 Tmux (Terminal Multiplexer)

**Prefix Key: `Ctrl + Space`**

### Session Management
| Keybinding | Action |
|------------|--------|
| `Ctrl + Space + $` | Rename session |
| `Ctrl + Space + s` | List sessions |
| `Ctrl + Space + d` | Detach from session |

### Window Management
| Keybinding | Action |
|------------|--------|
| `Ctrl + Space + c` | Create new window |
| `Ctrl + Space + &` | Kill window |
| `Ctrl + Space + ,` | Rename window |
| `Ctrl + Space + n` | Next window |
| `Ctrl + Space + p` | Previous window |
| `Ctrl + Space + 1-9` | Switch to window 1-9 |

### Pane Management
| Keybinding | Action |
|------------|--------|
| `Ctrl + Space + %` | Split horizontally |
| `Ctrl + Space + "` | Split vertically |
| `Ctrl + Space + x` | Kill pane |
| `Ctrl + Space + h/j/k/l` | Navigate panes (vim-style) |
| `Ctrl + Space + H/J/K/L` | Resize panes |
| `Ctrl + Space + {` | Swap pane left |
| `Ctrl + Space + }` | Swap pane right |

### Copy Mode (Vi-style)
| Keybinding | Action |
|------------|--------|
| `Ctrl + Space + [` | Enter copy mode |
| `v` | Begin selection |
| `V` | Line selection |
| `y` | Copy selection |
| `Ctrl + Space + ]` | Paste |

---

## ✏️  Neovim (Text Editor)

### Basic Movement
| Keybinding | Action |
|------------|--------|
| `h/j/k/l` | Move left/down/up/right |
| `w/b/e` | Word movement |
| `0/$` | Beginning/end of line |
| `gg/G` | First/last line |
| `Ctrl + u/d` | Page up/down |

### Insert Mode
| Keybinding | Action |
|------------|--------|
| `i/a` | Insert before/after cursor |
| `I/A` | Insert at line start/end |
| `o/O` | New line below/above |
| `Esc` | Return to normal mode |

### File Operations
| Keybinding | Action |
|------------|--------|
| `:w` | Save file |
| `:q` | Quit |
| `:wq` | Save and quit |
| `:q!` | Quit without saving |

### Search & Replace
| Keybinding | Action |
|------------|--------|
| `/pattern` | Search forward |
| `?pattern` | Search backward |
| `n/N` | Next/previous match |
| `:%s/old/new/g` | Replace all |

### Custom Plugin Keybindings (from your config)
| Keybinding | Action |
|------------|--------|
| `Space` | Leader key |
| `Space + e` | File explorer (Neo-tree) |
| `Space + ff` | Find files (Telescope) |
| `Space + fg` | Live grep (Telescope) |
| `Space + fb` | Find buffers (Telescope) |
| `gd` | Go to definition (LSP) |
| `gr` | Go to references (LSP) |
| `K` | Hover documentation (LSP) |

---

## 🐚 Zsh (Shell)

### Command Line Editing (Vi-mode)
| Keybinding | Action |
|------------|--------|
| `Esc` | Enter normal mode |
| `i/a` | Insert mode |
| `0/$` | Beginning/end of line |
| `w/b` | Word movement |
| `dd` | Delete line |
| `v` | Edit in nvim |

### History & Completion
| Keybinding | Action |
|------------|--------|
| `Ctrl + R` | Reverse history search |
| `Up/Down` | History navigation |
| `Tab` | Completion |
| `Ctrl + Space` | Accept autosuggestion |

### **NEW** FZF Power Functions
| Command | Action |
|---------|--------|
| `fkill` | Kill processes with fuzzy search |
| `fdocker` | Docker container interaction |
| `fglog` | Interactive git log browser |
| `fgco` | Fuzzy git branch checkout |
| `fgbr` | Recent git branch switcher |
| `calc "expression"` | Quick calculations |

---

## 🔍 FZF (Fuzzy Finder)

### In Command Line
| Keybinding | Action |
|------------|--------|
| `Ctrl + T` | Find files |
| `Ctrl + R` | Search history |
| `Alt + C` | Change directory |

### In FZF Interface
| Keybinding | Action |
|------------|--------|
| `Ctrl + J/K` | Navigate up/down |
| `Ctrl + N/P` | Navigate up/down (alt) |
| `Tab` | Select multiple |
| `Ctrl + A` | Select all |
| `Ctrl + D` | Deselect all |
| `Enter` | Confirm selection |
| `Esc` | Cancel |

---

## 📁 lf (File Manager)

### Navigation
| Keybinding | Action |
|------------|--------|
| `h/j/k/l` | Navigate (vim-style) |
| `gg/G` | First/last item |
| `Enter` | Open file/enter directory |
| `Backspace` | Go to parent directory |

### File Operations
| Keybinding | Action |
|------------|--------|
| `y` | Copy (yank) |
| `d` | Cut (delete) |
| `p` | Paste |
| `c` | Create file |
| `mkdir` | Create directory |
| `r` | Rename |
| `Delete` | Delete file |

### Marks & Search
| Keybinding | Action |
|------------|--------|
| `m + letter` | Set mark |
| `' + letter` | Go to mark |
| `/` | Search |
| `n/N` | Next/previous search |

---

## 🌐 Git (Custom Functions)

### Custom Git Functions
| Function | Action |
|----------|--------|
| `g` | Amend commit and force push |
| `r` | Rebase current branch to master |
| `fglog` | Interactive git log with preview |
| `fgco` | Fuzzy checkout branch |
| `fgbr` | Switch to recent branch |

### Standard Git (with delta diff)
| Command | Action |
|---------|--------|
| `git log` | Enhanced log with delta |
| `git diff` | Side-by-side diff with delta |
| `git show` | Enhanced commit view |

---

## 🧮 Calculator (NEW)

### Calculator Options
| Keybinding | Type | Description |
|------------|------|-------------|
| `Super + C` | **Popup Calculator** | Compact wofi interface with history |
| `Super + Shift + C` | **Terminal Calculator** | Full-featured Python calculator |

### Popup Calculator (Super + C)
- Compact 400x500px interface
- Calculation history (last 5 results)
- Quick example buttons
- Auto-copy results to clipboard
- Type expressions directly or click examples

### Terminal Calculator (Super + Shift + C) 
- Full Python math environment
- Interactive terminal interface (600x400px)
- Command history with arrow keys
- Advanced functions available
- Auto-copy results to clipboard

### Supported Functions (Both)
```bash
# Basic arithmetic
2 + 3 * 4          # → 14
(10 + 5) * 2       # → 30

# Advanced math (Terminal calculator)
sqrt(16)           # → 4.0
sin(pi/2)          # → 1.0
log(e)             # → 1.0
2**8               # → 256
cos(pi)            # → -1.0

# Constants
pi                 # → 3.14159...
e                  # → 2.71828...

# Commands
help()             # Show help (terminal only)
q or quit()        # Exit calculator
c or clear()       # Clear screen/history
```

---

## 📋 Clipboard Management (NEW)

### Clipboard Tools
| Keybinding | Action |
|------------|--------|
| `Super + V` | Original clipboard manager |
| `Super + Shift + V` | **Clipboard history (cliphist)** |

---

## ⚡ Modern CLI Tools (NEW)

### Better Commands
| Old Command | New Command | Description |
|-------------|-------------|-------------|
| `ls` | `eza` | Better file listing |
| `ps` | `procs` | Better process viewer |
| `du` | `dust` | Better disk usage |
| `df` | `duf` | Better filesystem info |
| `ping` | `gping` | Visual ping |
| `htop` | `bottom` | Better system monitor |

### Git Enhancements
| Tool | Description |
|------|-------------|
| `delta` | Enhanced git diffs (replaces diff-so-fancy) |
| `starship` | Modern shell prompt with git info |

---

## 🚀 Quick Reference Card

### Most Used Combos
```bash
# Terminal workflow
Super + Enter           # New terminal
Ctrl + Space + c        # New tmux window
Space + ff              # Find files in nvim
fkill                   # Kill process
Super + C               # Quick calculation

# Window management  
Super + Space           # Launch app
Super + h/j/k/l         # Focus windows
Super + 1-9             # Switch workspace
Super + Shift + Q       # Kill window

# Git workflow
fglog                   # Browse git history
fgco                    # Checkout branch
g                       # Amend & push
r                       # Rebase to master
```

---

## 📝 Notes

- **Prefix Keys**: Tmux uses `Ctrl + Space`, Nvim uses `Space`
- **Vi-mode**: Available in tmux copy mode, zsh command line, and nvim
- **FZF Integration**: Available throughout the system for fuzzy finding
- **Clipboard**: All tools copy to system clipboard automatically
- **Modern Tools**: All CLI commands have been upgraded for better UX

This reference covers your complete mouseless development environment!