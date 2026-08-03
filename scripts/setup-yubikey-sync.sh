#!/bin/bash
# Setup YubiKey-encrypted Syncthing config
# Run this ONCE with YubiKey plugged in to create encrypted config
#
# This creates an age identity on your YubiKey and encrypts
# your Syncthing config so only your YubiKey can decrypt it.

set -euo pipefail

DOTFILES="${DOTFILES:-$HOME/sync/src/dotfiles}"
SECRETS_DIR="$DOTFILES/secrets"
IDENTITY_FILE="$SECRETS_DIR/yubikey-identity.txt"
SYNCTHING_CONFIG="$HOME/.local/state/syncthing/config.xml"

echo "=== YubiKey Syncthing Config Encryption ==="
echo ""

# Check YubiKey is present
if ! ykman info &>/dev/null; then
    echo "ERROR: No YubiKey detected! Please insert your YubiKey."
    exit 1
fi

echo "✓ YubiKey detected"

# Check age-plugin-yubikey is installed
if ! command -v age-plugin-yubikey &>/dev/null; then
    echo "Installing age-plugin-yubikey..."
    paru -S --noconfirm age-plugin-yubikey || yay -S --noconfirm age-plugin-yubikey
fi

# Create secrets directory
mkdir -p "$SECRETS_DIR"

# Check for existing identity or generate new one
echo ""
echo "Checking for existing YubiKey age identity..."
EXISTING=$(age-plugin-yubikey --list 2>/dev/null || true)

if [ -z "$EXISTING" ]; then
    echo "No identity found. Generating new age identity on YubiKey..."
    echo ""
    echo "You may need to touch your YubiKey and enter PIN."
    echo ""

    # Generate identity (slot 1, touch required)
    age-plugin-yubikey --generate --slot 1 --touch-policy always --pin-policy once > "$IDENTITY_FILE"

    echo ""
    echo "✓ Identity generated and saved to: $IDENTITY_FILE"
else
    echo "✓ Existing identity found"
    echo "$EXISTING" > "$IDENTITY_FILE"
fi

# Extract recipient (public key) from identity
RECIPIENT=$(grep "^age1yubikey" "$IDENTITY_FILE" | head -1)
echo ""
echo "Recipient (public key): $RECIPIENT"

# Save recipient separately for easy access
echo "$RECIPIENT" > "$SECRETS_DIR/yubikey-recipient.txt"

# Check Syncthing config exists
if [ ! -f "$SYNCTHING_CONFIG" ]; then
    echo ""
    echo "ERROR: Syncthing config not found at $SYNCTHING_CONFIG"
    echo "Make sure Syncthing has been run at least once."
    exit 1
fi

# Extract essential config (device IDs and folder config)
echo ""
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

# Also save the known device IDs in plain text (not secret, just identifiers)
echo ""
echo "Known devices:"
grep 'device id=' "$SYNCTHING_CONFIG" | grep -oP 'id="\K[^"]+' | sort -u | while read -r id; do
    name=$(grep -A1 "id=\"$id\"" "$SYNCTHING_CONFIG" | grep -oP 'name="\K[^"]+' | head -1)
    echo "  $name: $id"
done

# Encrypt the bootstrap config
echo ""
echo "Encrypting config with YubiKey (touch required)..."
age -r "$RECIPIENT" -o "$SECRETS_DIR/syncthing-bootstrap.xml.age" /tmp/syncthing-bootstrap.xml
rm /tmp/syncthing-bootstrap.xml

echo ""
echo "✓ Encrypted config saved to: $SECRETS_DIR/syncthing-bootstrap.xml.age"

# Create decryption test
echo ""
echo "Testing decryption (touch YubiKey)..."
if age -d -i "$IDENTITY_FILE" "$SECRETS_DIR/syncthing-bootstrap.xml.age" > /dev/null 2>&1; then
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
echo "It will prompt for YubiKey to decrypt the config."
