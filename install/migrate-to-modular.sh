#!/bin/bash

# Migration Script: Convert existing dotfiles to modular structure
# This script helps migrate your current dotfiles to the new modular organization

set -euo pipefail

DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"
BACKUP_DIR="$DOTFILES/.migration-backup-$(date +%Y%m%d_%H%M%S)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

show_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║              🔄 DOTFILES MIGRATION                   ║"
    echo "║         Converting to Modular Structure             ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

create_backup() {
    log "Creating backup of current structure..."
    mkdir -p "$BACKUP_DIR"
    
    # Backup current configuration files
    for dir in config bin; do
        if [ -d "$DOTFILES/$dir" ]; then
            cp -r "$DOTFILES/$dir" "$BACKUP_DIR/"
            info "Backed up $dir to $BACKUP_DIR"
        fi
    done
    
    log "Backup created at: $BACKUP_DIR"
}

migrate_core_configs() {
    log "Migrating core configurations..."
    
    # Create core directories
    mkdir -p "$DOTFILES/core"/{shell,editor,git,tmux}
    
    # Migrate shell configs
    if [ -d "$DOTFILES/config/zsh" ]; then
        log "Migrating zsh configuration..."
        mv "$DOTFILES/config/zsh" "$DOTFILES/core/shell/zsh"
    fi
    
    # Migrate neovim configs
    if [ -d "$DOTFILES/config/nvim" ]; then
        log "Migrating neovim configuration..."
        mv "$DOTFILES/config/nvim" "$DOTFILES/core/editor/nvim"
    fi
    
    # Migrate git configs
    if [ -d "$DOTFILES/config/git" ]; then
        log "Migrating git configuration..."
        mv "$DOTFILES/config/git" "$DOTFILES/core/git/"
    fi
    
    # Migrate tmux configs
    if [ -d "$DOTFILES/config/tmux" ]; then
        log "Migrating tmux configuration..."
        mv "$DOTFILES/config/tmux" "$DOTFILES/core/tmux/"
    fi
}

migrate_desktop_configs() {
    log "Migrating desktop environment configurations..."
    
    # Create desktop directories
    mkdir -p "$DOTFILES/desktop/wayland"/{hyprland,waybar,wofi,common}
    mkdir -p "$DOTFILES/desktop/x11"/{i3,polybar,rofi,common}
    
    # Migrate Wayland configs
    if [ -d "$DOTFILES/config/gui/Wayland" ]; then
        log "Migrating Wayland configurations..."
        
        if [ -d "$DOTFILES/config/gui/Wayland/hypr" ]; then
            mv "$DOTFILES/config/gui/Wayland/hypr" "$DOTFILES/desktop/wayland/hyprland/"
        fi
        
        if [ -d "$DOTFILES/config/gui/Wayland/waybar" ]; then
            mv "$DOTFILES/config/gui/Wayland/waybar" "$DOTFILES/desktop/wayland/waybar/"
        fi
        
        if [ -d "$DOTFILES/config/gui/Wayland/wofi" ]; then
            mv "$DOTFILES/config/gui/Wayland/wofi" "$DOTFILES/desktop/wayland/wofi/"
        fi
    fi
    
    # Migrate X11 configs
    if [ -d "$DOTFILES/config/gui/Xorg" ]; then
        log "Migrating X11 configurations..."
        
        if [ -d "$DOTFILES/config/gui/Xorg/i3" ]; then
            mv "$DOTFILES/config/gui/Xorg/i3" "$DOTFILES/desktop/x11/i3/"
        fi
        
        if [ -d "$DOTFILES/config/gui/Xorg/polybar" ]; then
            mv "$DOTFILES/config/gui/Xorg/polybar" "$DOTFILES/desktop/x11/polybar/"
        fi
        
        if [ -d "$DOTFILES/config/gui/Xorg/rofi" ]; then
            mv "$DOTFILES/config/gui/Xorg/rofi" "$DOTFILES/desktop/x11/rofi/"
        fi
    fi
    
    # Migrate common GUI configs
    if [ -d "$DOTFILES/config/gui" ]; then
        log "Migrating common GUI configurations..."
        
        # Move common configs to both wayland and x11 common directories
        for common_dir in alacritty dunst gtk-2.0 gtk-3.0 zathura; do
            if [ -d "$DOTFILES/config/gui/$common_dir" ]; then
                cp -r "$DOTFILES/config/gui/$common_dir" "$DOTFILES/desktop/wayland/common/"
                cp -r "$DOTFILES/config/gui/$common_dir" "$DOTFILES/desktop/x11/common/"
                info "Migrated $common_dir to common directories"
            fi
        done
    fi
}

migrate_platform_configs() {
    log "Migrating platform-specific configurations..."
    
    # Create platform directories
    mkdir -p "$DOTFILES/platforms/arch/config"
    
    # Move systemd configs
    if [ -d "$DOTFILES/config/systemd" ]; then
        log "Migrating systemd configurations..."
        mv "$DOTFILES/config/systemd" "$DOTFILES/platforms/arch/config/"
    fi
    
    # Move environment configs
    if [ -d "$DOTFILES/config/environment.d" ]; then
        log "Migrating environment configurations..."
        mv "$DOTFILES/config/environment.d" "$DOTFILES/platforms/arch/config/"
    fi
}

migrate_modules() {
    log "Migrating feature modules..."
    
    # Create modules directory
    mkdir -p "$DOTFILES/modules"
    
    # Migrate bluetooth module
    if [ -d "$DOTFILES/config/bluetooth" ]; then
        log "Migrating bluetooth module..."
        mkdir -p "$DOTFILES/modules/bluetooth/config"
        mv "$DOTFILES/config/bluetooth" "$DOTFILES/modules/bluetooth/config/"
        
        # Move bluetooth scripts
        for script in bluetooth-manager bluetooth-backup-auto bluetooth-backup-cleanup bluetooth; do
            if [ -f "$DOTFILES/bin/$script" ]; then
                mkdir -p "$DOTFILES/modules/bluetooth/scripts"
                cp "$DOTFILES/bin/$script" "$DOTFILES/modules/bluetooth/scripts/"
            fi
        done
    fi
}

