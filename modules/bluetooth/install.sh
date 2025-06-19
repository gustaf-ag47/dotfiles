#!/bin/bash

# Bluetooth Module Installation Script

set -euo pipefail

DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"
MODULE_DIR="$DOTFILES/modules/bluetooth"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

log "Installing Bluetooth module..."

# Install packages based on platform
if command -v pacman >/dev/null 2>&1; then
    # Arch Linux
    log "Installing bluetooth packages (Arch Linux)..."
    sudo pacman -S --needed bluez bluez-utils
elif command -v apt >/dev/null 2>&1; then
    # Ubuntu/Debian
    log "Installing bluetooth packages (Ubuntu/Debian)..."
    sudo apt update
    sudo apt install -y bluez bluetooth
elif command -v dnf >/dev/null 2>&1; then
    # Fedora
    log "Installing bluetooth packages (Fedora)..."
    sudo dnf install -y bluez bluez-tools
else
    warn "Unknown package manager, please install bluetooth packages manually"
fi

# Enable bluetooth service
log "Enabling bluetooth service..."
sudo systemctl enable bluetooth.service
sudo systemctl start bluetooth.service

# Copy scripts to bin directory
log "Installing bluetooth scripts..."
cp "$MODULE_DIR/../../../bin/bluetooth-manager" "$DOTFILES/bin/" 2>/dev/null || true
cp "$MODULE_DIR/../../../bin/bluetooth-backup-auto" "$DOTFILES/bin/" 2>/dev/null || true
cp "$MODULE_DIR/../../../bin/bluetooth-backup-cleanup" "$DOTFILES/bin/" 2>/dev/null || true

# Make scripts executable
chmod +x "$DOTFILES/bin/bluetooth"* 2>/dev/null || true

# Create bluetooth config directory
mkdir -p "$DOTFILES/config/bluetooth/backups"

# Install systemd service and timer if available
if [ -f "$MODULE_DIR/config/systemd/bluetooth-auto-backup.service" ]; then
    log "Installing systemd service..."
    cp "$MODULE_DIR/config/systemd/"* "$HOME/.config/systemd/user/" 2>/dev/null || true
    systemctl --user daemon-reload
    systemctl --user enable bluetooth-auto-backup.timer
    systemctl --user start bluetooth-auto-backup.timer
fi

# Create initial backup
log "Creating initial bluetooth backup..."
if command -v bluetooth-backup-auto >/dev/null 2>&1; then
    bluetooth-backup-auto || warn "Failed to create initial backup"
fi

log "Bluetooth module installed successfully!"
echo ""
echo "📋 Available commands:"
echo "  • bluetooth-manager      - Full management interface"
echo "  • bluetooth              - Quick device switching"
echo "  • bluetooth-backup-auto  - Create backup"
echo "  • bluetooth-backup-cleanup - Clean old backups"