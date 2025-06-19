# 🏗️ Modular Dotfiles Guide

Your dotfiles are now organized using a modular architecture for maximum portability and maintainability.

## 🚀 Quick Start

### 1. **System Detection**
```bash
# See what your system supports
dotfiles-module detect

# Check specific components
./install/detect.sh platform    # arch, ubuntu, macos
./install/detect.sh desktop     # wayland/hyprland, x11/i3
./install/detect.sh modules     # available feature modules
```

### 2. **Module Management**
```bash
# Initialize the module system
dotfiles-module init

# See available modules for your system
dotfiles-module available

# Install and enable a module
dotfiles-module install bluetooth

# Manage modules
dotfiles-module enable power-management
dotfiles-module disable bluetooth
dotfiles-module status all
```

### 3. **Platform Installation**
```bash
# Install platform-specific packages
./platforms/arch/install.sh        # Arch Linux
./platforms/ubuntu/install.sh      # Ubuntu (when created)
```

## 📁 **Directory Structure**

```
dotfiles/
├── 🔧 core/                    # Universal configs (works everywhere)
├── 🐧 platforms/               # OS-specific (arch, ubuntu, macos)
├── 🖥️  desktop/                # Desktop environments (wayland, x11)
├── 📱 applications/            # App-specific configs
├── 🔌 modules/                 # Feature modules (bluetooth, power)
├── 🎨 themes/                  # Visual themes
├── 📋 profiles/                # Pre-configured setups
└── ⚙️  install/                # Installation scripts
```

## 🔍 **How It Works**

### **Conditional Loading**
Each module includes a `detect.sh` script:
```bash
# modules/bluetooth/detect.sh
#!/bin/bash
command -v bluetoothctl >/dev/null 2>&1 && exit 0 || exit 1
```

### **Module Structure**
```
module-name/
├── detect.sh       # Check if module should load
├── install.sh      # Installation script  
├── README.md       # Documentation
├── config/         # Configuration files
└── scripts/        # Module-specific scripts
```

### **Loading Priority**
1. **Core** - Base functionality
2. **Platform** - OS-specific configs
3. **Desktop** - DE-specific configs
4. **Applications** - App configs
5. **Modules** - Feature modules
6. **Theme** - Visual theme
7. **Profile** - Preset combinations

## 🎯 **Common Workflows**

### **Setting Up a New Machine**
```bash
# 1. Clone dotfiles
git clone <repo> ~/.dotfiles && cd ~/.dotfiles

# 2. Auto-detect and install
dotfiles-module detect                    # See what's available
./platforms/$(./install/detect.sh platform)/install.sh  # Install platform packages
dotfiles-module init                      # Initialize modules
dotfiles-module install bluetooth        # Install specific modules

# 3. Install desktop environment configs
dotfiles-module install wayland/hyprland # Or your preferred DE
```

### **Adding a New Module**
```bash
# 1. Create module structure
mkdir -p modules/new-module/{config,scripts}

# 2. Create detection script
cat > modules/new-module/detect.sh << 'EOF'
#!/bin/bash
command -v new-tool >/dev/null 2>&1
EOF

# 3. Create installation script
cat > modules/new-module/install.sh << 'EOF'
#!/bin/bash
# Install packages, copy configs, etc.
EOF

# 4. Test and install
dotfiles-module install new-module
```

### **Creating a Profile**
```bash
# profiles/developer-arch-hyprland/install.sh
#!/bin/bash
dotfiles-module install bluetooth
dotfiles-module install power-management
dotfiles-module install wayland/hyprland
# ... more modules
```

## 🔧 **Advanced Usage**

### **Override Configurations**
```bash
# Override platform-specific configs
modules/bluetooth/override/arch/config.conf     # Arch-specific override
modules/bluetooth/override/minimal/config.conf  # Minimal override
```

### **Custom Profiles**
```bash
# Create custom profile
mkdir profiles/my-setup
cat > profiles/my-setup/install.sh << 'EOF'
#!/bin/bash
./platforms/arch/install.sh
dotfiles-module install bluetooth power-management
# Custom setup commands
EOF
```

### **Module Dependencies**
```bash
# modules/advanced-feature/install.sh
#!/bin/bash
# Check dependencies
dotfiles-module status bluetooth | grep -q "Enabled" || {
    echo "Installing required dependency: bluetooth"
    dotfiles-module install bluetooth
}
```

## 🎨 **Theme Management**

### **Switching Themes**
```bash
# Apply Tokyo Night theme
ln -sf themes/tokyo-night/starship.toml config/starship.toml

# Apply Catppuccin theme  
ln -sf themes/catppuccin/starship.toml config/starship.toml
```

### **Creating New Themes**
```bash
mkdir -p themes/my-theme
# Add theme files (colors, wallpapers, etc.)
# Create theme application script
```

## 🚚 **Migration from Old Structure**

### **Automated Migration**
```bash
# Backup and migrate existing dotfiles
./install/migrate-to-modular.sh

# Review changes
cat MIGRATION-SUMMARY.md

# Initialize new system
dotfiles-module init
```

### **Manual Migration**
```bash
# Move configs to appropriate modules
mv config/bluetooth modules/bluetooth/config/
mv config/zsh core/shell/zsh/

# Update symlinks and paths
# Test functionality
```

## 🔍 **Troubleshooting**

### **Module Not Loading**
```bash
# Check detection
./modules/module-name/detect.sh && echo "OK" || echo "Requirements not met"

# Check status  
dotfiles-module status module-name

# Reinstall
dotfiles-module disable module-name
dotfiles-module install module-name
```

### **Platform Issues**
```bash
# Verify platform detection
./install/detect.sh platform

# Check platform packages
cat platforms/$(./install/detect.sh platform)/packages.txt

# Reinstall platform
./platforms/$(./install/detect.sh platform)/install.sh
```

## 📚 **Benefits**

### **For Users**
- ✅ **Selective Installation**: Only install what you need
- ✅ **Easy Customization**: Override specific modules
- ✅ **Quick Setup**: Pre-configured profiles
- ✅ **Cross-Platform**: Works on multiple OS/DE combinations

### **For Maintainers**  
- ✅ **Modular Testing**: Test components in isolation
- ✅ **Clear Dependencies**: Each module declares requirements
- ✅ **Easy Updates**: Update one component at a time
- ✅ **Platform Support**: Easy to add new platforms

### **For Contributors**
- ✅ **Clear Structure**: Know where to add features
- ✅ **Isolated Changes**: Changes don't affect other modules
- ✅ **Self-Documenting**: Each module includes documentation

## 🎯 **Examples**

### **Minimal Server Setup**
```bash
# Just core tools, no GUI
dotfiles-module install shell editor git
```

### **Full Development Workstation**
```bash
# Everything for development
./platforms/arch/install.sh
dotfiles-module install bluetooth power-management
dotfiles-module install wayland/hyprland
dotfiles-module install development/languages/all
```

### **Gaming Setup**
```bash
# Gaming-optimized configuration
dotfiles-module install power-management
dotfiles-module install gaming/steam
dotfiles-module install media/discord
```

This modular approach makes your dotfiles truly portable and maintainable across different systems and use cases! 🚀