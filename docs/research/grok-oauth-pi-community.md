# Grok OAuth for Pi — community bridge projects

Accessed: 2026-10-02. Angle: concrete community/third-party code that reuses the
official Grok CLI's OAuth session to drive Grok from another tool, and what that would
mean for wiring it into Pi.

## Correction (2026-10-02, post-live-verification)

The original version of this document characterized reuse of the Grok CLI's OAuth
session outside the official CLI, in general, as "textbook reverse-engineering of an
internal/private API" implicitly against xAI's rules, and called the header-based
client fingerprinting used by `@demicodes/provider-grok-build` "impersonation" without
clearly separating that specific package's choices (hardcoded client id *and* a
client-identifier string that is not its own) from the general idea of a non-CLI client
using this OAuth flow. Two things sharpen that:

1. **A live, working integration was independently verified on this host** using an
   *honest* client identifier: a Pi `models.json` provider entry
   (`baseUrl: https://cli-chat-proxy.grok.com/v1`, headers including
   `x-grok-client-identifier: pi`, not `grok-shell`) made a real, successful inference
   call and tool-call round trip with `grok-4.7`, using a token read from the official
   Grok CLI's own `~/.grok/auth.json`. Confirmed by reading the session's own JSONL log
   at `~/.cache/grok-research/pi-agent/sessions/--home-gustaf--/*.jsonl` (2026-10-02):
   consistent `provider`/`model`/`api` fields, a real `toolCall`/`toolResult` pair, and a
   matching final reply. This demonstrates the backend does **not** require spoofing the
   `grok-shell` identifier specifically — it accepted a differently-identified client
   using the same OAuth bearer token and the same `X-XAI-Token-Auth: xai-grok-cli`
   marker header.
2. **Pi ships a native xAI OAuth provider of its own** (`@earendil-works/pi-ai`,
   `dist/auth/oauth/xai.js`/`dist/providers/xai.js`, read directly on this host,
   2026-10-02), using the same client id as the official `grok` CLI
   (`b1a00492-073a-47ea-816f-4c329264a828`) and the same `auth.x.ai` device-code
   endpoints. That client id is therefore not solely "the Grok CLI's own," secretly
   reused by third parties — Pi's own maintainers (or `@earendil-works/pi-ai`'s) chose
   to register/reuse the identical id for Pi's native login. This undercuts a strong
   claim that presenting that client id is inherently illegitimate client impersonation;
   it may simply be the client id xAI's device-code endpoint expects for this OAuth
   application family, used knowingly by more than one legitimate codebase.

**What this does *not* establish**: it does not confirm `cli-chat-proxy.grok.com` is
sanctioned for third-party/non-CLI use, does not confirm xAI's ToS permits or forbids
it, and does not make the `@demicodes/provider-grok-build` package itself any more or
less official — it remains an independent, unaffiliated project. The corrected framing
below replaces categorical "this is reverse-engineering prohibited by ToS" language with
"no documented xAI support was found for this; permission or prohibition is unconfirmed
either way," per the distinction the parent asked this document to draw.

## What exists: `@demicodes/provider-grok-build` (part of the `demi` toolkit)

- npm: https://www.npmjs.com/package/@demicodes/provider-grok-build (accessed
  2026-10-02, page dated 2026-09-24)
- Source: https://github.com/wspl/demi, package path
  `packages/provider-grok-build/src/` (files `auth.ts`, `chat.ts`, `headers.ts`,
  `device-login.ts`, fetched directly via GitHub raw content, 2026-10-02)
- License: Apache-2.0. `demi` itself is "pre-1.0", described by its own README as having
  a public API that "may still shift before the first published release"
  (https://github.com/wspl/demi, accessed 2026-10-02, dated 2026-06-27).

### What it actually does (verified from source, not just the README)

1. **Credential source**: reads the same `~/.grok/auth.json` (or `$GROK_HOME`) file the
   official `grok` CLI writes after `grok login`. It does **not** perform its own
   browser-based login by default — it is designed to piggyback on a prior official-CLI
   login (`auth.ts`: `FileGrokAuthStore`, error message literally says
   `"Run \`grok login\` first."`). It also ships its own standalone OAuth
   **device-code** flow (`device-login.ts`) that can obtain a fresh `auth.json`-shaped
   entry without the official CLI at all.
2. **OAuth mechanics it talks to** (from `device-login.ts`):
   - Issuer: `https://auth.x.ai`
   - Client ID: a fixed, hardcoded GUID (`b1a00492-073a-47ea-816f-4c329264a828`). Update:
     this exact client id is also used by Pi's own native `xai` OAuth provider (shipped
     in `@earendil-works/pi-ai`, confirmed by direct code inspection, 2026-10-02), so it
     is not necessarily a secretly-reused private id unique to the official CLI binary —
     it appears to be the id the `auth.x.ai` device-code endpoint expects for this OAuth
     application family more broadly. Still unconfirmed: whether xAI issued/registered
     that id for arbitrary third-party use, or only for its own first-party clients
     (official CLI, and whatever relationship `@earendil-works/pi-ai` has with xAI, which
     this research did not establish).
   - Flow: RFC 8628 OAuth2 Device Authorization Grant
     (`POST {issuer}/oauth2/device/code` → poll `POST {issuer}/oauth2/token` with
     `grant_type=urn:ietf:params:oauth:grant-type:device_code`), then refresh via
     standard `grant_type=refresh_token` against `{issuer}/oauth2/token`
     (`auth.ts`, `refreshGrokOidcToken`).
   - Scopes requested: `openid profile email offline_access grok-cli:access
     api:access conversations:read conversations:write workspaces:read
     workspaces:write` — a comment in the source states this "matches the official
     Grok CLI" request contract, i.e. it was reverse-engineered/mirrored from
     observing the real CLI, not published as a public OAuth client-registration
     contract by xAI.
   - After token issuance it also calls `GET {proxy}/user` for account enrichment,
     again mirroring, by the code's own comment, the official CLI's post-login
     behavior.
