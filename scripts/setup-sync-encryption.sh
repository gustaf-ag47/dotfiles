#!/bin/bash
# Setup passphrase-encrypted Syncthing config
# Run this ONCE to create encrypted config for new machine bootstrap
#
# This encrypts your Syncthing device config with a passphrase.
# On a new machine, you'll enter the passphrase to decrypt.

set -euo pipefail

DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"
SECRETS_DIR="$DOTFILES/secrets"
SYNCTHING_CONFIG="$HOME/.local/state/syncthing/config.xml"

echo "=== Syncthing Config Encryption ==="
echo ""

# Check age is installed
if ! command -v age &>/dev/null; then
    echo "Installing age..."
    sudo pacman -S --noconfirm age
fi

# Create secrets directory
mkdir -p "$SECRETS_DIR"

# Check Syncthing config exists
if [ ! -f "$SYNCTHING_CONFIG" ]; then
    echo "ERROR: Syncthing config not found at $SYNCTHING_CONFIG"
    echo "Make sure Syncthing has been run at least once."
    exit 1
fi

# Extract essential config (device IDs and folder config)
echo "Extracting Syncthing configuration..."

# Create a bootstrap config with device IDs and folder setup
cat > /tmp/syncthing-bootstrap.xml << 'XMLEOF'
<?xml version="1.0" encoding="UTF-8"?>
<configuration version="37">
XMLEOF

# Extract devices
grep -E '<device id=|name=|</device>' "$SYNCTHING_CONFIG" | head -20 >> /tmp/syncthing-bootstrap.xml

# Extract folder config
grep -E '<folder id=|path=|</folder>|<device id=' "$SYNCTHING_CONFIG" | head -30 >> /tmp/syncthing-bootstrap.xml

echo '</configuration>' >> /tmp/syncthing-bootstrap.xml

# Show known devices
echo ""
echo "Known devices in your sync network:"
grep 'device id=' "$SYNCTHING_CONFIG" | grep -oP 'id="\K[^"]+' | sort -u | while read -r id; do
    name=$(grep -A1 "id=\"$id\"" "$SYNCTHING_CONFIG" | grep -oP 'name="\K[^"]+' | head -1)
    echo "  $name: $id"
done

# Encrypt the bootstrap config with passphrase
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║ Enter a passphrase to encrypt your Syncthing config.              ║"
echo "║ You'll need this passphrase when setting up a new machine.        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

age -p -o "$SECRETS_DIR/syncthing-bootstrap.xml.age" /tmp/syncthing-bootstrap.xml
rm /tmp/syncthing-bootstrap.xml

echo ""
echo "✓ Encrypted config saved to: $SECRETS_DIR/syncthing-bootstrap.xml.age"

# Test decryption
echo ""
echo "Testing decryption (enter the same passphrase)..."
if age -d "$SECRETS_DIR/syncthing-bootstrap.xml.age" > /dev/null 2>&1; then
    echo "✓ Decryption test passed!"
else
    echo "ERROR: Decryption test failed!"
    exit 1
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Files created in $SECRETS_DIR/:"
ls -la "$SECRETS_DIR/"
echo ""
echo "On a new machine, run: ./scripts/bootstrap-sync.sh"
echo "It will prompt for the passphrase to decrypt the config."
