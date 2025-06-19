# 🏗️ Dotfiles Modular Architecture

This document outlines the modular organization strategy for maximum portability, maintainability, and flexibility.

## 🎯 Design Principles

1. **Separation of Concerns**: Platform, desktop environment, and application configs are separate
2. **Conditional Loading**: Modules load only when their dependencies are available
3. **Override System**: More specific configurations override general ones
4. **Minimal Core**: Core functionality works everywhere, modules add features
5. **Easy Testing**: Each module can be enabled/disabled independently

## 📁 Directory Structure

```
dotfiles/
├── core/                          # Universal configurations (works everywhere)
│   ├── shell/                     # Shell configs (bash, zsh)
│   ├── editor/                    # Editor configs (vim, nvim)
│   ├── git/                       # Git configuration
│   ├── tmux/                      # Terminal multiplexer
│   └── scripts/                   # Universal utility scripts
│
├── platforms/                     # OS-specific configurations
│   ├── arch/                      # Arch Linux specific
│   │   ├── packages.txt           # Package lists
│   │   ├── aur.txt               # AUR packages
│   │   ├── services.txt          # Systemd services
│   │   └── config/               # Arch-specific configs
│   ├── ubuntu/                    # Ubuntu/Debian specific
│   ├── macos/                     # macOS specific
│   └── common-linux/              # Common Linux configs
│
├── desktop/                       # Desktop environment configurations
│   ├── wayland/                   # Wayland-specific
│   │   ├── hyprland/             # Hyprland window manager
│   │   ├── sway/                 # Sway window manager
│   │   ├── waybar/               # Wayland status bar
│   │   ├── wofi/                 # Wayland app launcher
│   │   └── common/               # Common Wayland configs
│   ├── x11/                       # X11-specific
│   │   ├── i3/                   # i3 window manager
│   │   ├── polybar/              # X11 status bar
│   │   ├── rofi/                 # X11 app launcher
│   │   └── common/               # Common X11 configs
│   └── terminal/                  # Terminal-only environments
│
├── applications/                  # Application-specific configurations
│   ├── browsers/                  # Browser configurations
│   │   ├── firefox/
│   │   ├── chromium/
│   │   └── common/
│   ├── development/               # Development tools
│   │   ├── languages/            # Language-specific configs
│   │   │   ├── python/
│   │   │   ├── javascript/
│   │   │   ├── rust/
│   │   │   └── go/
│   │   ├── databases/            # Database tools
│   │   ├── containers/           # Docker, K8s configs
│   │   └── cloud/                # Cloud provider configs
│   ├── productivity/             # Productivity applications
│   │   ├── obsidian/
│   │   ├── notion/
│   │   └── calendar/
│   └── media/                     # Media applications
│       ├── mpv/
│       ├── spotify/
│       └── image-viewers/
│
├── modules/                       # Feature modules (can be mixed and matched)
│   ├── bluetooth/                 # Bluetooth management
│   ├── power-management/          # Power/battery management
│   ├── networking/                # Network configurations
│   ├── security/                  # Security tools and configs
│   ├── backup/                    # Backup configurations
│   ├── monitoring/                # System monitoring
│   └── automation/                # Automation scripts
│
├── themes/                        # Visual themes
│   ├── tokyo-night/              # Tokyo Night theme
│   ├── catppuccin/               # Catppuccin theme
│   ├── nord/                     # Nord theme
│   └── gruvbox/                  # Gruvbox theme
│
├── profiles/                      # Pre-configured combinations
│   ├── developer-arch-hyprland/   # Full dev setup
│   ├── minimal-server/            # Minimal server setup
│   ├── designer-macos/            # Design-focused setup
│   └── gaming-arch/               # Gaming-optimized setup
│
├── install/                       # Installation and management scripts
│   ├── detect.sh                 # System detection
│   ├── install.sh                # Main installer
│   ├── modules/                  # Per-module installers
│   └── profiles/                 # Profile installers
│
└── docs/                         # Documentation
    ├── modules/                  # Module documentation
    ├── platforms/                # Platform-specific docs
    └── guides/                   # Setup guides
```

