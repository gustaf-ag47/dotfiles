# 🔵 Smart Bluetooth Management System

A comprehensive Bluetooth management system integrated into your dotfiles with automatic backups, location-based connections, and smart device switching.

## 🚀 Quick Start

```bash
# Setup automation services
~/sync/src/dotfiles/bin/setup-bluetooth-automation

# Test the system
bluetooth-manager status

# Create initial backup
bluetooth-manager backup

# Quick apartment setup (connect headphones)
bluetooth-manager apartment
```

## 📱 Your Devices

Based on your current setup:

- **🎧 WH-1000XM6** (`80:99:E7:E3:EA:45`) - Primary headphones
- **🎵 WF-1000XM5** (`80:99:E7:68:25:40`) - Earbuds  
- **⌨️ AnnePro2 P1** (`64:33:DB:AD:25:55`) - Keyboard

## 🎯 Main Commands

### Basic Operations
```bash
bluetooth-manager status              # Show all devices and status
bluetooth-manager devices             # Detailed device information
bluetooth-manager backup [name]       # Create configuration backup
bluetooth-manager restore [backup]    # Restore from backup
```

### Smart Connection Profiles
```bash
bluetooth-manager apartment           # 🏠 Home setup (headphones)
bluetooth-manager office              # 🏢 Work setup (keyboard, disconnect headphones)
bluetooth-manager travel              # ✈️ Travel setup (earbuds)
bluetooth-manager auto-connect        # Connect preferred devices
```

### Device Shortcuts
```bash
bluetooth-manager headphones          # Connect WH-1000XM6
bluetooth-manager earbuds             # Connect WF-1000XM5  
bluetooth-manager keyboard            # Connect AnnePro2
bluetooth-manager connect <device>    # Connect any device
bluetooth-manager disconnect <device> # Disconnect device
```

### Profile Management
```bash
bluetooth-manager create-profile home     # Save current setup as "home"
bluetooth-manager load-profile home       # Load "home" profile
bluetooth-manager list-profiles           # Show all profiles
```

## 🔧 Automation Features

### 1. Location-Based Auto-Connection

The system can automatically detect when you enter your apartment and connect your headphones:

```bash
# Manual trigger (for testing)
~/sync/src/dotfiles/bin/apartment-trigger

# WiFi-based automation (edit network names)
vim ~/.local/bin/bluetooth-wifi-monitor
```

### 2. Daily Backups

Automatic daily backups of your Bluetooth configuration:

```bash
# Enable automatic backups
systemctl --user enable bluetooth-auto-backup.timer
systemctl --user start bluetooth-auto-backup.timer

# Check backup status
systemctl --user status bluetooth-auto-backup.timer
```

### 3. WiFi Network Monitoring

Automatically switch device profiles based on WiFi network:

```bash
# Enable WiFi monitoring
systemctl --user enable bluetooth-wifi-monitor.service
systemctl --user start bluetooth-wifi-monitor.service

# Customize network mappings
vim ~/.local/bin/bluetooth-wifi-monitor
```

## 📋 Shell Aliases

Added to your shell configuration:

```bash
bt                    # bluetooth-manager (short form)
bt-status             # Show status
bt-apartment          # Apartment setup
bt-office             # Office setup
bt-headphones         # Connect headphones quickly
bt-backup             # Create backup
```

## 🏠 Apartment Entry Automation

### Method 1: WiFi-Based Detection

Edit your WiFi networks in the monitor script:

```bash
vim ~/.local/bin/bluetooth-wifi-monitor

# Add your actual WiFi network names:
case "$CURRENT_NETWORK" in
    "YourApartmentWiFi"|"HomeNetwork")
        "$APARTMENT_TRIGGER" &
        ;;
esac
```

### Method 2: Manual Triggers

Add to your shell profile or create desktop shortcuts:

```bash
# Quick apartment setup when you get home
alias home='bluetooth-manager apartment'

# Add to .zshrc for instant home setup
echo 'alias home="bluetooth-manager apartment"' >> ~/.zshrc
```

### Method 3: Geolocation Trigger

For advanced users, integrate with location services:

```bash
# Example with geoclue (if installed)
# This would require additional setup
geoclue-monitor | while read location; do
    if [[ "$location" =~ "home_coordinates" ]]; then
        apartment-trigger
    fi
done
```

## 📊 Configuration Files

