# Backup & Restore Guide

This document describes the backup and restore system for your dotfiles and system configuration.

## Overview

The backup system creates timestamped, comprehensive backups of critical system and user data to `$SYNC/backup/`. All backups are stored as compressed tarballs with preserved permissions.

## Location

- **Backup Scripts**: `$DOTFILES/bin/backup` and `$DOTFILES/bin/backup-borg`
- **Restore Script**: `$DOTFILES/bin/restore`
- **Backup Storage**: `$BACKUP_DIR` (defaults to `$SYNC/backup/`)
- **Environment**: `BACKUP_DIR` must be set (automatically configured in dotfiles)

## Quick Start

### Create Backup

```bash
# Ensure BACKUP_DIR is set
export BACKUP_DIR="$SYNC/backup"

# Run backup (creates timestamped archive)
backup
```

### Restore from Backup

```bash
# List available backups
ls -lh $SYNC/backup/*.tar.gz

# Extract desired backup
tar -xzf $SYNC/backup/2024-11-08_09-56-50.tar.gz -C $SYNC/backup/

# Run restore
restore
```

### Borg Backup (External Drive)

```bash
# Backup entire $SYNC to external drive
backup-borg
```

## What Gets Backed Up

### System Configuration
- `/var/lib/bluetooth` - Bluetooth pairings
- `/etc/NetworkManager/system-connections` - Network connections
- `/etc/systemd/system` - Systemd service units
- `/etc/fstab`, `/etc/hostname`, `/etc/hosts` - System files

### User Credentials & Secrets (600/700 permissions)
- `~/.ssh/` - SSH keys and configuration
- `~/.gnupg/` - GPG keys
- `~/.aws/` - AWS credentials and configuration
- `~/.kube/` - Kubernetes cluster configurations
- `~/.password-store/` - Pass password manager store
- `~/.claude/` - Claude Code credentials
- `~/.claude.json` - Claude Code configuration
- `~/.docker/` - Docker credentials
- `~/.pulumi/` - Pulumi state and credentials
- `~/.env` - Environment variables file

### Development Tools
- `~/.cargo/` - Rust/Cargo configuration
- `~/.terraform.d/` - Terraform plugins and configuration

### Application Data
- `~/.mozilla/firefox/` - Firefox profiles and data
- `~/.thunderbird/` - Thunderbird email data
- `$XDG_CONFIG_HOME/tmuxp/` - Tmux session templates
- `$ZDOTDIR/.zhistory` - Zsh command history

### Package Lists
- Installed packages (`pacman -Qqe`)
- AUR packages (`pacman -Qqm`)
- User crontab

## Backup Structure

Each backup creates a timestamped directory:

```
$BACKUP_DIR/
├── 2024-11-08_09-56-50/
│   ├── aws/                    # AWS credentials
│   ├── bluetooth/              # Bluetooth pairings
│   ├── cargo/                  # Cargo config
│   ├── claude/                 # Claude settings
│   ├── claude.json             # Claude config file
│   ├── docker/                 # Docker credentials
│   ├── env                     # Environment variables
│   ├── firefox-data/           # Firefox profiles
│   ├── gnupg/                  # GPG keys
│   ├── kube/                   # Kubernetes configs
│   ├── network-connections/    # NetworkManager
│   ├── password-store/         # Pass passwords
│   ├── pulumi/                 # Pulumi state
│   ├── ssh-keys/               # SSH keys
│   ├── systemd-services/       # Systemd units
│   ├── terraform.d/            # Terraform plugins
│   ├── thunderbird-data/       # Thunderbird data
│   ├── tmuxp-sessions/         # Tmux sessions
│   ├── zhistory                # Shell history
│   ├── aurlist.txt             # AUR packages
│   ├── crontab                 # User crontab
│   ├── fstab                   # Filesystem table
│   ├── hostname                # System hostname
│   ├── hosts                   # Hosts file
│   ├── permission_log.txt      # Original permissions
│   └── pkglist.txt             # Installed packages
└── 2024-11-08_09-56-50.tar.gz  # Compressed archive
```

## Permission Management

The backup script:
1. **Logs** original permissions to `permission_log.txt`
2. **Sets** secure permissions during backup:
   - Sensitive files/dirs: `600`/`700` (owner only)
   - Config files: `644`/`755` (standard)
