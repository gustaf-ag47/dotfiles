# 🚀 Dotfiles - Complete Development Environment

A comprehensive, mouseless development environment optimized for productivity on Arch Linux with Hyprland (Wayland) and i3 (X11) support.

![Tokyo Night Theme](https://img.shields.io/badge/Theme-Tokyo%20Night-blueviolet?style=for-the-badge)
![Arch Linux](https://img.shields.io/badge/OS-Arch%20Linux-1793d1?style=for-the-badge&logo=arch-linux)
![Hyprland](https://img.shields.io/badge/WM-Hyprland-58a6ff?style=for-the-badge)

## ✨ Features

### 🪟 **Window Management**
- **Hyprland** (Wayland) with custom Tokyo Night theme
- **i3** (X11) fallback support
- Workspace-based application organization
- Vim-style navigation keybindings
- Floating window rules for calculators, system tools

### 🐚 **Shell & Terminal**
- **Zsh** with vi-mode and custom prompt
- **Starship** prompt with git integration and battery status
- **Modern CLI tools**: `bat`, `eza`, `fd`, `ripgrep`, `dust`, `duf`, `procs`
- **Tmux** with vim-style keybindings
- **Alacritty** terminal with Tokyo Night theme

### ✏️ **Editor**
- **Neovim** with LSP, completion, and 25+ plugins
- **LazyVim**-based configuration
- Language support: Python, JavaScript, Rust, Go, PHP, Java, Kotlin
- Database tools, HTTP client, and debugging support
- Custom snippets and keybindings

### 🎨 **UI & Theme**
- **Tokyo Night** color scheme across all applications
- **Waybar** status bar with custom modules
- **Wofi** (Wayland) and **Rofi** (X11) application launchers
- **Dunst** notifications with custom styling
- Custom wallpapers and GTK themes

### 🛠️ **Development Tools**
- **Git** with delta diffs and custom aliases
- **Docker** and **Kubernetes** support
- **FZF** integration for fuzzy finding
- **lf** file manager with preview
- Database clients: **mycli**, **pgcli**
- **Bluetooth** management with automatic backups

### 🧮 **Productivity**
- **Popup Calculator** (`Super+C`) - Quick calculations with history
- **Terminal Calculator** (`Super+Shift+C`) - Full-featured Python calculator
- **Clipboard Manager** with history (`Super+V`)
- **Screenshot tools** with annotation support
- **Power management** with battery monitoring

## 🚀 Quick Start

### Prerequisites

```bash
# Essential packages (Arch Linux)
sudo pacman -S base-devel git zsh tmux neovim alacritty
sudo pacman -S hyprland waybar wofi dunst wl-clipboard
sudo pacman -S starship fzf ripgrep fd bat eza dust duf procs

# AUR packages
yay -S bluetooth-manager bluetoothctl-git
```

### Installation

```bash
# Clone the repository
git clone <your-repo-url> ~/.dotfiles
cd ~/.dotfiles

# Run the installation script
make install

# Or manually:
./scripts/install.sh
```

### Post-Installation

1. **Set Zsh as default shell:**
   ```bash
   chsh -s $(which zsh)
   ```

2. **Install Tmux plugins:**
   ```bash
   # Start tmux and press Ctrl+Space + I
   tmux
   # Press Ctrl+Space + I to install plugins
   ```

3. **Configure Git:**
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```

## 📋 Key Bindings

### 🪟 **Hyprland (Window Manager)**
| Keybinding | Action |
|------------|--------|
| `Super + Enter` | Open terminal |
| `Super + Space` | Application launcher |
| `Super + C` | **Popup calculator** |
| `Super + V` | Clipboard manager |
| `Super + h/j/k/l` | Focus windows (vim-style) |
| `Super + 1-9` | Switch workspaces |
| `Super + Shift + Q` | Kill window |
| `Super + F` | Toggle fullscreen |

### 📺 **Tmux (Prefix: Ctrl+Space)**
| Keybinding | Action |
|------------|--------|
| `Ctrl+Space + c` | New window |
| `Ctrl+Space + %` | Split horizontal |
| `Ctrl+Space + "` | Split vertical |
| `Ctrl+Space + h/j/k/l` | Navigate panes |

### ✏️ **Neovim (Leader: Space)**
| Keybinding | Action |
|------------|--------|
| `Space + e` | File explorer |
| `Space + ff` | Find files |
| `Space + fg` | Live grep |
| `Space + fb` | Find buffers |

*See [KEYBINDINGS.md](KEYBINDINGS.md) for complete reference.*

## 🗂️ **Directory Structure**

```
dotfiles/
├── bin/                    # Custom scripts and utilities
│   ├── calculator/         # Calculator implementations
│   ├── bluetooth-*         # Bluetooth management tools
│   ├── dev-*              # Development workflow tools
│   └── ...
├── config/
│   ├── gui/
│   │   ├── Wayland/       # Hyprland, Waybar, Wofi
│   │   └── Xorg/          # i3, Polybar, Rofi
│   ├── nvim/              # Neovim configuration
│   ├── zsh/               # Zsh configuration and plugins
│   ├── tmux/              # Tmux configuration
│   └── ...
├── scripts/               # Installation and maintenance scripts
├── KEYBINDINGS.md         # Complete keybinding reference
└── README.md             # This file
```

## 🧮 **Calculator Features**

### Popup Calculator (`Super + C`)
- Compact 400x500px interface
- Calculation history (last 5 results)
- Auto-copy results to clipboard
- Quick example buttons for common operations

### Terminal Calculator (`Super + Shift + C`)
- Full Python math environment
- Interactive terminal interface
- Advanced functions: `sqrt()`, `sin()`, `cos()`, `log()`
- Constants: `pi`, `e`
- Command history with readline
- Answer continuation: `* 2` operates on last result

## 🔧 **Customization**

### Theme Colors (Tokyo Night)
```bash
# Primary colors used throughout
Background: #1a1b26
Foreground: #c0caf5
Blue: #7aa2f7
Green: #9ece6a
Yellow: #e0af68
Red: #f7768e
Purple: #bb9af7
Cyan: #7dcfff
```

### Adding New Applications
1. **Desktop entries**: Add to `config/applications/`
2. **Window rules**: Update `config/gui/Wayland/hypr/windowrule.conf`
3. **Keybindings**: Add to `config/gui/Wayland/hypr/keymap.conf`

### Custom Scripts
Place executable scripts in `bin/` directory. They'll be automatically available in PATH.

## 🛠️ **Development Workflow**

### Git Workflow (Custom Functions)
```bash
g        # Amend commit and force push
r        # Rebase current branch to master
fglog    # Interactive git log with preview
fgco     # Fuzzy checkout branch
fgbr     # Switch to recent branch
```

### Docker & Kubernetes
```bash
fdocker  # Interactive Docker container management
kubectl  # With custom aliases and completion
kubectx  # Context switching
kubens   # Namespace switching
```

### Database Tools
- **mycli**: MySQL client with autocompletion
- **pgcli**: PostgreSQL client with autocompletion
- **Neovim dadbod**: Database queries in editor

## 📊 **System Monitoring**

### Battery Management
- Battery status in Waybar
- Low battery notifications
- Power mode switching
- Automatic power profile switching

### Bluetooth Management
- Automatic device backups
- Connection logging
- Profile switching
- Backup rotation (keeps 3 most recent)

## 🔍 **Troubleshooting**

### Common Issues

**Hyprland not starting:**
```bash
# Check logs
journalctl -u display-manager
# Or
cat /var/log/Xorg.0.log
```

**Zsh plugins not loading:**
```bash
# Reinstall plugins
rm -rf ~/.config/zsh/plugins
make install
```

**Tmux plugins not working:**
```bash
# Reinstall TPM
rm -rf ~/.local/share/tmux/plugins
git clone https://github.com/tmux-plugins/tpm ~/.local/share/tmux/plugins/tpm
# Then: Ctrl+Space + I
```

### Getting Help
- 📖 Read the complete [KEYBINDINGS.md](KEYBINDINGS.md)
- 🐛 Check existing issues
- 💬 Open a new issue with logs and configuration

## 🎯 **Performance**

### Optimizations Included
- Lazy loading of heavy tools (pyenv, fzf)
- Bluetooth backup rotation
- Tmux session persistence
- Neovim lazy plugin loading
- Modern CLI tools for speed

### Benchmarks
- **Zsh startup**: ~50ms (with all plugins)
- **Neovim startup**: ~100ms (with 25+ plugins)
- **Tmux new session**: ~20ms

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Code Style
- Use consistent indentation (2 spaces)
- Add comments for complex logic
- Follow existing naming conventions
- Test all keybindings work

## 📜 **License**

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- [Tokyo Night theme](https://github.com/folke/tokyonight.nvim)
- [Hyprland community](https://hyprland.org)
- [Neovim community](https://neovim.io)
- All the amazing open-source projects that make this possible

---

**🚀 Happy coding with a completely mouseless workflow!**