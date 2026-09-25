---
name: deepseek
description: Run Pi sessions, delegated agents or loops on DeepSeek's metered API instead of Anthropic or ChatGPT subscription quota. Use when the user requests DeepSeek or explicitly approves moving work off the subscription providers.
---

# DeepSeek in the unified Pi setup

Use **plain `pi`**, just as for Anthropic and ChatGPT. DeepSeek uses separately
metered API credit, not either subscription. Switching providers sends the
conversation to that provider; get approval before switching private work.

## Verify availability

```bash
pi --list-models deepseek
llm-usage --provider deepseek
```

Pi resolves a stored `deepseek` credential in `~/.pi/agent/auth.json` before
`DEEPSEEK_API_KEY`. Missing models mean no resolvable auth/configuration, not
necessarily a missing environment variable. Set up credentials with Pi's `/login`;
keep keys outside tracked configuration. `llm-usage` reads balance without generating
an inference request. HTTP 402 during inference usually means insufficient balance.

## Run

Choose an available model from the installed catalog. Current examples:

```bash
pi --model deepseek/deepseek-v4-flash
pi --model deepseek/deepseek-v4-pro -p 'your task'
~/.pi/agent/skills/delegate/scripts/delegate.sh \
  --model deepseek/deepseek-v4-pro --brief docs/handover/my-task.md
```

Use Flash for inexpensive bulk work, Pro for harder tasks; verify current model
capabilities and prices rather than relying on fixed historical estimates.

## Loops

For a loop still using `pi-claude-sub`, explicitly configure its launcher as `pi`
and provider/model as DeepSeek. Keep these changes within the loop's documented
configuration; do not change live services or another lane without authorization.
Credentials in Pi's normal auth store are available to child Pi processes. A custom
`PI_CODING_AGENT_DIR` needs its own credential store or an intentionally shared link.

DeepSeek has no OAuth refresh lifecycle. Use `llm-usage` to check its prepaid balance;
re-authentication does not fix an empty balance.
