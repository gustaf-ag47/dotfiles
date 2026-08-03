#!/bin/bash
# Bootstrap script for setting up Syncthing on a new machine
# Run this AFTER the basic Arch install and dotfiles clone
#
# Usage: ./scripts/bootstrap-sync.sh
#
# If encrypted config exists:
#   - Decrypts config with passphrase
#   - Shows known devices for easy setup
#
# Otherwise:
#   - Manual setup via web UI

set -euo pipefail

DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"
SYNC_DIR="${SYNC:-$HOME/sync}"
SECRETS_DIR="$DOTFILES/secrets"
ENCRYPTED_CONFIG="$SECRETS_DIR/syncthing-bootstrap.xml.age"
SYNCTHING_CONFIG_DIR="$HOME/.local/state/syncthing"

echo "=== Syncthing Bootstrap ==="
echo ""

# Step 1: Install Syncthing if not present
if ! command -v syncthing &> /dev/null; then
    echo "[1/5] Installing Syncthing..."
    sudo pacman -S --noconfirm syncthing
else
    echo "[1/5] Syncthing already installed ✓"
fi

# Step 2: Check for encrypted config
if [ -f "$ENCRYPTED_CONFIG" ]; then
    echo "[2/5] Found encrypted Syncthing config"
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║ Enter the passphrase to decrypt your Syncthing config.            ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo ""

    # Check age is installed
    if ! command -v age &> /dev/null; then
        echo "Installing age..."
        sudo pacman -S --noconfirm age
    fi

    # Decrypt config
    mkdir -p "$SYNCTHING_CONFIG_DIR"

    if age -d "$ENCRYPTED_CONFIG" > /tmp/syncthing-bootstrap.xml 2>/dev/null; then
        echo "✓ Config decrypted successfully!"

        # Extract device IDs from decrypted config
        echo ""
        echo "[3/5] Known devices from your network:"
        grep 'name=' /tmp/syncthing-bootstrap.xml | grep -oP 'name="\K[^"]+' | while read -r name; do
            echo "  - $name"
        done

        # Start Syncthing to generate initial config
        echo ""
        echo "[4/5] Starting Syncthing to generate base config..."
        systemctl --user enable syncthing.service
        systemctl --user start syncthing.service
        sleep 5

        # Get this device's ID
        DEVICE_ID=$(syncthing --device-id 2>/dev/null || syncthing cli show system 2>/dev/null | grep -oP 'myID":"\K[^"]+')
        echo ""
        echo "╔════════════════════════════════════════════════════════════════════╗"
        echo "║ THIS DEVICE'S ID (add on your existing machines):                 ║"
        echo "╠════════════════════════════════════════════════════════════════════╣"
        printf "║ %-68s ║\n" "$DEVICE_ID"
        echo "╚════════════════════════════════════════════════════════════════════╝"

        # Import devices from encrypted config via API
        echo ""
        echo "[5/5] Importing device configuration..."
        echo ""
        echo "Opening Syncthing web UI..."
        echo "Please manually:"
        echo "  1. Add the known devices (IDs shown above)"
        echo "  2. On your OTHER machine, accept this device and share 'sync' folder"
        echo "  3. Create folder: mkdir -p $SYNC_DIR"
        echo "  4. Accept the shared folder in Syncthing UI"
        echo ""

        rm -f /tmp/syncthing-bootstrap.xml

        # Open browser
        if command -v xdg-open &> /dev/null; then
            sleep 2
            xdg-open "http://127.0.0.1:8384" 2>/dev/null &
        fi

    else
        echo "ERROR: Failed to decrypt config. Wrong passphrase?"
        echo "Falling back to manual setup..."
        USE_MANUAL=true
    fi
else
    echo "[2/5] No encrypted config found, using manual setup"
    USE_MANUAL=true
fi

# Manual setup fallback
if [ "${USE_MANUAL:-false}" = true ]; then
    echo ""
    echo "[3/5] Starting Syncthing..."
    systemctl --user enable syncthing.service
    systemctl --user start syncthing.service
    sleep 3

    DEVICE_ID=$(syncthing --device-id 2>/dev/null || echo "Run 'syncthing --device-id' to get ID")

    echo ""
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║ THIS DEVICE'S ID:                                                  ║"
    echo "╠════════════════════════════════════════════════════════════════════╣"
    printf "║ %-68s ║\n" "$DEVICE_ID"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "[4/5] Known devices in your sync network:"
    # Device IDs are personal, so they are not hardcoded in this public repo.
    # They live in the decrypted bootstrap config; list them from an existing
    # machine with:  syncthing cli config devices list
    if [ -f "$SECRETS_DIR/known-devices.txt" ]; then
        sed 's/^/  /' "$SECRETS_DIR/known-devices.txt"
    else
        echo "  (run 'syncthing cli config devices list' on an existing machine,"
        echo "   or see $SECRETS_DIR/known-devices.txt)"
    fi
    echo ""
    echo "[5/5] Manual steps:"
    echo "  1. Open: http://127.0.0.1:8384"
    echo "  2. Add Remote Device → paste device ID from above"
    echo "  3. On existing machine: accept + share 'sync' folder"
    echo "  4. Create: mkdir -p $SYNC_DIR"
    echo "  5. Accept shared folder in UI"
    echo ""

    if command -v xdg-open &> /dev/null; then
        read -p "Open Syncthing web UI? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            xdg-open "http://127.0.0.1:8384" 2>/dev/null &
        fi
    fi
fi

# Wait for sync
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "Press Enter once the sync folder is connected and initial sync complete..."
read -r

if [ -d "$SYNC_DIR/src/dotfiles" ]; then
    echo ""
    echo "✓ Sync folder detected with dotfiles!"
    echo ""
    read -p "Run full dotfiles install now? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        cd "$SYNC_DIR/src/dotfiles"
        ./scripts/install.sh
    fi
else
    echo ""
    echo "Sync folder not ready yet. Once synced, run:"
    echo "  cd $SYNC_DIR/src/dotfiles && ./scripts/install.sh"
fi

echo ""
echo "=== Bootstrap complete ==="