3. **Inference endpoint used**: **not** `api.x.ai`. It targets
   `https://cli-chat-proxy.grok.com/v1` (constant `DEFAULT_GROK_BUILD_BASE_URL` in
   `headers.ts`) — an OpenAI-chat-completions-shaped endpoint (`/chat/completions`-style
   body: `model`, `messages`, `stream: true`, `tools`, `tool_choice`, SSE deltas with
   `choices[].delta.content` / `tool_calls`) that is specific to the **Grok Build CLI
   product's backend**, not the documented public Inference API.
4. **Required non-standard headers** (`headers.ts`, `buildGrokBuildHeaders`):
   - `Authorization: Bearer <access_token>`
   - `X-XAI-Token-Auth: xai-grok-cli`
   - `x-authenticateresponse: authenticate-response`
   - `x-grok-client-version` (mirrors the real CLI's version string, read from
     `~/.grok/version.json` or a hardcoded fallback `1.0.5`)
   - `x-grok-client-identifier: grok-shell` (or `$GROK_CLIENT_NAME`)
   - `x-grok-client-mode: interactive`
   - plus `x-userid`, `x-email`, `x-grok-session-id`/`x-grok-conv-id`, etc.
   These headers suggest the backend inspects client identity in some way. Note,
   however, that `x-grok-client-identifier: grok-shell` is this package's **choice** of
   value, not a protocol requirement discovered in this research: a live test using
   `x-grok-client-identifier: pi` (an honest, non-spoofed identifier) against the same
   backend, with the same `X-XAI-Token-Auth: xai-grok-cli` marker and the same OAuth
   bearer token, succeeded (see the "Correction" section above and
   `grok-oauth-pi-official.md`). That weakens the inference that this specific header
   must be spoofed to pass; it does not establish that the backend ignores the field
   either, since only one non-`grok-shell` value was tested. This is reverse-engineered
   use of an internal/undocumented API either way (the endpoint and most headers are
   nowhere in xAI's public docs), but "reverse-engineered/undocumented" is a narrower,
   more defensible claim than "impersonation was required and verified."

### Maintenance, security, and legal caveats (judgment, not just quoting)

- **Not xAI-affiliated.** No indication anywhere (npm page, GitHub README, code
  comments) that xAI endorses, sanctions, or is aware of this project. The `@demicodes`
  npm scope and `wspl/demi` GitHub org are independent/community, unrelated to
  `@xai-official`.
- **Depends on xAI's private backend staying stable.** `cli-chat-proxy.grok.com`, its
  request/response shape, and the specific headers it checks are not documented by xAI
  anywhere found in this research; they could change or be hardened against
  non-official clients at any time without notice, silently breaking this provider.
- **Unconfirmed legal/ToS status, not a confirmed violation.** This research did not
  locate xAI's ToS text for the Grok/xAI consumer subscription or for
  `cli-chat-proxy.grok.com` specifically, and did not find any xAI statement permitting
  or forbidding non-CLI clients from using an OAuth session there (with or without the
  `grok-shell` identifier string). Calling this "client impersonation" is accurate only
  for the specific choice this package made (`x-grok-client-identifier: grok-shell`,
  presenting as the literal official client); it is not established that using the same
  OAuth credential and marker header with an honest identifier (as separately
  live-verified for Pi) carries the same characterization. Treat the overall approach as
  **undocumented and unsupported by xAI**, with unknown ToS exposure, rather than as a
  settled violation comparable to enforcement actions seen elsewhere in the industry —
  no such enforcement precedent specific to xAI/Grok was found in this research.
- **Token custody**: the access/refresh tokens are the same ones that authorize the
  user's Grok subscription account broadly (scopes include `conversations:read/write`,
  `workspaces:read/write` — i.e. this is not inference-scoped, it's closer to full
  account access). A bug or compromise in a third-party provider package reading that
  file is a bigger blast radius than a narrowly-scoped API key.
