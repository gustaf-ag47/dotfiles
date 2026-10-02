# Grok CLI OAuth Pi provider (`grok-build`)

Status: implemented and manually verified end-to-end against the live
`cli-chat-proxy.grok.com` backend (with a deliberately invalid token, to
avoid touching real credentials). Full real-token inference is **not**
verified by this change; the parent coordinates that live check. Branch
`feat/grok-pi-auth`, own-files only.

## Correction to the earlier handover assumption

The handover this task started from assumed Pi had no relevant native OAuth
and that we'd likely need to hand-roll device-code OAuth and/or a CLI
auth-file reader with our own refresh/locking. That assumption was wrong.

`@earendil-works/pi-ai` (the package Pi's coding agent is built on, already
vendored at `config/pi/node_modules/@earendil-works/pi-ai` in the installed
dotfiles) ships a **native `xai` provider**
(`providers/xai.ts` / `dist/providers/xai.js`) whose OAuth flow
(`auth/oauth/xai.ts`):

- uses client_id `b1a00492-073a-47ea-816f-4c329264a828` — **the same client
  id** the Grok CLI itself uses (confirmed against the proof-of-concept's
  `~/.grok/auth.json` entry key
  `https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828`),
- talks to the same `auth.x.ai` device-code/token endpoints,
- requests scope `openid profile email offline_access grok-cli:access
  api:access` — i.e. it already asks for `grok-cli:access`,
- implements device-code login, token refresh with refresh-token rotation
  handling, and expiry skew, and
- stores credentials through Pi's own `CredentialStore`, which is
  cross-process file-locked and serializes refresh so concurrent Pi
  instances cannot double-refresh a rotated token.

The only thing that native `xai` provider does differently from what we need
is point at `https://api.x.ai/v1` (the paid, metered API) instead of
`https://cli-chat-proxy.grok.com/v1` (the Grok CLI's own OAuth-gated,
subscription-backed backend that the proof-of-concept exercised).

This directly contradicts the "impersonation/no in-repo OAuth support"
assumption in earlier research docs referenced by the original handover.
Parent should correct any such claim; it does not hold for this flow with
client identifier `pi` and the CLI proxy host.

## Design

New provider `grok-build`, registered from a single extension:

- `config/pi/extensions/grok-build.ts` — registers a complete `Provider`
  (`pi.registerProvider()`, native form) built by spreading Pi's own
  `xaiProvider()` and overriding only `id`, `name`, `baseUrl`, `headers`,
  `models`, `getModels`, `refreshModels`, `stream`, `streamSimple`. This is
  the same "wrap a native provider and re-route it" pattern already used by
  `config/pi/extensions/anthropic-subscription.ts` for the local Claude
  proxy.
  - `baseUrl`: `https://cli-chat-proxy.grok.com/v1` (fixed, never derived
    from input).
  - `headers`: `X-XAI-Token-Auth: xai-grok-cli`,
    `x-grok-client-identifier: pi`, `x-grok-client-version: 1.0.46` — exactly
    the headers the live proof used, with an honest client identifier
    (`pi`, not a spoofed Claude Code / Grok CLI identity).
  - `models`: a single static `grok-4.7` entry matching the live `/models`
    response captured in the proof (`api_backend=responses`, 256000 token
    context window; the proof also noted an optional 500000 window, not
    modeled as a separate variant since the live behavior of that flag
    wasn't exercised). No `cost` is implied beyond zero: this is a
    subscription-gated CLI backend, not metered `api.x.ai` billing, so
    nonzero cost numbers would be fabricated.
  - `refreshModels`: queries `GET {baseUrl}/models` with `redirect: "error"`
    (never follows a redirect off the fixed host) when network access is
    allowed and a credential is configured; on any failure (offline, non-2xx,
    bad JSON) it silently keeps the previous/static list rather than clearing
    the catalog — a missing/expired/bad auth state degrades to "use the
    static grok-4.7 entry", not "no models".
  - `stream`/`streamSimple`: delegate entirely to the native `xai` provider's
    own `openai-responses` implementation, just routed at the model object
    (`baseUrl`/`headers` overridden per request) so Pi's existing message
    conversion, tool handling, usage accounting, retry/compaction, and
    cancellation behavior are reused unmodified, per `docs/custom-provider.md`.

- **Auth, two paths, one credential per store:**
  1. **Primary — reused native OAuth** (`auth.oauth: native.auth.oauth`):
     `/login grok-build` runs Pi's own device-code flow against `auth.x.ai`
     (same client id/scope as above) and Pi stores/refreshes the resulting
     credential in its own `~/.pi/agent/auth.json`, keyed by the
     `grok-build` provider id — distinct from any separately configured
     `xai` provider credential, but still only **one** store, with Pi's
     already-tested refresh and cross-process locking. This avoids
     reimplementing a lock/refresh contract against the Grok CLI's own
     `~/.grok/auth.json`, which the handover explicitly warned not to
     casually invent.
     - **Not yet live-verified**: that a token obtained through *Pi's own*
       login (rather than `grok login --device-auth`) is accepted by
       `cli-chat-proxy.grok.com`. The client id/scope match structurally,
       but only a CLI-obtained token was proven live. Flagging for parent
       verification; do **not** assume it works without a real `/login
       grok-build` check.
  2. **Secondary — read-only Grok CLI session bridge**
     (`scripts/grok_oauth.py`, wrapped by `bin/grok-oauth-token`, wired as
     the provider's `apiKey` auth via a `!command` credential): reads the
     Grok CLI's own `$GROK_HOME/auth.json` (default `~/.grok/auth.json`),
     validates the entry is keyed to the **fixed, hardcoded** issuer/client
     (`https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828` — never
     derived from file contents, so a tampered file can't redirect trust to
     another issuer), checks `auth_mode == "oidc"`, and prints the current
     access token. **It never writes to that file and never refreshes it.**
     The Grok CLI remains the sole owner of that file's refresh/rotation.
     Pi re-invokes the script fresh on every request (Pi's `!command` apiKey
     resolution already does this) instead of caching a copy, so a given
     refresh token is still only ever rotated by one process. This
     satisfies "do not copy rotating refresh credentials into two
     independent stores": the CLI's store is read-only from Pi's side, and
     Pi's own OAuth store (path 1) is entirely separate and self-contained.

  Both paths coexist under one provider; `/login grok-build` offers a choice
  between them. Neither reads nor writes the other's storage.

- **GROK_HOME**: respected by the bridge script (`$GROK_HOME/auth.json`,
  default `~/.grok/auth.json`), matching the Grok CLI's own convention
  (confirmed against the community reference implementation at
  `/home/gustaf/.cache/grok-research/demi/package/dist/index.mjs`, which
  reads the same env var and default path — used only as a field-name/shape
  reference, not copied).

- **No arbitrary-host credential sending**: the fixed `baseUrl` is never
  parameterized by user/file input; `fetchGrokModels()` only ever requests
  `${GROK_BUILD_BASE_URL}/models` and sets `redirect: "error"` so a
  malicious or misconfigured response can't bounce the request (and its
  bearer token) to another host.

- **No install of third-party provider package** and **no API-key
  fallback**: the provider has no `XAI_API_KEY`/`GROK_API_KEY` env-var path;
  its only two auth methods are the two described above. It never falls
  back to `api.x.ai`.

- **Does not change the default model** or add cross-provider fallback: this
  is purely a new, opt-in provider id; nothing about default model selection
  or other providers changes.

## Verification performed (no real credentials used)

All runs below use a temp `PI_CODING_AGENT_DIR` and/or temp `GROK_HOME`;
none touch `~/.pi` or `~/.grok`.

1. **No-login / no-extension baseline unaffected**: with a fresh
   `PI_CODING_AGENT_DIR` and no credentials anywhere, `pi --list-models`
   prints "No models available..." both with and without
   `--extension ./config/pi/extensions/grok-build.ts` loaded — identical
   output, confirming the new provider does not break default/no-login
   startup or other providers.

2. **Extension loads and registers the provider** (against the installed
   dotfiles' `config/pi/node_modules/@earendil-works/pi-ai`, temporarily
   symlinked into this worktree for the test run only, then removed before
   committing — this worktree does not and should not carry its own
   `node_modules`):

   ```
   $ PI_CODING_AGENT_DIR=<tmp> pi --extension ./config/pi/extensions/grok-build.ts --list-models
   provider    model     context  max-out  thinking  images
   grok-build  grok-4.7  256K     8.2K     yes       no
   ```

3. **End-to-end request plumbing against the real backend**, using the
   read-only CLI bridge with a deliberately fake token (temp `GROK_HOME`,
   temp `PI_CODING_AGENT_DIR` auth.json pointing `grok-build`'s apiKey at
   `bin/grok-oauth-token`):

   ```
   $ pi --model grok-build/grok-4.7 -p "say hi"
   grok-build API error (401): 401 "Invalid or expired credentials
   (auth_kind=bearer, x_xai_token_auth=xai-grok-cli, upstream=PermissionDenied,
   reason=no auth context)"
   ```

   The server's own error echoes `x_xai_token_auth=xai-grok-cli`, confirming
   the request actually reached `cli-chat-proxy.grok.com` with the correct
   header and bearer-auth shape; it rejected only because the token was
   intentionally fake. This is the strongest offline-safe signal available
   that `baseUrl`, headers, and the reused `openai-responses` stream wiring
   are correct.

4. **Unit tests for the CLI auth bridge** (`tests/unit/test_grok_oauth.py`,
   offline, temp `GROK_HOME` per test, no real file touched):

   ```
   $ python3 -m pytest tests/unit/test_grok_oauth.py -v
   12 passed
   ```

   Covers: missing auth file, malformed JSON, wrong/missing entry key
   (guarded fixed issuer), wrong `auth_mode`, missing token field, valid
   session (prints only the token), `GROK_HOME` override, the script never
   writing/mutating the auth file (mtime + byte-identical content across two
   runs), expired-`expires_at` rejection, future-`expires_at` acceptance,
   and absent-`expires_at` (CLI-owned, not treated as expired).

## Not done / handed to others

- No live login through either auth path was performed (would require a
  real device-code round trip or a real Grok CLI session); parent owns live
  verification per the handover.
- Usage accounting/proxy integration is the sibling's; this change only
  registers the provider and its auth, consistent with "own ONLY" scope.
- Install/documentation wiring (e.g. adding `grok-build` to
  `config/pi/models.example.json` or `docs/`) is parent's; not touched here.
- `GROK_CLI_VERSION` ("1.0.46") is hardcoded to the version the proof was
  captured against; it is not re-derived from a live `grok --version` call.
  Bump it deliberately on re-verification against a newer CLI, don't guess.

## Files owned by this change

- `config/pi/extensions/grok-build.ts` — provider registration
- `scripts/grok_oauth.py` — read-only Grok CLI auth-file bridge
- `bin/grok-oauth-token` — thin exec wrapper for the bridge, used as the
  provider's `!command` apiKey credential
- `tests/unit/test_grok_oauth.py` — offline bridge-script tests
- `docs/research/grok-pi-auth-implementation.md` — this report