## 🔍 Module Detection System

Each module includes a `detect.sh` script that determines if it should be loaded:

```bash
# Example: desktop/wayland/detect.sh
#!/bin/bash
# Check if Wayland is available
[ -n "$WAYLAND_DISPLAY" ] || [ -n "$XDG_SESSION_TYPE" ] && [ "$XDG_SESSION_TYPE" = "wayland" ]
```

## 📦 Module Structure

Each module follows this standard structure:

```
module-name/
├── detect.sh                     # Detection logic
├── install.sh                    # Installation script
├── config/                       # Configuration files
├── scripts/                      # Module-specific scripts
├── packages.txt                  # Required packages
├── README.md                     # Module documentation
└── override/                     # Override configs for specific scenarios
    ├── arch/
    ├── ubuntu/
    └── minimal/
```

## 🎮 Loading Priority

Configurations are loaded in this order (later overrides earlier):

1. **Core** - Universal base configuration
2. **Platform** - OS-specific configurations
3. **Desktop** - Desktop environment configurations  
4. **Applications** - Application-specific configurations
5. **Modules** - Feature modules
6. **Theme** - Visual theme
7. **Profile** - Profile-specific overrides
8. **Local** - User-specific local overrides

## 🔧 Configuration Examples

### Core Shell Configuration
```bash
# core/shell/zsh/zshrc
# Universal zsh configuration that works everywhere
export EDITOR="vi"  # Fallback editor
export HISTSIZE=1000

# Load platform-specific configurations
for config in "$DOTFILES/platforms/$(detect_platform)/shell"/*.zsh; do
    [ -f "$config" ] && source "$config"
done
```

### Platform-Specific Package Management
```bash
# platforms/arch/install.sh
#!/bin/bash
pacman -S --needed $(cat packages.txt)
yay -S --needed $(cat aur.txt)
```

### Desktop Environment Detection
```bash
# install/detect.sh
detect_desktop() {
    if [ -n "$WAYLAND_DISPLAY" ]; then
        echo "wayland"
    elif [ -n "$DISPLAY" ]; then
        echo "x11"
    else
        echo "terminal"
    fi
}
```

## 🚀 Installation Workflows

### Quick Start (Automatic Detection)
```bash
curl -sSL dotfiles.example.com/install | bash
# Automatically detects system and installs appropriate modules
```

### Custom Installation
```bash
./install/install.sh \
  --platform=arch \
  --desktop=wayland/hyprland \
  --modules=bluetooth,power-management \
  --theme=tokyo-night \
  --profile=developer
```

### Module Management
```bash
# Install specific module
./install/modules/bluetooth/install.sh

# Enable/disable modules
dotfiles module enable bluetooth
dotfiles module disable power-management

# List available modules
dotfiles module list
```

## 🎯 Benefits

### For Maintainers
- **Easy Testing**: Test individual modules in isolation
- **Clear Dependencies**: Each module declares its requirements
- **Modular Updates**: Update one component without affecting others
- **Platform Support**: Easy to add new platforms/desktop environments

### For Users
- **Selective Installation**: Only install what you need
- **Easy Customization**: Override specific modules without forking
- **Quick Setup**: Pre-configured profiles for common scenarios
- **Portable**: Move between different systems easily

### For Contributors
- **Clear Structure**: Know exactly where to add new features
- **Isolated Changes**: Changes don't affect unrelated modules
- **Easy Testing**: Test modules on different platforms
- **Documentation**: Each module is self-documenting

## 🔄 Migration Strategy

1. **Phase 1**: Restructure existing configs into modules
2. **Phase 2**: Add detection and installation scripts
3. **Phase 3**: Create profiles for common setups
4. **Phase 4**: Add support for new platforms/desktop environments
5. **Phase 5**: Advanced features (remote configs, cloud sync)

This modular approach makes your dotfiles truly portable and maintainable across different systems and use cases.