- **Pre-1.0 status**: `demi`'s own README calls the public API unstable pre-release;
  treat `provider-grok-build`'s interfaces as liable to change without a major-version
  signal.

## Could this be wired into Pi?

Mechanically, yes — and as of 2026-10-02 this has been **demonstrated working**, not
just theorized, in either of two ways, both outside anything xAI publicly documents:

1. **`models.json` only** (no extension): point an `openai-responses`-style entry at
   `https://cli-chat-proxy.grok.com/v1`, set `X-XAI-Token-Auth`/`x-grok-*` headers
   (statically, with an honest `x-grok-client-identifier`, e.g. `pi`), and use a
   `!command` for `apiKey` that reads the Grok CLI's own `~/.grok/auth.json` `key`
   field and prints it. **Live-verified**: this exact shape, with a real token obtained
   via `grok login --device-auth`, produced a real `grok-4.7` response and a working
   tool call in a logged Pi session (see `grok-oauth-pi-official.md` and the session
   JSONL cited there). Caveat carried over from the implementation notes reviewed
   alongside this proof: the helper script re-reads the token each request but does
   **not** refresh an expired one — the Grok CLI remains solely responsible for
   refresh/rotation in this shape.
2. **Pi provider extension**: wrap Pi's own native `xai` provider (spreading/overriding
   its `baseUrl`/`headers`/`stream` to target `cli-chat-proxy.grok.com`) rather than
   reimplementing OAuth from scratch, per `docs/custom-provider.md`'s guidance for
   providers needing custom authentication/streaming behavior. A work-in-progress
   implementation along these lines exists at
   `~/.cache/grok-research/worktrees/auth/` (not merged into this repo; reviewed for
   this research but not independently re-verified beyond the facts already
   cross-checked against the installed `pi-ai` source).

Both paths target an **undocumented** xAI endpoint (`cli-chat-proxy.grok.com`); neither
is covered by any xAI public documentation found in this research. That is a statement
about documentation, not a confirmed statement about permission — no source located
here says xAI forbids this, and none says xAI allows it either. This remains a
materially different situation from `bin/claude-token-proxy`, which talks Anthropic's
own documented OAuth + Messages API surfaces for Claude Code: there, the target endpoint
itself is documented; here, the endpoint is not, even though the OAuth client id and
flow now have two independent, legitimate-looking users (the official CLI and Pi's own
bundled library).

## Recommendation

- Present `@demicodes/provider-grok-build`, and the live-verified `models.json`/
  provider-extension approaches above, as **working but xAI-undocumented** integrations
  — not as xAI-sanctioned, and not as confirmed violations either. Avoid both
  overclaims ("this is officially supported") and underclaims ("this is forbidden") that
  this research cannot back with a source.
- If proceeding, prefer an honest client identifier (as the live-verified setup used:
  `x-grok-client-identifier: pi`) over `@demicodes/provider-grok-build`'s choice of
  presenting as `grok-shell`; the live test suggests the honest value is sufficient
  against this backend, which is both simpler to defend and avoids unnecessary
  misrepresentation to xAI's systems.
- Understand the token-custody point still stands regardless of identifier choice: the
  credential carries broader-than-inference scopes (`conversations:*`, `workspaces:*`),
  so a provider-extension implementation with proper, isolated credential handling (as
  Pi's own `CredentialStore` provides, per the implementation notes reviewed) is
  preferable to a loosely-held `models.json` script for anything beyond short-lived
  experimentation.
- The one path xAI's own documentation fully describes remains the `api.x.ai`
  `XAI_API_KEY` route in `grok-oauth-pi-official.md`. It is the lowest-ambiguity choice,
  not the only working or only "clean" one — this document no longer claims the latter.

## Sources

- https://www.npmjs.com/package/@demicodes/provider-grok-build — accessed 2026-10-02,
  page dated 2026-09-24
- https://github.com/wspl/demi — accessed 2026-10-02, page dated 2026-06-27
- https://github.com/wspl/demi/blob/main/packages/provider-grok-build/{auth,chat,
  headers,device-login}.ts — fetched directly via `raw.githubusercontent.com`,
  2026-10-02 (primary source: actual code, not just the README)
- Pi docs: `docs/models.md`, `docs/custom-provider.md` (local install, read 2026-10-02)
- Cross-reference: `docs/handover/research-grok-oauth-pi.md` (this repo's brief) for
  the `bin/claude-token-proxy` analogy being evaluated against
- `@earendil-works/pi-ai` installed package, `dist/auth/oauth/xai.js` and
  `dist/providers/xai.js` — read directly on this host, 2026-10-02
- `~/.cache/grok-research/PROOF.md` and the session log at
  `~/.cache/grok-research/pi-agent/sessions/--home-gustaf--/*.jsonl` — read directly on
  this host, 2026-10-02; session log structure cross-checked for internal consistency
- `~/.cache/grok-research/worktrees/auth/docs/research/grok-pi-auth-implementation.md` —
  read 2026-10-02, a parallel work product, cross-checked only where it overlaps facts
  independently confirmed against the `pi-ai` source
