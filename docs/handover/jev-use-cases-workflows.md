# Brief — Best Jev use cases: Pi workflows

## Context
User asks: "Delegate sub-agents to find the best JEV use-cases for pi". Parent tmux 3:jev-pilot, checkout /home/gustaf/sync/src/dotfiles. This is research, not implementation. Existing evidence: docs/jev-pi.md, docs/research/jev-pi-routing.md, docs/research/jev-ten-levels-review.md, config/pi/extensions/jev.ts, config/pi/lib/jev.mjs. Parent also has an untracked docs/handover/implement-jev-ultrafast-skill.md you may READ for context; it is not authorization to implement.

## Job
1. Inspect actual Pi workflows/extensions/skills in this repo and identify concrete high-value Jev uses beyond generic model routing.
2. Rank 5–8 cases by user value, frequency, latency sensitivity, integration effort and failure consequences. Include concrete input/output examples, abstention/fallback behavior, and whether deterministic logic would be better.
3. Recommend top three and explicitly reject weak uses. Cite code paths and distinguish evidence from hypotheses. Note current observation-only boundary.

## Scope and constraints
Own only docs/research/jev-use-cases-workflows.md and this brief in your isolated branch. Siblings investigate capabilities (research/jev-use-cases-capabilities) and evaluation (research/jev-use-cases-evaluation); do not touch their outputs or production code/config. Shared parent checkout and environments are read-only; report fixes, do not apply them. Read applicable AGENTS.md/CLAUDE.md. Before Pi-specific conclusions read installed Pi README and relevant docs completely, following related .md references: /home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/. Use available research skills if useful. No live Jev calls, secret reads, deployments or package installs. Scratch: $HOME/.cache/jev-use-cases/workflows (not /tmp). No need for runtime tests for a documentation-only investigation; verification: git diff --check, and confirm each cited file/API exists. Use GIT_EDITOR=true for any git continuation. Parent owns merges. Commit only your owned docs locally; do not push or merge.

## Done / budget
Write a concise evidence-backed report, commit it, and report commit/path plus limitations to parent. Aim for 15 minutes; avoid exhaustive browsing. If blocked, record partial findings and blocker rather than invent evidence.
