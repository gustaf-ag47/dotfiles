# Brief — Audit docs/ for outdated, broken and redundant documentation

**Agent:** delegated pi sub-agent, model `anthropic/claude-opus-5-5`, own worktree.
**Parent:** the operator's main pi session. **Date:** 2026-10-03.

## Context

Dotfiles repo, HEAD `bfb4c31` on master. Commit `bfb4c31` deleted `docs/handover/`
(54 files), `docs/wayfinder/`, `ralph/llm-utilization/`, `bin/waybar-claude-usage`
and `docs/research/jev-test.mjs`. Remaining docs were written across many work
sessions and likely contain stale claims, broken links to the deleted files, and
duplication.

This is an **investigation-first audit**. You produce a report; you do NOT rewrite
docs (fixing a broken link is still a change — propose, don't apply).

## Your job

1. **Broken links/references:** every reference in `docs/**`, `README.md`,
   `CLAUDE.md`, `config/nvim/MODULAR_APPROACH.md` to a path that no longer exists
   (especially `docs/handover/*`, `docs/wayfinder/*`, `ralph/*`). Done = complete
   list with file:line.
2. **Stale claims:** statements contradicted by current code/config. Spot-check the
   high-traffic docs hard: `CLAUDE.md` (root), `docs/README.md`,
   `docs/KEYBINDINGS.md` (vs actual keybinding configs — sample 15 bindings),
   `docs/GIT_WORKFLOW.md` (vs `bin/git-*` and hooks), `docs/BACKUP.md`,
   `docs/SECURITY.md` (vs `config/git/hooks/pre-commit` — note the hook recently
   gained an `|| true` fix for all-deletion commits), `docs/LINTING.md` (vs
   `Dockerfile.linters`, `Makefile`, `.github/workflows/*`). Done = list of claim →
   reality with evidence.
3. **Redundancy:** docs that substantially duplicate each other or that exist only as
   historical session notes with no forward value (e.g. convergence/incident notes:
   `docs/dotfiles-convergence-2026-10-03.md`, `docs/nvim-lock-convergence.md`,
   `docs/nvim-memory-leak.md`, `docs/llm-utilization-host-verification.md` — assess
   each: keep as living doc, fold into another doc, or archive/delete). Done = per-doc
   verdict table for ALL files in `docs/` (top level) and `docs/research/`.
4. **docs/research/ pruning:** these are research notes from past work. For each,
   verdict: still-referenced/load-bearing (something in code or living docs points at
   it), historical-but-harmless, or safe-to-delete. Done = table.
5. Write the report to `docs/research/audit-2026-10-docs.md`, commit on your branch.
   Structure: Broken references → Stale claims → Per-doc verdict table → Top-10
   recommended actions ranked by value/risk.

## Scope fence

- **You own:** `docs/research/audit-2026-10-docs.md` (new file) — the ONLY file you
  may create/commit.
- **Do NOT touch:** everything else, including the docs you audit.
- Siblings in parallel: bin/scripts auditor (`audit-2026-10-bin-scripts.md`), config
  auditor (`audit-2026-10-config.md`), tests/CI auditor
  (`audit-2026-10-tests-ci.md`). Do not deep-audit code; that is theirs. Checking a
  doc claim against code is fine.

## Constraints

- Evidence = `rg` output / file reads. For every "stale" verdict, quote the claim and
  the contradicting source.
- You change no files other than your report. No installers, no service restarts.
- Commit message: `docs(audit): docs audit 2026-10`.
- At ~80% context: commit what you have with a "Remaining" section and report.

## Report back

One line to the parent when done:
`audit-docs: DONE <sha> - docs/research/audit-2026-10-docs.md`
