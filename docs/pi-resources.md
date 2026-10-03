# Pi resource management

How pi configuration on a machine relates to this repo, after the 2026-10-03
audit and convergence (`fix/pi-config-drift`).

## One mechanism: `pi-setup`

`bin/pi-setup` (→ `scripts/pi_setup.py`) is the only supported way to provision
`~/.pi/agent` from this repo. `make install` runs `pi-setup --apply` when `pi`
is on PATH.

What it manages (file-level symlinks, reversible backups under
`$XDG_STATE_HOME/pi-dotfiles`):

| Source | Target | Notes |
|---|---|---|
| `config/pi/extensions/*` | `~/.pi/agent/extensions/` | every tracked extension, including those importing `../lib` |
| `config/pi/lib/*` | `~/.pi/agent/lib/` | shared `.mjs` modules the extensions import |
| `config/pi/bin/*` | `~/.pi/agent/bin/` | agent-side tools (e.g. `pi-scratch`) |
| `config/pi/skills/*` | `~/.pi/agent/skills/` | public skills |
| `$SYNC/dotfiles-local/config/pi/skills/*` | `~/.pi/agent/skills/` | private skills (company/personal infra) |
| `config/pi/{settings,models}.example.json` | `~/.pi/agent/{settings,models}.json` | **seed-only**: copied when missing, never overwritten — live drift from the examples afterwards is by design |
| pi-ai dependency | `config/pi/node_modules/…`, `~/.pi/agent/node_modules/…` | lets `.ts` extensions resolve imports |

Excluded on purpose: `auth.json`, `settings.json`/`models.json` once they
exist, sessions, locks, the delegate mailbox, `.venv`/`__pycache__`/`.bak`
inside skills, and anything else that is runtime state.

`pi-setup` (no flags) is the drift check: prints pending changes and verifies
the third-party skill clones. `--rollback <manifest>` undoes an apply.

### Retired: `pi-link-extensions`

Removed 2026-10-03. It linked an allowlist of extensions **without**
`config/pi/lib`, so any extension importing `../lib/*.mjs` (jev, jev-context,
grok-build) broke every new pi session once linked — pi refuses to start on an
extension load error. It also ignored tracked-but-unlisted extensions
(`anthropic-subscription.ts`), leaving hand-made unmanaged links. `pi-setup`
links extensions and their libs together, so the failure mode is structural
gone.

## Third-party skill collections

`~/.agents/skills/{mattpocock,pi-skills,vladikk-modularity}` are git clones
pinned in `config/pi/upstreams.json`. Fetch missing ones with
`pi-setup --fetch-upstreams`; existing checkouts are never touched.

## Private skills live in `local/`

Skills tied to personal machines or company infra belong in
`$SYNC/dotfiles-local/config/pi/skills/` (gitignored, synced across machines),
not in `~/.pi/agent/skills` directly. Adopted there 2026-10-03:
`laptop-cobrowse`, `neko-cobrowse`, `browse-shop`, `tcg-store-search` — the
last two had been deleted from this repo ("moved to project repo") while the
only real copies kept living, unmanaged and unbacked, in the live agent dir.

## Known opt-ins

- `config/pi/skills/jev-ultrafast` is provisioned like any other skill but
  requires its own `scripts/setup.sh` (pinned checkout + venv) before use; the
  SKILL.md gates execution.

## Runtime state inventory (never in git)

`~/.pi/agent/`: `auth.json` (+ keep no stale `.bak` copies — they hold
credentials), `models-store.json`, `trust.json`, `crashes.json`, `sessions/`,
`locks/`, `delegate-mailbox/`, `profiles/<ephemeral agent profiles — delete
after the event, they contain their own auth.json>`.
