# Google Gemini in Pi via the Antigravity OAuth session (EXPERIMENTAL)

`bin/google-code-assist-proxy` is a loopback-only, OpenAI-compatible proxy that
lets Pi reach Gemini through the OAuth session the Antigravity CLI (`agy`)
already holds. It is **experimental, text-only, and not a default model**.

## Closeout disposition (2026-10-03)

Preserved on `feat/google-code-assist-proxy`, **not promoted into the active master
configuration**. The live service is disabled and the stale local provider entry
is removed by the coordinator. The successful earlier text probe does not establish
safe tool-capable inference. Direct access currently fails in the tested account/
project configuration; whether that is entitlement or project selection needs
separate investigation. No subscription purchase or credential migration is implied.
The opt-in `agy` path launches a second agent: sandboxing and an empty working
directory are not proof of tool-less behavior or absence of global context. Do not
use it as a transparent replacement for Pi's permission/tool execution model.

## Pieces

| File | Role |
| --- | --- |
| `bin/google-code-assist-proxy` | Proxy on `127.0.0.1:8790` (refuses any other bind address) |
| `config/systemd/user/google-code-assist-proxy.service` | User unit (not enabled by `make install`) |
| `config/pi/models.example.json` | `google-cloud-code` provider template for `~/.pi/agent/models.json` |

## Activation (manual)

```bash
agy                                  # sign in once; agy owns and refreshes the token
ln -sfn "$DOTFILES/config/systemd/user/google-code-assist-proxy.service" ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now google-code-assist-proxy
# copy the google-cloud-code provider block from config/pi/models.example.json into ~/.pi/agent/models.json
pi --no-tools --model google-cloud-code/gemini-3.8-flash-low
```

## Limitations / safety

- **No tool calling.** Requests containing `tools`, `tool_choice`, tool calls,
  tool results or non-text content get HTTP 400. Pi's normal coding mode sends
  tools, so use `--no-tools` (chat, review, summarisation). Nothing is silently
  dropped and tool support is never claimed.
- **Credential handling.** Reads `~/.gemini/antigravity-cli/antigravity-oauth-token`
  read-only; never refreshes, writes, logs or echoes it. An expired token yields
  HTTP 503 "run `agy` once to refresh it". No request logging; upstream error
  bodies are not forwarded.
- **Direct path.** `POST /v1internal:generateContent` on Cloud Code Assist. The
  tested account/project configuration returned `403 SUBSCRIPTION_REQUIRED`,
  which the proxy reports as a 502 error. This is not proof that all consumer
  accounts fail or that purchasing a subscription is the correct fix.
- **`agy` fallback (opt-in).** With `GOOGLE_CODE_ASSIST_AGY_FALLBACK=1`, a 401/403
  makes the proxy run `agy --sandbox --disable-slash-commands -p=<transcript>` in
  an empty temp directory. That is a second agent process using the Antigravity
  quota; the prompt is passed on argv (visible in `ps` to the same user). Off by
  default.
- Streaming is emulated: the full answer arrives as one SSE chunk.
- Not integrated with `llm-usage`, the Anthropic proxy route oracle, or
  `llm-failover`. Antigravity quota is visible via `agy --output-format json -p='/usage'`.
