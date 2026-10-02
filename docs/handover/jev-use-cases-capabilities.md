# Brief — Best Jev use cases: capabilities and limits

## Context
User asks: "Delegate sub-agents to find the best JEV use-cases for pi". Parent tmux 3:jev-pilot in /home/gustaf/sync/src/dotfiles. Research only. Start with docs/jev-pi.md, docs/research/jev-pi-routing.md, docs/research/jev-ten-levels-review.md and docs/research/jev-helper-implementation.md. Current integration is an observation-only classifier; do not assume Jev is a general coding agent.

## Job
1. Verify Jev/TypeSafe capabilities against current primary documentation using web-research/research skills, and reconcile with the existing research and actual integration config/pi/lib/jev.mjs.
2. Identify 5–8 Pi use cases suited to its actual structured-output, latency, context, pricing and reliability properties. Separate verified facts, vendor claims and hypotheses; cite URLs and repository paths. Do not fabricate timing results.
3. Rank top three, identify poor fits, and state privacy/security and failure boundaries. Explain when a deterministic rule or normal Pi model is preferable.

## Scope and constraints
Own only docs/research/jev-use-cases-capabilities.md and this brief in isolated branch research/jev-use-cases-capabilities. Siblings workflows and evaluation own their correspondingly named reports/branches; do not modify those or production code/config. Shared parent checkout/environments read-only. Read applicable AGENTS.md/CLAUDE.md. Read installed Pi README and relevant Pi docs completely, following related .md references before Pi-specific conclusions: /home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/. Do not invoke paid APIs/live Jev, inspect secrets, deploy or install packages. Scratch: $HOME/.cache/jev-use-cases/capabilities, never /tmp. Verification: git diff --check; check sources and cited APIs. Runtime tests not applicable to documentation-only task. GIT_EDITOR=true for continuations. Parent owns merging. Commit owned docs locally, no push or merge.

## Done / budget
Produce concise sourced report and local commit; report path, commit and unknowns to parent. Aim for 15 minutes with a bounded primary-source search. If blocked, preserve partial findings and clearly name missing evidence.
