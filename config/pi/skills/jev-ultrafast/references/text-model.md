# Typing backend (TYPE_TEXT only)

Jev chooses the operation/target. Only `TYPE_TEXT` needs text generation. Choose
**Pi** (existing credentials) or **API** (an explicitly configured compatible
endpoint); neither silently falls back to the other.

## Pi: existing OAuth credentials, no separate text API key

One run:

```sh
python3 scripts/run.py --url 'https://example.com' --goal 'your explicit goal' \
  --text-backend pi --pi-text-model openai-codex/gpt-5.6-luna \
  --execute --max-steps 8 --max-seconds 60
```

Resolve `scripts/run.py` relative to this skill directory. Keep the usual human
step approvals in an interactive terminal/tmux pane.

Or save a non-secret preference in
`${XDG_CONFIG_HOME:-$HOME/.config}/jev-ultrafast/text-model.json`:

```json
{
  "backend": "pi",
  "model": "openai-codex/gpt-5.6-luna",
  "timeout_seconds": 30
}
```

Environment equivalents: `TEXT_MODEL_BACKEND=pi`, `PI_TEXT_MODEL=provider/id`,
`PI_TEXT_TIMEOUT_SECONDS=30` (1–60 seconds). Model IDs must be exact. Supported
providers are `openai-codex`, `anthropic`, and `grok-build`; choose a model actually
available to your account. Credentials are not copied into this file.

- Codex uses Pi's credential store and native OAuth refresh.
- Anthropic reuses the dotfiles local subscription-pool provider; DeepSeek proxy
  fallback is disabled for these requests.
- Grok reuses the dotfiles `grok-build` provider (including its CLI-session path).
- Other custom providers, virtual models and `models.json` endpoint overrides
  are deliberately not loaded by this small adapter.

`doctor.py` checks Node/Pi SDK presence and configuration, **not** provider auth,
quota or model availability. Missing credentials, unavailable models, quota errors,
timeouts and malformed responses stop typing; there is no provider/model fallback.
Use the normal owning client's login to restore credentials.

## API: explicitly configured endpoint

Set **all three**:

- `TEXT_MODEL_API_KEY`
- `TEXT_MODEL_BASE_URL`: HTTPS base URL; `/chat/completions` is appended.
- `TEXT_MODEL`: exact model ID.

`TEXT_MODEL_BACKEND=api` selects this path explicitly. An API environment also
selects it when no backend is specified, preserving the existing setup. A partial
API configuration is an error, not an excuse to use the saved Pi choice. Combining
Pi selection with API credentials is rejected as ambiguous. Upstream's implicit
DeepSeek defaults are not used.

`TEXT_MODEL_BACKEND=none` disables typing even when keys/preferences exist.
With nothing configured, click-only runs may proceed; a typing operation stops.

## What the Pi adapter does

The pinned upstream's `field_text` callback is replaced **in memory**, leaving its
operation selection, freshness checks, approval gates and browser executor intact.
A one-shot Node worker invokes Pi's `ModelRuntime.completeSimple()` directly with:

- one fixed instruction and the upstream's bounded `field_context` (goal, field,
  page title/visible text, at most six recent actions), maximum 32 KiB;
- no coding tools, agent loop, conversation history, skills, AGENTS files, prompt
  templates, arbitrary extensions, session persistence, or extra HTTP server;
- only the selected dotfiles provider adapter for Anthropic/Grok when needed;
- a per-field deadline, zero inference retries, and a requested 1024-output-token
  limit; the outer browser timeout still terminates the whole run;
- strict JSON output: exactly one nonempty `text` string of at most 2000 characters.
  Null means a required value is missing, not the literal text to type. Prose,
  tool calls, truncated output and extra fields are rejected.

State travels over stdin, not argv or temporary prompt files. Generated values
travel back over a bounded private pipe, not diagnostic logs. The key is resolved
by Pi and never passed to another model service. OAuth refresh may update Pi's own
credential store, as normal.

Browser data **does leave the machine to the selected model provider**. Reusing
OAuth avoids a separate API key; it does not guarantee free usage, local inference,
or the upstream demo's speed. Provider quota/credits/extra-usage rules still apply.
Text-model usage is returned to upstream's in-memory metadata, separately from
Jev's decision calls; neither is charged to the task classifier's local budget.
