#!/bin/bash

# Arch Linux Platform Installation Script

set -euo pipefail

PLATFORM_DIR="$(dirname "$0")"
DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
info() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

log "Installing Arch Linux platform packages..."

# Check if we're on Arch Linux
if [ ! -f /etc/arch-release ]; then
    error "This script is for Arch Linux only"
    exit 1
fi

# Update system
log "Updating system packages..."
sudo pacman -Syu --noconfirm

# Install packages from packages.txt
if [ -f "$PLATFORM_DIR/packages.txt" ]; then
    log "Installing packages from packages.txt..."
    
    # Filter out comments and empty lines
    packages=$(grep -v '^#' "$PLATFORM_DIR/packages.txt" | grep -v '^$' | tr '\n' ' ')
    
    if [ -n "$packages" ]; then
        sudo pacman -S --needed --noconfirm $packages
    fi
fi

# Install AUR helper if not present
if ! command -v yay >/dev/null 2>&1 && ! command -v paru >/dev/null 2>&1; then
    log "Installing yay AUR helper..."
    
    # Create temporary directory
    temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
    # Clone and install yay
    git clone https://aur.archlinux.org/yay.git
    cd yay
    makepkg -si --noconfirm
    
    # Cleanup
    cd "$HOME"
    rm -rf "$temp_dir"
fi

# Determine which AUR helper to use
if command -v yay >/dev/null 2>&1; then
    AUR_HELPER="yay"
elif command -v paru >/dev/null 2>&1; then
    AUR_HELPER="paru"
else
    warn "No AUR helper found, skipping AUR packages"
    exit 0
fi

# Install AUR packages
if [ -f "$PLATFORM_DIR/aur.txt" ]; then
    log "Installing AUR packages with $AUR_HELPER..."
    
    # Filter out comments and empty lines
    aur_packages=$(grep -v '^#' "$PLATFORM_DIR/aur.txt" | grep -v '^$' | tr '\n' ' ')
    
    if [ -n "$aur_packages" ]; then
        $AUR_HELPER -S --needed --noconfirm $aur_packages
    fi
fi

# Enable essential services
log "Enabling essential services..."
services=(
    "NetworkManager"
    "bluetooth"
    "docker"
)

for service in "${services[@]}"; do
    if systemctl list-unit-files "$service.service" >/dev/null 2>&1; then
        sudo systemctl enable "$service.service"
        info "Enabled $service service"
    else
        warn "Service $service not found, skipping"
    fi
done

# Add user to docker group if docker is installed
if command -v docker >/dev/null 2>&1; then
    log "Adding user to docker group..."
    sudo usermod -aG docker "$USER"
    info "You may need to log out and back in for docker group changes to take effect"
fi

log "Arch Linux platform setup completed!"
echo ""
echo "📋 Next steps:"
echo "  • Log out and back in for group changes to take effect"
echo "  • Run 'dotfiles-module available' to see available modules"
echo "  • Install desktop environment: 'dotfiles-module install wayland/hyprland'"