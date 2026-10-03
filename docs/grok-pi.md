# Grok CLI OAuth in Pi and LLM usage

Verified on 2026-10-02 with Pi 0.99.1 and Grok CLI 1.0.46. Provider ID: `grok-build`.
This uses the Grok CLI backend, **not** the metered `xai` API-key provider.

## Setup

Install the official CLI using the instructions at <https://x.ai/cli>, then:

```sh
grok login --device-auth
cd "$DOTFILES"
bin/pi-setup --check
bin/pi-setup --apply
pi --provider grok-build --model grok-4.7
```

Or restart Pi / run `/reload`, then select `grok-build/grok-4.7` in `/model`.
The resource installer adds the extension and helper without replacing existing
settings, credentials or sessions. The example settings include Grok in model
cycling; existing users can add it through `/scoped-models`. Defaults stay unchanged.

### Credential ownership

Two separate paths are supported:

- **Existing CLI login (works without another login):** Pi invokes
  `bin/grok-oauth-token`, reading the current OAuth access token from
  `$GROK_HOME/auth.json` (default `~/.grok/auth.json`). No token is copied into
  Pi's credential store. The helper never refreshes or writes that file. Keep
  the CLI session current; if it expires, run `grok models` to let the official
  CLI refresh it without generating model output. Use `grok login --device-auth`
  if refresh fails.
- **Pi-managed login:** `/login` → Grok CLI → OAuth reuses Pi's built-in xAI
  device flow and refresh implementation, storing a separate credential under
  `grok-build` in Pi's `auth.json`. This avoids sharing a rotating refresh token
  with the CLI. The native flow exists in the installed library, but this
  specific fresh-login path has not been live-tested in our integration.

Do not run `grok-oauth-token` in a visible terminal: its stdout is the access
credential, intended only for the provider/usage subprocess. Never commit auth
files or paste credentials into configs. The provider ignores xAI API-key env
variables; inference stays on `https://cli-chat-proxy.grok.com/v1` using Responses.
It identifies itself as `pi`; no Claude identity or wire-format proxy is involved.
The CLI backend is not a documented stable third-party API contract.

## Usage and routing

```sh
llm-usage                       # Grok included alongside existing providers
llm-usage --provider grok-build --refresh
llm-usage --provider grok-build --json
```

The read-only observers in `scripts/llm_usage.py` and `bin/claude-token-proxy`
prefer a Pi-managed `grok-build` OAuth credential; when absent they use the
existing CLI session via the same helper. Neither observer logs in or refreshes.
An expired Pi-managed credential is reported explicitly rather than silently
switching accounts. Refresh/login in its owning client.

For an already running proxy, restart `claude-token-proxy.service` after updating
its code (at a safe point: a restart interrupts in-flight requests). After the
initial asynchronous poll, `/_usage` includes `providers.grok-build`. Pi's
`/usage` command uses `llm-usage` and therefore includes Grok too.

**Unknown means unknown:** the tested account's billing response exposes a weekly
period but no recognized usage/limit amount. The report shows `UNKNOWN` / `?%`,
not free capacity. A successful quota GET does not establish inference headroom.
A later real inference rejection (2026-10-02) did expose a **historical** quota
observation: HTTP 429 reported `grok-4.7` free usage at 602,828 / 600,000 tokens
in a rolling 24-hour window. This was absent from the successful billing GET.
It is not a live remaining-balance reading, does not specify which token categories
count, and provides no exact reset timestamp. Capturing these error observations
with timestamps/model/account scope is a follow-up, not implemented by the current
billing reader; do not hard-code that limit for other plans or infer a midnight reset.

Grok is intentionally **not** added to `routes.json`, task classes, automatic
failover, or the waste/reset scheduler. Manual selection works. The `grok.routable`
predicate in `llm-wait` remains false unless a future oracle candidate explicitly
establishes readiness. Existing provider priorities remain unchanged.

## Verification

- `make test-unit`: 239 tests, OK (one pre-existing skip).
- `node --test --experimental-strip-types tests/unit/test_grok_cli_bridge.mjs tests/unit/test_llm_failover.mjs`: 30 passing.
- Normal installed Pi (no isolated proof config), with xAI/Grok/OpenAI key env vars
  unset, returned `GROK_DOTFILES_OK` from `grok-build/grok-4.7`.
- Normal `llm-usage --refresh` includes Grok using `grok-cli-session`.
- Restarted proxy's `/_usage` reports Grok observer `status=ok`, credential source
  `grok-cli-session`; quota amount unknown.

The original throwaway proof in `~/.cache/grok-research` is no longer needed for
normal operation. Source, offline tests and installation now live in dotfiles.
