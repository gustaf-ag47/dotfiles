# agent-git / agent-gh: guarded git and gh for Pi agents

Agents push with Gustaf's GitHub account. On 2026-10-03 an agent sweep
deleted a human colleague's branches; force pushes over others' work are the
other risk. `nix/agent-git/` builds patched `git` and a wrapped `gh` that
refuse the dangerous operations outright, and wires them onto `PATH` for Pi
agent sessions only — never for Gustaf's own interactive shells.

Inspiration: Geoffrey Huntley's demo
([repo](https://github.com/ghuntley/nix-demo),
[writeup](https://ghuntley.com/nix/)): patch git once in a Nix overlay, test
the refusal in a NixOS VM, use the same package everywhere. Patches 001/002
in `nix/agent-git/third_party/git/` are copied near-verbatim from that repo
(see its SPDX header); patch 003 extends the same technique to `--mirror`,
`--prune`, `--delete`/`-d` and `:ref` deletion refspecs, for this repo.

## What's refused

`agent-git` (`git push ...`) refuses, with a clear `fatal:` message instead
of silently proceeding:

- `--force` / `-f`
- `--force-with-lease[=...]`
- `+refspec` (command line, and `remote.<name>.push` config)
- `--mirror`
- `--prune`
- `--delete` / `-d`, and `:ref` deletion refspecs

Everything else — plain push, fetch, pull, rebase, `send-pack` without
`--force` — works exactly like stock git. `gitMinimal` (the git nixpkgs uses
internally to build half the world) is left unpatched so the overlay never
triggers unrelated rebuilds; only code that asks for `agent-git` gets the
patched binary.

`agent-gh` wraps the real `gh` and refuses:

- `gh repo delete`
- `gh api ... -X DELETE` against a repo-, ref- or branch-deletion endpoint
  (`DELETE /repos/{o}/{r}`, `.../git/refs/...`, `.../branches/{b}`)
- `gh pr close`, and `gh api .../pulls/{n} -X PATCH` with `state=closed`,
  **unless** the PR's author is the authenticated account. (Since agents
  push as Gustaf's account, "not an agent" in practice means a PR opened
  by a human collaborator under a different login — on write access
  granted to that account.) If the author can't be determined (API call
  fails, no network), the wrapper blocks by default.

Refusals print: `blocked for agents: ask Gustaf (via Hermes) — <reason>`.

**Allow-rule for branch deletion:** agents' own branches may disappear only
via GitHub's "automatically delete head branches" repo setting after merge
— never by an agent calling the delete API or `git push --delete` itself.

## Building and wiring it in

One-time per machine, after installing Nix (below):

```bash
scripts/agent-git-setup.sh   # nix build agent-git + agent-gh, record their paths
bin/pi-setup --apply         # link config/pi/bin/{git,gh} into the live agent bin dir
```

`config/pi/bin/git` and `config/pi/bin/gh` are small dispatcher scripts
(committed, not the Nix store paths themselves, since those are
machine/build-specific) that `exec` whatever `scripts/agent-git-setup.sh`
last built. `bin/pi-setup` is the existing narrow step that links
`config/pi/bin/*` into `~/.pi/agent/bin/`, which pi agent sessions put first
on `PATH` (see `scripts/pi_setup.py`). Gustaf's own zsh never has
`~/.pi/agent/bin` on `PATH`, so this never touches his shells. Re-run
`scripts/agent-git-setup.sh` after changing the patches or the `gh` wrapper;
`bin/pi-setup --apply` is idempotent and safe to run any time (it is the one
installer this repo's agents are allowed to run on their own, as documented
in `AGENTS.md`/`CLAUDE.md`).

Verifying a delegated Pi child resolves to the guarded binaries:

```bash
env PATH="$HOME/.pi/agent/bin:/usr/bin:/bin" bash -c 'git --version; git push --force 2>&1; gh api user --jq .login'
```

## Installing Nix (per machine)

```bash
sudo pacman -S --needed nix
echo "experimental-features = nix-command flakes" | sudo tee -a /etc/nix/nix.conf
sudo systemctl enable --now nix-daemon.service
sudo mkdir -p /nix/store && sudo chown root:nixbld /nix/store && sudo chmod 1775 /nix/store
```

The last line is a workaround seen on Arch: the `nix` package creates
`/nix/var` but not `/nix/store` itself; the daemon doesn't create it either.
Without it `nix build`/`nix eval` fail with `/nix/store: No such file or
directory`. Codified for skrubben in `system/hosts/skrubben/packages`
(`nix`), `system/hosts/skrubben/services` (`enable nix-daemon.service`) and
`system/hosts/skrubben/files/etc/nix/nix.conf`; apply via
`sudo scripts/install-system.sh --apply` (keeps the Arch package's own
`build-users-group` line so a pacman upgrade regenerating the file doesn't
silently drop flakes support — `install-system.sh --check` will flag it).

## Testing

```bash
cd nix/agent-git
nix flake check                      # evaluates overlay, packages and the VM test derivation
nix build .#agent-git .#agent-gh     # builds the two packages directly
nix build .#checks.x86_64-linux.no-force-push   # runs the NixOS VM test (needs /dev/kvm)
```

The VM test (`tests/no-force-push.nix`) asserts every refusal above against
a local bare repo, and that normal push/fetch/rebase still work. It needs
`/dev/kvm`; a GitHub Actions `ubuntu-latest` runner has it, this dev host
did not at the time of writing. On a host without KVM, use the manual smoke
test from "Verifying a delegated Pi child..." above plus:

```bash
cd nix/agent-git
nix build .#agent-git -o /tmp/g && /tmp/g/bin/git push --force 2>&1   # expect: fatal: force push is disabled...
nix build .#agent-gh -o /tmp/h && /tmp/h/bin/gh repo delete owner/repo --yes 2>&1  # expect: blocked for agents...
```

## Server-side rulesets (report, not applied blind)

See operator notes: agent-git-ruleset-proposal.md for which repos agents
push to and the proposed GitHub rulesets (block force-push + deletion on
default/release branches). Only `gustaf-ag47/*` repos get rulesets applied
directly; org repos owned by others are a proposal only.
