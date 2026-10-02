# Integrate Grok CLI OAuth into llm-usage and proxy quota oracle

User explicitly requests Grok added across Pi, llm-usage, token-proxies in $DOTFILES, research as needed. Parent coordinating; sibling implements Pi OAuth auth provider ID `grok-build`. You own usage/proxy integration.

Evidence: Official Grok CLI 1.0.46 installed, authenticated ~/.grok/auth.json OIDC. Parent proved Pi grok-4.7 openai-responses with https://cli-chat-proxy.grok.com/v1, headers X-XAI-Token-Auth=xai-grok-cli, x-grok-client-identifier=pi, x-grok-client-version=1.0.46. No API keys; /models works. /home/gustaf/.cache/grok-research/PROOF.md. Downloaded community adapter /home/gustaf/.cache/grok-research/demi/package/dist/index.mjs includes quota/user endpoint adapter; research and read source. Actual live behavior outranks assumptions in old research.

Own: scripts/llm_usage.py, bin/claude-token-proxy, new scripts/grok_usage.py if useful, tests/unit/test_grok_usage.py and test_proxy_grok.py; docs/research/grok-usage-implementation.md. Do NOT change routes.json, classes.json, existing tests or Pi extension/setup/docs shared files. Parent will integrate tests and route policy. Do not modify live service/cache/config or restart anything.

Required:
- Read CLAUDE.md and relevant code; usage/proxy observers MUST read-only use current token, never refresh OAuth (sibling owns auth refresh). Never print tokens/raw credential/account responses. Read-only live account/quota GET probes authorized but capture only sanitized schemas/quotas. Never call inference or paid API.
- Research actual Grok quota/user endpoints, expose meaningful subscription/account windows/reset/limits/source/freshness in llm-usage and proxy /_usage providers.grok-build, missing auth/expired/unknown safe and clear.
- Do not invent quota unlimited or assume remaining quota from successful /models. Unknown quota must never qualify for proactive routing. Add route candidate support if safe, but don't automatically add Grok to route table or switch user models. Existing Anthropic/Codex/DeepSeek unaffected. No Grok passthrough translation inside Anthropic proxy.
- Keep proxy current architectural conventions (stdlib standalone if mandated). New module if importing safe versus duplicate minimal adapter, justify. Tests offline mocked HTTP/temp HOME/cache no live refresh or real cache writes. Exact test commands in report. Handle expiry HTTP errors schema variation malformed data, avoid redirects credential exfiltration, bound network time.
- Work in isolated branch; commit only owned files, no merge/push. Parent owns merge. GIT_EDITOR=true git rebase --continue if needed. Persistent scratch ~/.cache/grok-research not /tmp. Budget ~15min; report unsupported quota truthfully instead of speculative values.
