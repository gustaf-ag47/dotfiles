# Research Jev classification for Pi + dotfiles routing

## User request
"Delegate a sub-agent to research how we can use JEV with our current Pi setup in our $DOTFILES and routing with llm token proxy, llm usage, and all that"
Research only; parent is concurrently integrating Grok OAuth into the same stack with other agents. Do not disturb their files or live state.

## Context
Repo $DOTFILES=/home/gustaf/sync/src/dotfiles. Architecture: bin/claude-token-proxy is Anthropic OAuth credential pool plus quota/routing oracle (/_usage, /_route), NOT generic wire-format translator. config/pi/extensions/llm-failover.ts lets Pi switch native providers using oracle. scripts/llm_usage.py reports quota/freshness/forecast; config/llm-proxy/{routes,classes}.json encode routing policy/task classes; bin/llm-wait and bin/llm-schedule gate delegated work. Pi resource installer scripts/pi_setup.py and bin/pi-link-extensions; skills/delegate and ralph-loop are further consumers. Read current implementation, not only old docs. Parent is adding grok-build provider (CLI OAuth, Grok 4.7), usage observer and quota candidate; assume it must eventually fit your recommendation but do NOT edit that integration.

Installed Pi 0.99.1 docs models.md already mentions TypeSafe Jev classification via models.classify, codemode, providers typesafe/openrouter/cloudflare-workers-ai/vercel-ai-gateway/opencode. Classifier models do not chat or show in /model. This is a starting lead, not proof of pricing, policy or capabilities. Native source available under /home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent and its node_modules/@earendil-works/pi-ai. Don't run classifier requests or paid APIs.

## Outcomes
1. Explain Jev's actual contract, inputs/outputs/confidence/calibration/limits/providers/auth/current costs, with primary docs/source URLs and access dates. Distinguish local llama.cpp classification vs hosted Jev if relevant.
2. Trace installed Pi's classifier API, virtual models/routing extension seams, codemode behavior; follow linked .md docs fully and inspect current checked examples. Explain which functions/hooks/version are available, not imagined APIs.
3. Map our exact routing/data flow with file/function references; identify where Jev could choose task class, capability tier, provider/model, escalation, or scheduling. Preserve hard quota/budget/availability gates; classifier output must not override them.
4. Compare minimal deterministic baseline vs Jev-assisted approach. Consider confidence thresholds, abstention, latency, per-decision cost, cache keys, prompt privacy/token custody, prompt injection, failure fallback, observability and /usage accounting. Distinguish quota from classification inference spend. Provider switch sends context elsewhere; honor existing constraints.
5. Recommend smallest useful opt-in experiment with detailed implementation plan and offline/live test/evaluation criteria, rollback and knobs. No implementation, no credential reads, no subscription/API spend, no service restart, no auto route changes. Flag uncertain facts rather than inventing APIs or prices.

## Scope / output
Read CLAUDE.md and web-research/research skills. Work in your isolated research worktree. Own only docs/research/jev-pi-routing.md (single durable cited findings doc). You may read parent repo to see current Grok changes, but must not write parent files. Commit only your report on your branch; parent owns merge. Do not push. GIT_EDITOR=true git rebase --continue if ever needed. Scratch /home/gustaf/.cache/jev-research, not /tmp. Budget ~20min research, report blockers and sources instead of endless blocked search engines. Fetch known docs/GitHub directly when search engines rate-limit. Notify parent when report is ready.