3. **Restores** using `restore` script

## Automation

### Systemd Timer (Example)

A systemd timer is set up for automatic Bluetooth backups. You can extend this pattern:

```bash
# View timer status
systemctl --user list-timers | grep backup

# Example timer (bluetooth-auto-backup.timer)
[Unit]
Description=Backup Timer
Requires=backup.service

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

## Backup Strategies

### Local Backup (Default)
```bash
# Manual backup
export BACKUP_DIR="$SYNC/backup"
backup
```

### Borg Backup (Recommended for External Storage)
```bash
# Initialize repository (first time)
borg init --encryption=repokey /path/to/repo

# Backup entire $SYNC
backup-borg

# List backups
borg list /path/to/repo

# Restore specific backup
borg extract /path/to/repo::backup-2024-11-08
```

### Cloud Sync
Since backups are stored in `$SYNC/backup/`, they can be synced to cloud storage:
- Syncthing (recommended for continuous sync)
- Restic (for encrypted cloud backups)
- rclone (for various cloud providers)

## Restore Procedure

### Full Restore

```bash
# 1. Extract backup
tar -xzf $SYNC/backup/YYYY-MM-DD_HH-MM-SS.tar.gz -C $SYNC/backup/

# 2. Run restore script
restore

# 3. Reboot or re-login for changes to take effect
```

### Selective Restore

```bash
# Restore specific directory
tar -xzf $SYNC/backup/backup.tar.gz -C $HOME backup/ssh-keys
cp -r $SYNC/backup/backup/ssh-keys/* $HOME/.ssh/

# Restore specific file
tar -xzf $SYNC/backup/backup.tar.gz -C /tmp backup/claude.json
cp /tmp/backup/claude.json $HOME/.claude.json
```

## Best Practices

1. **Regular Backups**: Run `backup` before major system changes
2. **Test Restores**: Periodically verify backups can be restored
3. **Multiple Locations**: Keep backups in multiple locations (local + external/cloud)
4. **Encryption**: Use Borg or encrypted cloud storage for sensitive data
5. **Version Control**: Keep multiple backup versions (automated with Borg)
6. **Documentation**: Update this file when adding new backup items

## Security Considerations

- Backup files contain **sensitive credentials** (SSH keys, AWS creds, passwords)
- Ensure `$SYNC/backup/` has appropriate permissions (`700` recommended)
- Use encrypted storage for backups (Borg with encryption, encrypted drives)
- Do not commit backup archives to version control
- Regularly rotate and test backup encryption keys

## Troubleshooting

### Backup Fails
```bash
# Check BACKUP_DIR is set
echo $BACKUP_DIR

# Verify write permissions
mkdir -p $BACKUP_DIR/test && rmdir $BACKUP_DIR/test

# Check disk space
df -h $SYNC
```

### Restore Issues
```bash
# Check backup integrity
tar -tzf $SYNC/backup/backup.tar.gz | head

# View original permissions
tar -xzf backup.tar.gz backup/permission_log.txt -O | less

# Restore with verbose output
bash -x $(which restore)
```

### Missing Files
If a file/directory doesn't exist, backup script skips it with a warning:
```
Warning: /path/to/file does not exist and was skipped
```

## Adding New Backup Items

To add new files/directories to backup:

1. Edit `$DOTFILES/bin/backup`:
```bash
# Add to backup script (around line 43-60)
backup_item "$HOME/.new-config" "$BACKUP_FOLDER/new-config" "644" "755"
```

2. Edit `$DOTFILES/bin/restore`:
```bash
# Add to restore script (around line 43-64)
restore_dir "$BACKUP_DIR/new-config" "$HOME/.new-config"
```

3. Update this documentation

## Related Scripts

- `backup` - Main backup script (`$DOTFILES/bin/backup:2371`)
- `restore` - Restoration script (`$DOTFILES/bin/restore:1108`)
- `backup-borg` - Borg backup script (`$DOTFILES/bin/backup-borg:599`)

## See Also

- [Borg Backup Documentation](https://borgbackup.readthedocs.io/)
- [Restic Documentation](https://restic.readthedocs.io/)
- [Syncthing Documentation](https://docs.syncthing.net/)
