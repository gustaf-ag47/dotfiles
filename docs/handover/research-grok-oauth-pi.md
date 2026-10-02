# Research brief: Grok OAuth for Pi via local proxy

## Context
The user asks how to use Grok with OAuth in Pi, analogous to this dotfiles setup's Claude Code OAuth proxy (`bin/claude-token-proxy`, Pi Anthropic pool extension). The existing proxy manages Anthropic subscription OAuth and speaks Anthropic Messages; it is not a generic OAuth broker or wire-format translator. Research must determine whether there is an official/legitimate xAI OAuth flow for Grok API usage, and practical community routes that could expose OAuth-authenticated Grok via an OpenAI-compatible endpoint/Pi provider.

## Job
Research one focused angle using the web-research skill scripts, reading primary sources and checking dates:
1. Search official xAI docs/product announcements for OAuth, API auth, OAuth/API access, and Grok Code/Grok CLI.
2. Investigate credible projects that bridge consumer Grok OAuth/subscription into OpenAI-compatible API proxies (e.g. CLI tools, gateways); determine actual auth source, protocol, maintenance/security/legal caveats.
3. Explain whether Pi can connect directly via models.json or needs provider extension/proxy, grounded in Pi docs if relevant.
4. Record concise findings with URLs, source dates, verified vs unverified claims, and a direct recommendation.

## Scope / safety
Read-only. Do not edit implementation, run logins, handle credentials, call paid APIs, or change services. Do not assume Claude OAuth credentials can be reused for xAI. Avoid presenting unofficial reverse-engineering as official/endorsed. Never expose secrets.

## Output
Write findings to `docs/research/grok-oauth-pi-<ANGLE>.md` (use `official` or `community`). Include source URLs and accessed date. No code changes beyond that research file; do not commit unless asked.
