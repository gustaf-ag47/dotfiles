# Fleet design: apps per machine, work/private split, sign-in, secrets

Design record (2026-10-06) for four questions raised while preparing the
Dell XPS 14 (`xps14`). Machine facts are from arch and skrubben on that date.
Builds on `machine-profiles-and-xps14.md`.

## 1. Apps per machine: done

`PROFILE_ROLES` in `profiles/<host>.env` selects roles; each role
(`system/roles/<role>/`) holds `packages`, `packages.aur` and `user-services`.
See `system/README.md`. Review a machine before installing it:

```bash
scripts/install-system.sh --profile xps14 --list
```

The roles were built from the union of what arch and skrubben run (384
explicit packages), sorted into `base`, `desktop`, `xorg`, `dev`, `work`,
`personal`, `latex`. `--undeclared` lists what a live machine has but no role
declares. `install-arch`'s `apps.csv` is now only the bootstrap set.

## 2. Separating work and private

### What exists today

| Plane | Today | Boundary? |
|---|---|---|
| Packages, user services | `work` / `personal` roles | **yes** (new) |
| Code | Company repos in `src/<company>/` are ignored by Syncthing and live on company remotes; `git-bundle-backup` never bundles them | yes |
| Private overlay (`dotfiles-local`) | One tree: work items (prod-DB units, company skills: `linear`, `betterstack-logs`, prod/sandbox DB skills) next to personal ones (InStockachu, TCG, co-browse) | no |
| Files (Syncthing) | **One folder, `sync`, 472 GB**, shared by arch and skrubben: Photos 188 G, `.stversions` 78 G, `src` 48 G, Vault 42 G, `library` 40 G, `archive` 34 G, ~980 book-author dirs at the top level, `Professional/` 0.7 G | no |

### Options for the file plane

**A. Per-device ignores (recommended first step).** Syncthing's `.stignore`
is *not* synced: each device may ignore different subtrees. Keep the patterns
in synced files (`$SYNC/.stignore.d/<role>.txt`) and generate each machine's
`.stignore` from its profile (`#include .stignore.d/media.txt`, ...). Cheap,
reversible, no data moves.
- A new device must have its `.stignore` *before* the folder is accepted,
  or it starts downloading all 472 GB. `bootstrap-sync.sh` would write it
  first.
- Ignored paths are simply absent on that device. This works for size, but
  it is not a security boundary: the device still holds the folder's key and
  could un-ignore.

**B. Split into several Syncthing folders (the real boundary).** For example:
`sync-core` (dotfiles-local, Vault, src, Inbox), `sync-media` (Photos,
library, books), `sync-work` (Professional, work notes, work overlay). A
device only receives the folders shared with it, so a company-owned machine
would never hold personal data.
- Costs: moving data; `$SYNC/...` paths in scripts change; re-sharing on
  every device; `.stversions` per folder.

**Prerequisite for either:** move the ~980 book-author directories at the top
of `$SYNC` into `library/` (or `Calibre Library/`). Today "everything except
media" cannot be written as a short pattern list.

### Private overlay

Split `dotfiles-local` the same way as roles:
`dotfiles-local/{common,work,personal}/...`. `install.sh` and `pi-setup` would
then apply only the parts named in `PROFILE_ROLES`. With option B, `work/`
lives in `sync-work` and never reaches a machine without the `work` role.

## 3. Signing in to the machines

Facts:
- Tailscale runs everywhere, but Tailscale SSH is off (`RunSSH: false`).
- arch has `--accept-routes` **off**, so LAN B (pve, pfSense) is reachable
  only by jumping through skrubben.
- `~/.ssh/config` holds only GitHub aliases.
- The same `id_ed25519` is on both machines and in the bootstrap kit.

Proposal, from least to most change:
1. `tailscale set --accept-routes` on the laptops: direct reach to LAN B.
   This is a one-time change per machine; it can go in the `base` role's
   install step.
2. A tracked SSH client config with aliases for every machine on MagicDNS
   names, plus `ProxyJump skrubben` fallbacks for LAN B. Hostnames and LAN
   IPs go in the private overlay, because this repo is public.
3. `authorized_keys` managed from a list of public keys (safe to commit).
   Then a new machine accepts the others on first boot.
4. Optional **Tailscale SSH** for machine-to-machine: tailnet identity +
   ACLs, no keys to distribute, optional periodic re-auth ("check mode").
   SSH keys stay as the fallback.

If "sign in" means *app* logins (gh, Claude, Gemini, Supabase, MCP, Discord):
long-lived tokens can be rendered from the secrets store at install (next
section). OAuth logins that tie to a browser session still need one
interactive login per machine.

## 4. Secrets management

### Today: five mechanisms

| Mechanism | Holds |
|---|---|
| Bootstrap kit (age, 2 YubiKeys + paper key) | SSH keys, GnuPG, `cctoken`, age identities |
| 4 separate age identities | SOPS for the InStockachu repos (`age1ystj…`, `age1g6g9…`), tcgtrader, one only on arch (`age17pau…`) |
| `pass` (GnuPG, 6 entries, in `$SYNC/.password-store`) | a few passwords |
| Plaintext files | `~/.config/discord-bot-token`, `claude-discord-webhook`, `gh/hosts.yml`, `~/.supabase/access-token`, `~/.mcp-auth/*`, `~/.env`, ... |
| bitwarden-cli (installed) | human passwords, presumably |

Also: `src/iac/.sops.yaml` encrypts to `age1vxav4j…`, which is on **neither**
machine. Either it only exists in a cluster, or it is lost.

### Proposal: one root, two stores

- **Root of trust: the YubiKeys** (already the kit's). Everything else can be
  re-derived from them plus the paper key.
- **Machine identities:** each machine generates its own age key at install.
  The YubiKey re-encrypts to add it as a recipient; removing a lost machine
  means removing its recipient and re-encrypting. This replaces copying the
  same keys everywhere.
- **Machine and config secrets → SOPS + age**, one file per domain
  (`secrets/personal.yaml`, `secrets/work.yaml`) in the private overlay. Work
  secrets are encrypted only to machines with the `work` role. A
  `secrets-render` step at install writes the token files above (0600), so
  "logging in" a new machine to gh/Discord/Supabase/webhooks is automatic.
- **Human passwords → one password manager** (Bitwarden, already installed),
  instead of also keeping `pass`.
- The four existing identities stay until their SOPS files are re-encrypted
  to the new recipients. Then they retire.

Why not a hosted vault (1Password/Bitwarden Secrets Manager/Vault): they need
network access and an account during bootstrap. SOPS + age works offline and
reuses the YubiKeys you already enrolled.

## Decisions needed

1. File plane: per-device ignores now (A), the folder split (B), or A then B?
   Which subtrees should the XPS 14 not receive (Photos? library? archive?)?
2. Split `dotfiles-local` into `common/work/personal`?
3. Sign-in: Tailscale SSH yes/no; enable `--accept-routes` on the laptops?
4. Secrets: adopt SOPS-per-domain + per-machine age keys; retire `pass` in
   favour of Bitwarden?
5. The `iac` SOPS key (`age1vxav4j…`): find it, or re-key that repo.