```
sync/src/dotfiles/
├── bin/
│   ├── bluetooth-manager           # Main management script
│   ├── apartment-trigger          # Apartment entry trigger
│   ├── bluetooth-backup-auto      # Auto backup script
│   └── setup-bluetooth-automation # Setup automation
├── config/
│   ├── bluetooth/
│   │   ├── backups/               # Configuration backups
│   │   ├── profiles/              # Connection profiles
│   │   └── state.json             # Current state
│   └── systemd/user/              # Service definitions
```

## 🔍 Monitoring & Logs

### Check Service Status
```bash
# Backup timer
systemctl --user status bluetooth-auto-backup.timer

# WiFi monitor
systemctl --user status bluetooth-wifi-monitor.service

# View logs
journalctl --user -u bluetooth-auto-backup.service
```

### Log Files
```bash
# Apartment trigger log
tail -f ~/.local/share/apartment-trigger.log

# WiFi monitor log  
tail -f ~/.local/share/bluetooth-wifi-monitor.log

# Bluetooth events
tail -f ~/sync/src/dotfiles/config/bluetooth/monitor.log
```

## 🛠️ Customization

### Adding New Devices

1. Pair the device normally:
```bash
bluetooth-manager scan
bluetooth-manager pair AA:BB:CC:DD:EE:FF
```

2. Add shortcut to the script:
```bash
vim ~/sync/src/dotfiles/bin/bluetooth-manager

# Add to get_device_mac() function:
"mydevice"|"My Device Name")
    echo "AA:BB:CC:DD:EE:FF"
    ;;
```

### Custom Profiles

Create profiles for different scenarios:

```bash
# Connect your desired devices manually
bluetooth-manager connect headphones
bluetooth-manager connect keyboard

# Save as profile
bluetooth-manager create-profile gaming

# Later, load the profile
bluetooth-manager load-profile gaming
```

### Custom Triggers

Create your own trigger scripts:

```bash
#!/bin/bash
# ~/bin/my-bluetooth-trigger

case "$1" in
    "work")
        bluetooth-manager office
        # Additional work setup
        ;;
    "gym")
        bluetooth-manager earbuds
        bluetooth-manager disconnect keyboard
        ;;
esac
```

## 🚨 Troubleshooting

### Common Issues

**Devices not connecting:**
```bash
# Check Bluetooth status
bluetooth-manager status

# Restart Bluetooth service
sudo systemctl restart bluetooth

# Re-pair problematic device
bluetooth-manager forget device_name
bluetooth-manager pair MAC_ADDRESS
```

**Automation not working:**
```bash
# Check if services are enabled
systemctl --user list-unit-files | grep bluetooth

# Restart services
systemctl --user restart bluetooth-wifi-monitor.service

# Check logs
journalctl --user -f -u bluetooth-wifi-monitor.service
```

**Audio issues:**
```bash
# Check PulseAudio Bluetooth modules
pactl list modules | grep bluetooth

# Restart PulseAudio
pulseaudio -k && pulseaudio --start
```

### Reset Everything

If something goes wrong:

```bash
# Stop all services
systemctl --user stop bluetooth-auto-backup.timer
systemctl --user stop bluetooth-wifi-monitor.service

# Restore from backup
bluetooth-manager restore latest

# Restart Bluetooth
sudo systemctl restart bluetooth
```

## 🔋 Battery Monitoring

The system shows battery levels for connected devices:

```bash
# View battery status
bluetooth-manager status

# Create alerts for low battery
# (Add to your notification system)
```

## 📱 Integration Examples

### With Waybar

Add Bluetooth status to your waybar:

```json
"custom/bluetooth": {
    "format": "{}",
    "exec": "bluetooth-manager status | grep -o 'Connected' | wc -l",
    "interval": 30,
    "on-click": "bluetooth-manager apartment"
}
```

### With Dunst Notifications

Get notifications when devices connect:

```bash
# Add to apartment-trigger script
notify-send "🏠 Welcome Home" "Headphones connected and ready!"
```

## 🎵 Audio Optimization

For better audio quality at home:

```bash
# Add to apartment-trigger script
# Set high-quality codec
pactl set-card-profile bluez_card.XX_XX_XX_XX_XX_XX a2dp_sink

# Adjust audio settings
pactl set-sink-volume @DEFAULT_SINK@ 80%
```

## ⚡ Performance Tips

1. **Faster connections**: Trust devices for quicker pairing
2. **Better range**: Keep devices closer during initial setup  
3. **Battery optimization**: Disconnect unused devices
4. **Audio quality**: Use A2DP profile for music, HSP for calls

Your Bluetooth management system is now fully integrated into your dotfiles and ready for smart, automated device management! 🎉