# Brief — Audit config/ for dead config, stale references and bloat

**Agent:** delegated pi sub-agent, model `anthropic/claude-opus-5-5`, own worktree.
**Parent:** the operator's main pi session. **Date:** 2026-10-03.

## Context

Dotfiles repo, HEAD `bfb4c31` on master. A recent cleanup removed completed work
artifacts (docs/handover/, docs/wayfinder/, ralph/, `bin/waybar-claude-usage`). The
operator wants an audit of `config/` for loose ends: dead config, references to
removed things, redundancy, over-commenting, bloat.

This is an **investigation-first audit**. You produce a report; you do NOT change
config. Proposals go in the report.

Layout: `config/` holds zsh, nvim, tmux, git, gui/{Wayland,Xorg}, lf, yazi, pi
(extensions/skills/lib), llm-proxy, systemd units, applications, and more. The repo
is installed by symlinking (see `scripts/install.sh`); `config/pi/` resources are
installed by `scripts/pi_setup.py`.

Known-deliberate (NOT findings):
- Dual desktop support (Hyprland AND i3) is intentional.
- `config/pi/` comments referencing deleted `docs/handover/*.md` briefs are
  historical pointers; flag them only in one consolidated list, low priority.
- `local/` is gitignored private config — out of scope.

## Your job

1. **Dead references:** config entries pointing at scripts/files that do not exist in
   the repo or in `bin/` (keybindings launching missing binaries, systemd units with
   missing ExecStart targets, zsh aliases to removed tools, nvim modules requiring
   missing lua files, waybar/hypr references). Done = list with file:line + what is
   missing.
2. **Redundancy/drift between the two desktops:** settings duplicated between
   Wayland and Xorg stacks that have drifted apart where they claim to mirror each
   other (e.g. keybinding parity claims vs reality — cross-check
   `docs/KEYBINDINGS.md` claims only where config itself asserts parity). Done =
   drift list.
3. **Stale/orphaned config files:** configs for apps that nothing installs or
   references anymore; `.example` templates whose real counterpart convention died;
   pi extensions/skills that are no longer loaded by `scripts/pi_setup.py`'s
   allowlist or superseded. Done = orphan list with evidence.
4. **Bloat and over-commenting:** top-10 worst files where comments restate code or
   carry stale dated claims contradicted by current behaviour.
5. **Loose ends:** TODO/FIXME markers, commented-out blocks that should die,
   env vars referenced but defined nowhere (check `config/zsh/.zshenv` and
   `profiles/*.env` before claiming undefined).
6. Write the report to `docs/research/audit-2026-10-config.md`, commit on your
   branch. Structure: Dead references → Drift → Orphans → Bloat → Loose ends →
   Top-10 recommended actions ranked by value/risk.

## Scope fence

- **You own:** `docs/research/audit-2026-10-config.md` (new file) — the ONLY file you
  may create/commit.
- **Do NOT touch:** everything else, including `config/` itself.
- Siblings in parallel: bin/scripts auditor (`audit-2026-10-bin-scripts.md`), docs
  auditor (`audit-2026-10-docs.md`), tests/CI auditor (`audit-2026-10-tests-ci.md`).
  Do not duplicate their areas in depth.

## Constraints

- Read `CLAUDE.md` at repo root first; also `config/nvim/MODULAR_APPROACH.md` for
  nvim intent before calling nvim structure wrong.
- Evidence = `rg`/`ls` output, not intuition. For "nothing references X", show the
  searches you ran.
- You change no code; run no installers; do NOT run `make install` or restart
  services.
- Commit message: `docs(audit): config audit 2026-10`.
- At ~80% context: commit what you have with a "Remaining" section and report.

## Report back

One line to the parent when done:
`audit-config: DONE <sha> - docs/research/audit-2026-10-config.md`
