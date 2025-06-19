# Bluetooth Module

Comprehensive Bluetooth device management with automatic backups and smart connection handling.

## Features

- Automatic device backup and restore
- Smart connection management
- Profile switching
- Connection logging
- Backup rotation (keeps 3 most recent)

## Requirements

- `bluetoothctl` command available
- Bluetooth service running
- Write access to `/var/lib/bluetooth` (for backups)

## Files

- `scripts/bluetooth-manager` - Main management interface
- `scripts/bluetooth-backup-auto` - Automatic backup creation
- `scripts/bluetooth-backup-cleanup` - Backup rotation
- `config/systemd/` - Systemd service for automatic backups

## Installation

The module will:
1. Install required packages (`bluez`, `bluez-utils`)
2. Enable bluetooth service
3. Set up automatic backup timer
4. Configure backup rotation

## Usage

```bash
# Main management interface
bluetooth-manager

# Quick device switching
bluetooth

# Manual backup
bluetooth-backup-auto

# Clean old backups
bluetooth-backup-cleanup
```