# Hermes Agent (skrubben)

Hermes runs from `~/.hermes` (HERMES_HOME). Its files are split three ways:

| What | Where | Why |
|---|---|---|
| `SOUL.md` | `config/hermes/SOUL.md` (this repo, public) | Generic persona, no private data |
| `config.yaml` | `local/config/hermes/config.yaml` (= `$SYNC/dotfiles-local`, private) | Contains Discord IDs and per-channel business prompts |
| memories, skills, handovers, scripts, assets, sessions | `$SYNC/hermes/<dir>`, bind-mounted onto `~/.hermes/<dir>` | Durable state, Syncthing + restic |
| live SQLite DBs, secrets | stay in `~/.hermes`; hourly `hermes-state-snapshot` (:50) copies them to `$SYNC/hermes/snapshot` and `local/config/hermes/secrets` | Syncthing ignores `*.db-wal`, so live DBs can't be synced safely |

`config.yaml` and `SOUL.md` are symlinks (Hermes' atomic writes resolve symlinks, so they survive `hermes config set`).
Directories are **bind mounts, not symlinks**: Hermes compares resolved skill paths against its unresolved skills root, which breaks with a symlinked `skills/`.

fstab (one line per dir, `<d>` in memories skills handovers scripts assets sessions):

```
/mnt/my_encrypted_nvme/sync/hermes/<d> /home/gud1/.hermes/<d> none bind,nofail,x-systemd.requires-mounts-for=/mnt/my_encrypted_nvme,x-systemd.wanted-by=mnt-my_encrypted_nvme.mount 0 0
```

The empty mountpoint dirs under `~/.hermes` are `chattr +i`, and the gateway drop-in
`config/systemd/user/hermes-gateway.service.d/10-state-mounts.conf` refuses to start without the mounts.

Only skrubben runs the Hermes gateway. The laptop receives `$SYNC/hermes` but must not run a gateway against it
(same Discord bot, cron jobs would fire twice).

Restore DBs/secrets: stop `hermes-gateway`, copy from `$SYNC/hermes/snapshot/db` and `local/config/hermes/secrets` back into `~/.hermes`, start it.
