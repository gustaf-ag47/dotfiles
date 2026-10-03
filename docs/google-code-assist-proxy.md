# Gemini in Pi via the Antigravity OAuth session

Same pattern as the Claude subscription setup: Pi uses its **native** provider
implementation (`google-generative-ai`: tools, thinking, thought signatures,
images) against a loopback endpoint that holds the subscription credential.
No second agent is spawned.

```
pi ──(Gemini API, placeholder key)──> 127.0.0.1:8790 google-code-assist-proxy
     ──(Bearer <agy OAuth>, {project, model, request})──> daily-cloudcode-pa.googleapis.com/v1internal
```

## Status

The native Gemini implementation is on `master` (superseding the earlier
text-only prototype and its closeout hold). The laptop service and Pi tool calling
have been verified. The original 403 was resolved by using the discovered project
and correct model IDs, not by purchasing a subscription. No `agy` subprocess is
spawned by inference; the proxy preserves the native Gemini tool/thinking payloads.

Each host needs its own explicitly provisioned Antigravity OAuth session and client
installation for refresh support. Credentials are not in git and are not silently
copied by `pi-setup`. The other host must not advertise this provider as ready
before its credentials, service and live tool-call check succeed.

## Pieces

| File | Role |
| --- | --- |
| `bin/google-code-assist-proxy` | Shim: wraps Gemini requests in the Code Assist envelope, unwraps `{"response": …}` replies/SSE events |
| `config/systemd/user/google-code-assist-proxy.service` | User unit (not enabled by `make install`) |
| `config/pi/models.example.json` | `google-antigravity` provider block for `~/.pi/agent/models.json` |

## Activation (manual)

```bash
agy                                  # sign in once
ln -sfn "$DOTFILES/config/systemd/user/google-code-assist-proxy.service" ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now google-code-assist-proxy
# merge the google-antigravity block from config/pi/models.example.json into ~/.pi/agent/models.json
pi --model google-antigravity/gemini-3.8-flash-tiered
curl -s 127.0.0.1:8790/_usage        # per-model remaining quota + reset time
```

Not a default model; select it explicitly or via `/model`.

## What made direct calls work

The Antigravity backend is the Code Assist `v1internal` API. Earlier attempts
failed only because of the request, not the account:

- **Project**: must be `cloudaicompanionProject` from `loadCodeAssist`
  (`aicode-consumers` on the free "Antigravity" tier). `agy`'s local
  `default-cli-project` gives `403 SUBSCRIPTION_REQUIRED`. Override with
  `GOOGLE_CODE_ASSIST_PROJECT`.
- **Model ids**: backend ids from `fetchAvailableModels`
  (`gemini-3.8-flash-tiered`, `gemini-3.6-flash-high`, `gemini-3.1-pro-low`, …),
  not agy's labels (`gemini-3.8-flash-low` → 404).

## Credentials

- Reads `~/.gemini/antigravity-cli/antigravity-oauth-token` (owned by `agy`),
  never writes it; picks up agy's newer token whenever the file changes.
- An expired access token is refreshed **in memory** with the stored refresh
  token and agy's OAuth client: client id from the id_token `aud`, client secret
  found in the installed `agy` binary at runtime (or
  `GOOGLE_ANTIGRAVITY_CLIENT_SECRET`). Like the Claude Code OAuth reuse, this
  presents as Google's own client; that is the policy trade-off of this setup.
- No logging; Pi's placeholder key is ignored; upstream errors are reduced to
  status, message and `ErrorInfo.reason` (so Pi's 429/503 retry still works).
- Listens on `127.0.0.1` only (any other bind address is refused).

## Limits

- Quota is the Antigravity weekly Gemini bucket shared with `agy`
  (`GET /_usage`, shown by `llm-usage` as `google-antigravity`). Not in the
  route oracle or `llm-failover`.
- Model list in `models.json` is static; refresh it from `/_usage` when Google
  ships new ids.
- Undocumented internal API; may change without notice.
