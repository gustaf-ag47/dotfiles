# Brief — Audit bin/ and scripts/ for dead code, redundancy and bloat

**Agent:** delegated pi sub-agent, model `anthropic/claude-opus-5-5`, own worktree.
**Parent:** the operator's main pi session. **Date:** 2026-10-03.

## Context

This dotfiles repo (HEAD `bfb4c31` on master) just had a cleanup pass that removed
completed work artifacts (docs/handover briefs, a Ralph loop scaffold, an obsolete
waybar widget `bin/waybar-claude-usage`, `docs/wayfinder/`). The operator now wants a
deeper audit: loose ends, redundant code, over-commenting, bloat, dead references.

This is an **investigation-first audit**. You produce a report; you do NOT refactor
code. Small, provably-safe deletions may be proposed as a patch in the report, not
applied.

Known-deliberate things that are NOT findings (do not report these):
- `bin/claude-usage` is a compat shim for `bin/llm-usage` — intentional.
- `bin/idle-manager` is a documented fallback (see CLAUDE.md) — intentional.
- `bin/claude-token-proxy` deliberately duplicates provider adapters from
  `scripts/llm_usage.py` to stay stdlib-only and single-file (documented in-file).
- Personal utilities with no in-repo references (`aocli`, `bwf`, `process_inbox`,
  `work-context`, `kubectx`, `kubens`, `pve-spice`, `switch-display-manager`) are
  used interactively from PATH; absence of references is not evidence of death.

## Your job

1. **Dead/stale code in `bin/` and `scripts/`:** for each script, determine whether it
   is (a) referenced by config/systemd/keybindings/installer/tests, (b) a plausible
   interactive tool, or (c) genuinely orphaned/superseded. Done = a table covering
   every file in `bin/` and `scripts/` with a verdict and evidence (grep hits).
2. **Internal redundancy:** duplicated logic between scripts (e.g. multiple tmux
   save/restore helpers, multiple backup scripts `backup` vs `backup-borg`,
   `capture` vs `screenshot`, battery/waybar helpers). Done = list of overlaps with a
   keep/merge/drop recommendation each.
3. **Comment and header bloat:** scripts where comments restate the code, or carry
   stale dates/claims that no longer match behaviour. Done = file+line examples, worst
   offenders only (top 10), not an exhaustive nitpick list.
4. **Loose ends:** TODO/FIXME/XXX markers, references to paths that no longer exist
   (especially `docs/handover/*`, `docs/wayfinder/*`, `ralph/*`,
   `bin/waybar-claude-usage`), env vars read but never set anywhere, flags documented
   but not implemented. Done = list with file:line.
5. Write the report to `docs/research/audit-2026-10-bin-scripts.md` and commit it on
   your branch. Structure: Verdict table → Redundancies → Bloat → Loose ends →
   Top-10 recommended actions ranked by value/risk.

## Scope fence

- **You own:** `docs/research/audit-2026-10-bin-scripts.md` (new file) — the ONLY file
  you may create/commit.
- **Do NOT touch:** everything else. Do not edit `bin/`, `scripts/`, other docs.
- Sibling agents running in parallel: config auditor (owns
  `docs/research/audit-2026-10-config.md`), docs auditor (owns
  `docs/research/audit-2026-10-docs.md`), tests/CI auditor (owns
  `docs/research/audit-2026-10-tests-ci.md`). Stay out of their report files and do
  not duplicate their areas in depth (one-line cross-references are fine).

## Constraints

- Read `CLAUDE.md` at repo root first.
- Read-only with respect to code. Evidence = `rg` output, not intuition.
- Verification gate before committing your report:
  ```bash
  bash -n $(git ls-files 'bin/*' 'scripts/*.sh' | head -100) 2>&1 | tail -1  # sanity only
  ```
  (You change no code, so no test suite is required; do NOT run `make install`.)
- Commit message: `docs(audit): bin and scripts audit 2026-10`.
- Budget: this is a bounded audit; if you reach ~80% context, commit what you have
  with a "Remaining" section and report.

## Report back

One line to the parent when done:
`audit-bin-scripts: DONE <sha> - docs/research/audit-2026-10-bin-scripts.md`