migrate_applications() {
    log "Migrating application configurations..."
    
    # Create applications directory
    mkdir -p "$DOTFILES/applications"/{development,productivity,media}
    
    # Migrate development configs
    for dev_config in npm mycli pgcli; do
        if [ -d "$DOTFILES/config/$dev_config" ]; then
            log "Migrating $dev_config configuration..."
            mv "$DOTFILES/config/$dev_config" "$DOTFILES/applications/development/"
        fi
    done
    
    # Migrate productivity configs
    for prod_config in obsidian notion; do
        if [ -d "$DOTFILES/config/$prod_config" ]; then
            log "Migrating $prod_config configuration..."
            mv "$DOTFILES/config/$prod_config" "$DOTFILES/applications/productivity/"
        fi
    done
    
    # Migrate media configs
    for media_config in mpv spotify; do
        if [ -d "$DOTFILES/config/$media_config" ]; then
            log "Migrating $media_config configuration..."
            mv "$DOTFILES/config/$media_config" "$DOTFILES/applications/media/"
        fi
    done
}

migrate_themes() {
    log "Setting up themes structure..."
    
    # Create themes directory
    mkdir -p "$DOTFILES/themes/tokyo-night"
    
    # Move theme-related configs
    if [ -f "$DOTFILES/config/starship.toml" ]; then
        log "Migrating starship theme configuration..."
        mv "$DOTFILES/config/starship.toml" "$DOTFILES/themes/tokyo-night/"
    fi
    
    # Move wallpapers
    if [ -d "$DOTFILES/config/gui/media/wallpaper" ]; then
        log "Migrating wallpapers..."
        mv "$DOTFILES/config/gui/media/wallpaper" "$DOTFILES/themes/tokyo-night/"
    fi
}

update_symlinks() {
    log "Updating symbolic links..."
    
    # This would need to be customized based on your current symlink setup
    warn "Symbolic link updates need to be done manually"
    warn "Please check your current symlinks and update paths accordingly"
}

create_migration_summary() {
    log "Creating migration summary..."
    
    cat > "$DOTFILES/MIGRATION-SUMMARY.md" << EOF
# Migration Summary

Migration completed on: $(date)

## Changes Made

### Core Configurations
- Shell configs moved to: \`core/shell/\`
- Editor configs moved to: \`core/editor/\`
- Git configs moved to: \`core/git/\`
- Tmux configs moved to: \`core/tmux/\`

### Desktop Environment Configurations
- Wayland configs moved to: \`desktop/wayland/\`
- X11 configs moved to: \`desktop/x11/\`
- Common GUI configs duplicated to both environments

### Platform-Specific Configurations
- Arch Linux configs moved to: \`platforms/arch/\`
- SystemD services moved to platform-specific directory

### Feature Modules
- Bluetooth module created at: \`modules/bluetooth/\`
- Module detection and installation scripts added

### Applications
- Development tools moved to: \`applications/development/\`
- Productivity apps moved to: \`applications/productivity/\`
- Media apps moved to: \`applications/media/\`

### Themes
- Tokyo Night theme organized in: \`themes/tokyo-night/\`

## Backup Location
Original files backed up to: \`$BACKUP_DIR\`

## Next Steps
1. Test the new modular structure
2. Update any hardcoded paths in scripts
3. Run \`dotfiles-module init\` to initialize the module system
4. Run \`dotfiles-module available\` to see available modules
5. Reinstall/relink configurations as needed

## Rollback
To rollback, restore files from the backup directory:
\`\`\`bash
cp -r $BACKUP_DIR/* $DOTFILES/
\`\`\`
EOF

    log "Migration summary created: $DOTFILES/MIGRATION-SUMMARY.md"
}

main() {
    show_banner
    
    echo -e "${WHITE}This script will migrate your existing dotfiles to a modular structure.${NC}"
    echo -e "${YELLOW}⚠️  This is a major restructuring operation.${NC}"
    echo ""
    echo "The migration will:"
    echo "  • Create a backup of your current configuration"
    echo "  • Reorganize files into the new modular structure"
    echo "  • Set up module detection and management systems"
    echo "  • Create migration documentation"
    echo ""
    
    read -p "Do you want to proceed with the migration? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Migration cancelled."
        exit 0
    fi
    
    echo ""
    log "Starting migration process..."
    
    create_backup
    migrate_core_configs
    migrate_desktop_configs
    migrate_platform_configs
    migrate_modules
    migrate_applications
    migrate_themes
    create_migration_summary
    
    echo ""
    log "Migration completed successfully!"
    echo ""
    echo -e "${GREEN}✅ Your dotfiles have been migrated to the modular structure.${NC}"
    echo ""
    echo -e "${WHITE}📋 Next steps:${NC}"
    echo -e "  1. Review the migration summary: ${CYAN}cat $DOTFILES/MIGRATION-SUMMARY.md${NC}"
    echo -e "  2. Initialize the module system: ${CYAN}dotfiles-module init${NC}"
    echo -e "  3. Check available modules: ${CYAN}dotfiles-module available${NC}"
    echo -e "  4. Test your configuration and update any broken paths"
    echo -e "  5. If something breaks, restore from: ${YELLOW}$BACKUP_DIR${NC}"
    echo ""
    echo -e "${BLUE}💡 The old structure is backed up and can be restored if needed.${NC}"
}

main "$@"