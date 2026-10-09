# Backup and restore

`bin/backup` creates an encrypted snapshot of selected machine state; it is **not** a backup of the entire home directory. Set `BACKUP_DIR` (normally exported by `config/zsh/.zshenv` to `$ARCHIVE/backups/backup`) and ensure `age`, `sudo` and `pacman` are available. `bin/backup-borg` separately archives the whole `$SYNC` directory to an external drive.

## Create a snapshot

```bash
backup
ls -lh "$BACKUP_DIR"/*.tar.gz.age
```

The script stages outside the synced tree and writes `<timestamp>.tar.gz.age` encrypted to `BACKUP_RECIPIENTS` (default: `$DOTFILES/secrets/recipients.txt`). **Keep the recipient identities available independently of the backup.** A failed run can leave a `.partial` file; only a completed `.age` file is a backup. Older plaintext `.tar.gz` archives may contain credentials and should be treated as sensitive.

Each archive contains a single `<timestamp>/` directory with these entries (missing optional sources are skipped):

| Archive entry | Source |
| --- | --- |
| `bluetooth`, `network-connections` | `/var/lib/bluetooth`, `/etc/NetworkManager/system-connections` |
| `ssh-keys`, `gnupg` | `~/.ssh`, `~/.gnupg` |
| `firefox-data`, `thunderbird-data` | `~/.mozilla/firefox`, `~/.thunderbird` |
| `tmuxp-sessions`, `zhistory` | `$XDG_CONFIG_HOME/tmuxp`, `$ZDOTDIR/.zhistory` |
| `age-keys`, `age-keys-alt`, `sops-age-keys` | `~/.config/age`, `~/.age`, `~/.config/sops/age` |
| `atuin-key`, `syncthing-key`, `pritunl-profiles` | Atuin key, Syncthing identity key, Pritunl profiles |
| `fstab`, `hostname`, `hosts`, `systemd-services` | Selected `/etc` files and `/etc/systemd/system` |
| `crontab`, `pkglist.txt`, `aurlist.txt`, `permission_log.txt` | User crontab, pacman lists, saved archive permissions |

This does **not** include cloud CLI credentials, container credentials, password stores, the dotfiles `local/` overlay or arbitrary development directories. Verify each critical source is backed up separately.

## Restore

```bash
# Newest .tar.gz or .tar.gz.age in BACKUP_DIR
restore
# Explicit archive (BACKUP_DIR is not needed for this form)
restore "$BACKUP_DIR/2026-10-06_09-56-50.tar.gz.age"
```

`restore` extracts the timestamped directory into a temporary directory, then copies supported items to their destinations. For encrypted archives it uses `BACKUP_IDENTITY` (default: `$DOTFILES/secrets/yubikey-identity.txt`); a hardware key may require a touch. Old plaintext `.tar.gz` archives are also accepted. The command uses `sudo` for Bluetooth and NetworkManager and may overwrite existing credentials. Inspect the archive and back up the destination first; run only on a trusted machine.

Restore covers the user entries above and the two system directories, plus a nonempty crontab. **It does not automatically restore** `fstab` (UUIDs may differ), `hostname`, `hosts`, `systemd-services`, package lists or `permission_log.txt`; review these by hand. It writes `zhistory` to `${ZDOTDIR:-$HOME}/.zhistory`. Re-login or reboot where required.

For a selective restore, extract to a private temporary directory and use the archive's actual timestamped path, not a `backup/` prefix:

```bash
work=$(mktemp -d)
chmod 700 "$work"
# For encrypted archives (set BACKUP_IDENTITY to your own identity if necessary):
age -d -i "${BACKUP_IDENTITY:-$DOTFILES/secrets/yubikey-identity.txt}" \
  "$BACKUP_DIR/2026-10-06_09-56-50.tar.gz.age" | tar -xz -C "$work"
# Inspect first, then copy a selected item from "$work/<timestamp>/".
# For old plaintext archives instead: tar -xzf archive.tar.gz -C "$work"
# When finished, remove the temporary decrypted copy securely per local policy.
```

## Borg (separate full sync backup)

`bin/backup-borg` backs up `$SYNC` to `$BORG_BACKUP_DRIVE/borg-repo` (default drive: `/run/media/$USER/backup-drive`). Set `BORG_BACKUP_DEVICE` if the drive must be mounted; the script mounts it at `$BORG_BACKUP_DRIVE` and initializes a repokey-encrypted repo there if absent. Keep the Borg passphrase and recovery key separately. Check available archives with `borg list "$BORG_BACKUP_DRIVE/borg-repo"`. This is independent of the encrypted snapshots above.

No backup timer is tracked here; schedule and test backups explicitly. Test a restore in a disposable environment before depending on it. Never commit archives or decrypted extracts.
