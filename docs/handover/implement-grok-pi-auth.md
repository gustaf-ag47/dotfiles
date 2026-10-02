# Implement production Grok CLI OAuth provider for Pi

User authorized adding proven Grok CLI OAuth to dotfiles Pi/llm-usage/token-proxies now. Parent coordinates integration; do not merge/push or change live services.

## Evidence
Official Grok CLI 1.0.46 installed at ~/.grok/bin/grok, user logged in via `grok login --device-auth`. Parent proved Pi inference+tool call+follow-up in tmux grok-oauth-proof using OAuth only, no API keys, client identified honestly as pi. Proof/config at /home/gustaf/.cache/grok-research/{PROOF.md,pi-agent/models.json,oauth-token.py}; safe to read, NO raw auth.json output. Endpoint https://cli-chat-proxy.grok.com/v1, API openai-responses, model grok-4.7 fetched from /models (256000 context; 500000 optional; reasoning low/medium/high/xhigh). Headers only X-XAI-Token-Auth=xai-grok-cli, x-grok-client-identifier=pi, x-grok-client-version=1.0.46 needed. Tokens saved ~/.grok/auth.json OIDC entry `https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828`. Never assume public api.x.ai takes these tokens.
Community reference source downloaded /home/gustaf/.cache/grok-research/demi/package/dist/index.mjs (auth refresh/locking etc). Use as reference, don't blindly copy dependency. Research skill available. Earlier docs claim impersonation required; live proof with identifier pi disproves that assumption. Don't repeat unverified legal claims.

## Own ONLY
- New config/pi/extensions/grok-build.ts and new config/pi/lib/grok-* helpers if needed.
- New scripts/grok_oauth.py and bin/grok-oauth-token if command auth bridge is appropriate; choose simple robust design.
- New tests/unit/test_grok_oauth.py and/or test_grok_provider.mjs.
- docs/research/grok-pi-auth-implementation.md report.
Sibling owns usage+proxy; parent owns install/docs/integration. Do not edit other existing files; propose needed setup changes in report.

## Required
Read repo CLAUDE.md and full relevant Pi docs/examples BEFORE implementation. Native supported provider extension preferred, registration must not break other providers/no-login startup. Reuse openai-responses implementation, actual CLI version/model metadata; honest pi identity. Expose provider ID `grok-build` (not xai paid API). Do not change default model or add auto fallbacks. Support CLI auth file and safe bounded OAuth refresh, locking compatible with CLI if verifiable, atomic file preservation, no leaked secrets, guard token endpoints (fixed known issuer), no arbitrary-host credential sending, no redirects of credentials. Multi-Pi concurrency and CLI refresh ownership considered; don't casually invent compatible lock contract. Missing/expired/bad auth should yield useful non-secret errors, not mark all Pi providers broken. Respect GROK_HOME when supported. No install of third-party provider package. Avoid API key fallback.
Keep tests offline temp HOME/cache; inject mock refresh/network, test refresh preservation, concurrency, permissions, errors, absent auth, model/endpoint. Never rotate or change live credentials during development. Parent will live verify. Run exact relevant test invocations and report. No /tmp caches. Budget ~15 minutes; report blockers rather than speculative implementation. Commit ONLY owned files in own branch; parent owns merge. GIT_EDITOR=true git rebase --continue if needed.
