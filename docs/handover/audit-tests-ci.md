# Brief — Audit tests, CI, Makefile and Docker for gaps, dead weight and drift

**Agent:** delegated pi sub-agent, model `anthropic/claude-opus-5-5`, own worktree.
**Parent:** the operator's main pi session. **Date:** 2026-10-03.

## Context

Dotfiles repo, HEAD `bfb4c31` on master. Recent cleanup removed completed work
artifacts. The operator wants the test/CI/build surface audited for loose ends:
dead tests, redundant infra, drift between what CI gates and what docs/hooks claim,
and untested load-bearing code.

Surface: `tests/` (unit: ~30 python/mjs files; e2e; shell test scripts at
`tests/*.sh`), `.github/workflows/` (dotfiles.yml, nvim.yml), `Makefile`,
`Dockerfile`, `Dockerfile.linters`, `docker-compose.linters.yml`,
`config/git/hooks/` (pre-commit, commit-msg), `scripts/test.sh`.

This is an **investigation-first audit**. Report only; change nothing.

Known context (not findings):
- `make test-unit` currently passes: 344 tests, 1 skipped.
- The pre-commit hook was just fixed for all-deletion commits (`|| true` on the
  added_lines grep) — already done, not a finding.

## Your job

1. **Dead/orphan tests:** tests whose subject no longer exists or that can never run
   in CI (check which test files `make test-unit` actually discovers vs what exists
   on disk — name any test file NOT picked up by the runner). Done = list with
   evidence of discovery mechanism.
2. **CI vs local drift:** what `.github/workflows/*` gates vs what `Makefile`/hooks
   run locally vs what docs claim (`docs/LINTING.md`). Mismatches = findings. Also:
   does CI exercise the mjs tests? The e2e tests? If not, say so explicitly. Done =
   drift matrix (gate × where it runs).
3. **Redundant build infra:** `Dockerfile` vs `Dockerfile.linters` vs
   `docker-compose.linters.yml` — what is actually used by Makefile/CI/hooks, what is
   vestigial. Done = verdict per file.
4. **Coverage holes in load-bearing code:** which of the critical scripts
   (`bin/claude-token-proxy`, `scripts/llm_usage.py`, `scripts/install.sh`,
   `scripts/pi_setup.py`, `bin/llm-wait`, `bin/llm-schedule`,
   `config/pi/extensions/*.ts`, `config/pi/lib/*.mjs`) have no test touching core
   behaviours. Do not demand 100% coverage; name the 5 most valuable missing tests.
5. **Test hygiene:** fixtures/left-behind artifacts, tests that hit the network or
   live services without guards, slow tests, duplicated fixture code worth one
   shared helper. Done = list.
6. Write the report to `docs/research/audit-2026-10-tests-ci.md`, commit on your
   branch. Structure: Dead tests → Drift matrix → Build infra verdicts → Top-5
   missing tests → Hygiene → Top-10 recommended actions ranked by value/risk.

## Scope fence

- **You own:** `docs/research/audit-2026-10-tests-ci.md` (new file) — the ONLY file
  you may create/commit.
- **Do NOT touch:** everything else.
- Siblings in parallel: bin/scripts auditor (`audit-2026-10-bin-scripts.md`), config
  auditor (`audit-2026-10-config.md`), docs auditor (`audit-2026-10-docs.md`).

## Constraints

- Read `CLAUDE.md` at repo root and `tests/README.md` first.
- Verification gate — actually run the suite once so your claims about discovery are
  grounded:
  ```bash
  make test-unit 2>&1 | tail -3
  ```
  Confirm the count; do not run `make test` (needs docker compose services) or
  `make install`.
- Evidence = command output. You change no code.
- Commit message: `docs(audit): tests and ci audit 2026-10`.
- At ~80% context: commit what you have with a "Remaining" section and report.

## Report back

One line to the parent when done:
`audit-tests-ci: DONE <sha> - docs/research/audit-2026-10-tests-ci.md`
