# Text model backend (TYPE_TEXT only)

`CLICK`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, and `BLOCKED` need only the TypeSafe
key. Only `TYPE_TEXT` (typing a value into an editable field) calls a second, separate text model.

This skill makes **no default choice** of text-model provider. You must set:

- `TEXT_MODEL_API_KEY` — the explicitly selected provider's credential.
- `TEXT_MODEL_BASE_URL` — its HTTPS OpenAI-compatible API base URL; the helper appends
  `/chat/completions`. Embedded URL credentials are rejected.
- `TEXT_MODEL` — the exact model ID to use.

All three must be set together. Partial configuration is rejected before execution;
upstream's implicit DeepSeek defaults are intentionally not used. With none configured,
click-only runs may proceed, but a `TYPE_TEXT` step fails before typing anything.

Why this skill doesn't wire up a Pi OAuth-backed model instead: upstream's text helper speaks a plain
OpenAI-compatible `/chat/completions` HTTP call with an API key, not Pi's internal provider/tool
plumbing, and a goal of this integration is that the text helper gets **no tool access and no
unrelated Pi session context** — only `{goal, field, page title, truncated visible text, recent
actions}`. Bridging that to a specific Pi-managed subscription model would need either a new local
OpenAI-compatible shim in front of a Pi provider (meaningful new surface, not done here) or reusing an
existing metered key you explicitly already pay for. Pick one by setting the three variables above;
report back if you want a Pi-model shim built as a follow-up.

Distinguish this from your Pi/Claude Code coding-model subscription: `TEXT_MODEL_API_KEY` is a
separate, directly metered API key billed by whatever provider's endpoint you point `TEXT_MODEL_BASE_URL`
at (DeepSeek, OpenRouter, or another OpenAI-compatible host). `TYPESAFE_API_KEY` is Jev's own metered
inference, billed by TypeSafe, and separate again from the existing shadow task-classifier's budget
(`config/llm-proxy/jev.json` caps do not apply here).
