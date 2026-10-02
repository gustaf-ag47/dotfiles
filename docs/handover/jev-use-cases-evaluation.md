# Brief — Best Jev use cases: skeptical evaluation and ROI

## Context
User asks: "Delegate sub-agents to find the best JEV use-cases for pi". Parent tmux 3:jev-pilot, /home/gustaf/sync/src/dotfiles. Research only, not permission to implement. Existing integration docs/jev-pi.md and config/pi/lib/jev.mjs are observation-only. Read prior docs/research/jev-*.md and relevant tests. Parent has an untracked docs/handover/implement-jev-ultrafast-skill.md you may read, not implement.

## Job
1. Independently select promising Jev uses in this Pi setup, with special attention to whether an added inference call truly beats deterministic rules or existing model behavior.
2. Rank candidates by expected net latency/cost/user-value, failure risks and ability to measure success. State assumptions instead of invented benchmarks.
3. Design a small offline/synthetic benchmark and shadow-mode pilot for the top three, with representative examples, baseline, abstention/fallback, privacy constraints, measurable promotion/stop gates. Provide a compact example dataset in the report, not executable implementation.
4. Recommend what to try first and what not to build. Cite actual repository evidence.

## Scope and constraints
Own only docs/research/jev-use-cases-evaluation.md and this brief in isolated branch research/jev-use-cases-evaluation. Siblings workflows/capabilities own their correspondingly named branches/reports; do not touch them or production code/config. Shared parent checkout/environments are read-only. Read applicable AGENTS.md/CLAUDE.md. Read installed Pi README and relevant docs completely and follow related .md references before Pi-specific conclusions: /home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/. No live/paid Jev calls, secret reads, deployments or package installs. Scratch: $HOME/.cache/jev-use-cases/evaluation, never /tmp. Verification: git diff --check and check cited code/API references; runtime tests not applicable to this docs-only task. GIT_EDITOR=true for git continuation. Parent owns merges. Commit only owned docs locally, no push/merge.

## Done / budget
Write concise actionable report, commit, report path/commit and uncertainties to parent. Aim for 15 minutes. If blocked, document partial evidence and blocker rather than making up results.
