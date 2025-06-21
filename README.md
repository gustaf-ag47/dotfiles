# 🚀 Dotfiles - Development Environment

A clean and efficient development environment optimized for productivity on Arch Linux with Hyprland (Wayland) and i3 (X11) support.

## ✨ Features

- **Hyprland** (Wayland) with Tokyo Night theme
- **i3** (X11) fallback support  
- **Zsh** with modern CLI tools
- **Neovim** with comprehensive plugin setup
- **Tmux** with vim-style keybindings
- **Modern CLI tools** integration

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <your-repo-url> ~/.dotfiles
cd ~/.dotfiles

# Run the installation script
make install
```

### Post-Installation

1. **Set Zsh as default shell:**
   ```bash
   chsh -s $(which zsh)
   ```

2. **Install modern CLI tools:**
   ```bash
   # Arch Linux
   sudo pacman -S bat eza fd ripgrep dust duf procs
   
   # The aliases will automatically activate when tools are installed
   ```

## 🔧 Modern CLI Tools

Enhanced aliases that activate when tools are installed:

- `bat` → better `cat` with syntax highlighting
- `eza` → better `ls` with colors and icons  
- `fd` → better `find`
- `dust` → better `du`
- `duf` → better `df`
- `procs` → better `ps`
- `ripgrep` → better `grep`

## 📋 Key Features

### Shell Enhancements
- Modern CLI tool aliases (conditional loading)
- Vim-style command line editing
- Enhanced completion and autosuggestions
- Git integration and shortcuts

### Editor Configuration
- Neovim with LSP support
- 25+ plugins for development
- Language support for Python, JavaScript, Rust, Go, etc.
- Custom keybindings and snippets

### Window Management
- Hyprland with Tokyo Night theme
- Vim-style navigation keybindings
- Workspace organization
- Custom window rules

## 🛠️ Customization

All configurations are organized in the `config/` directory:
- `config/zsh/` - Shell configuration
- `config/nvim/` - Editor configuration  
- `config/gui/` - Desktop environment configs
- `config/tmux/` - Terminal multiplexer

## 📖 Documentation

- Complete keybinding reference: [KEYBINDINGS.md](KEYBINDINGS.md)
- Installation troubleshooting in individual config directories

---

**🚀 A clean, efficient development environment that grows with your needs!**