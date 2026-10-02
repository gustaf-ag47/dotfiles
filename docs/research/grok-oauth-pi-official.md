# Grok OAuth for Pi — official xAI surface

Accessed: 2026-10-02. Angle: does xAI officially offer OAuth for Grok API/Pi use, as
analogous to Anthropic's Claude-subscription OAuth that `bin/claude-token-proxy` brokers?

## Correction (2026-10-02, post-live-verification)

The original version of this document asserted categorically that no OAuth path into
Grok existed for Pi beyond the official `grok` CLI, and recommended the `api.x.ai`
API-key route as the sole "ToS-clean" option. That framing has been corrected below
after two things verified directly on this host:

1. **Pi's own vendored inference library ships a native xAI OAuth provider.**
   `@earendil-works/pi-ai` (installed at
   `~/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai`,
   matching Pi 0.99.1) contains `dist/auth/oauth/xai.js` and `dist/providers/xai.js`,
   inspected directly on 2026-10-02. The native `xai` provider's OAuth config has
   `loginLabel: "Sign in with SuperGrok or X Premium"`, `isSubscription: true`, and
   implements a device-code flow against `auth.x.ai` using client id
   `b1a00492-073a-47ea-816f-4c329264a828` — the **same** client id the official `grok`
   CLI uses. This is a real, shipped Pi feature, not a hypothetical. It was missed in
   the first pass of this research because the initial searches focused on `api.x.ai`
   docs and did not inspect Pi's own bundled provider code.
2. **A live, working integration was demonstrated and logged** (not merely coded): a
   custom `models.json` provider entry (`grok-build-oauth`, `api: "openai-responses"`,
   `baseUrl: "https://cli-chat-proxy.grok.com/v1"`, `apiKey` sourced via `!command` from
   a script reading the official Grok CLI's own `~/.grok/auth.json`) performed a real
   inference call *and* a real tool-call round trip with `grok-4.7`. Verified directly
   by reading the session's own JSONL log
   (`~/.cache/grok-research/pi-agent/sessions/.../*.jsonl`, 2026-10-02): it shows
   `"provider":"grok-build-oauth"`, `"model":"grok-4.7"`, `"api":"openai-responses"`,
   a `toolCall`/`toolResult` pair for `printf GROK_PI_OAUTH_TOOL_OK`, and a matching
   final assistant reply — internally consistent with genuine Pi output (response ids,
   reasoning signatures, usage accounting), not just an unverifiable written claim.

**What remains unverified** (flagging explicitly rather than asserting either way):

- Whether a token obtained through *Pi's own* native `/login` for the `xai` provider
  (device-code flow, same client id) is accepted by `api.x.ai` (the provider's default
  `baseUrl`) for billed inference. The live-tested path instead reused a token from the
  official Grok CLI's own login (`grok login --device-auth`) against the undocumented
  `cli-chat-proxy.grok.com` host with a custom `baseUrl` override. These are two
  different combinations; only the second was live-tested.
- Whether xAI's terms of service for the Grok/X subscription or the Inference API
  explicitly permit or forbid using an OAuth-obtained session against
  `cli-chat-proxy.grok.com` from a client other than the official CLI/TUI, even when the
  client honestly identifies itself (as the verified setup does, via
  `x-grok-client-identifier: pi`, rather than impersonating the CLI). This research did
  not locate xAI's specific ToS text for that scenario. **No documented xAI support was
  found for third-party use of `cli-chat-proxy.grok.com`; this is different from having
  proven it is disallowed or unsafe.** Avoid stating either absence of permission or
  presence of prohibition as settled fact.
- Longevity: whether `cli-chat-proxy.grok.com`'s behavior, required headers, or
  tolerance for non-CLI clients remains stable over time is unknown; it is an internal,
  undocumented backend that could change without notice.

## Bottom line (narrowed per the above)

xAI publishes **two** separate, non-interchangeable auth surfaces in its own docs:

1. **`api.x.ai` (the paid Inference API / xai-sdk)** — API-key only. You create a key at
   `console.x.ai` and send `Authorization: Bearer $XAI_API_KEY`. No OAuth, no
   subscription-login option. This is the surface a Pi `models.json` "openai-completions"
   or native-xAI entry would normally target.
   - Source: https://docs.x.ai/docs/overview (accessed 2026-10-02, page dated
     2026-08-22) — curl example uses `Authorization: Bearer $XAI_API_KEY`.
   - Source: https://docs.x.ai/docs/tutorial (accessed 2026-10-02, page dated
     2026-09-25) — "Generate an API key via the API Keys page… export it or add it as an
     environment variable."
   - **Caveat added post-correction**: Pi's native `xai` provider *does* offer an OAuth
     login ("Sign in with SuperGrok or X Premium") pointed at this same `api.x.ai`
     `baseUrl` by default (see provider code citation above). xAI's own docs still only
     describe key-based auth for this surface, and no test in this research exercised
     that native-OAuth-against-`api.x.ai` combination end-to-end, so whether it actually
     authenticates against the documented API is unconfirmed either way — not disproven.

2. **Grok Build (the official Grok coding-agent CLI, `grok`)** — this one *does* use a
   browser-based OAuth/device-login flow by default, tied to a subscription account
   rather than a metered API key:
   - Install: `curl -fsSL https://x.ai/cli/install.sh | bash` or `npm i -g
     @xai-official/grok`.
   - "On first launch, Grok opens a browser for authentication. In non-browser
     environments, use an API key: `export XAI_API_KEY=...`"
   - Source: https://docs.x.ai/build/overview (accessed 2026-10-02, page dated
     2026-03-02).
   - Source: https://www.npmjs.com/package/@xai-official/grok (accessed 2026-10-02,
     page dated 2026-09-30) — same "opens your browser to authenticate" / API-key
     fallback language, confirms this is the real, current official package (not a
     squatted name).

So there **is** an official OAuth login (confirmed twice over: in xAI's own `grok` CLI
docs, and independently as code shipped inside Pi's own dependency tree), but xAI's
*published documentation* only describes it in the context of the `grok` CLI product
talking to xAI's own backend (`cli-chat-proxy.grok.com`, confirmed in the
community-provider source reviewed in the companion `-community.md` file, and in the
live-logged Pi session above), not the public Inference API. xAI has not published this
as a general third-party OAuth service and has no documented OAuth client-registration
process for parties other than its own CLI. That is a statement about **documentation
gaps**, not a claim that xAI forbids other uses — no such prohibition was located, and
none should be inferred without xAI's own ToS text.

## Does Pi need a provider extension, or can `models.json` just point at it?

From Pi's own docs (`docs/models.md` in the Pi install, read 2026-10-02):

- A **static API key** (e.g. an `XAI_API_KEY` from console.x.ai) is exactly the case
  `models.json` is designed for — `api: "openai-completions"`/anthropic-compatible entry
  with the `apiKey` field referencing `$XAI_API_KEY` (or a `!command`). This is already enough to use
  `grok-4.7` etc. on the real `api.x.ai` surface in Pi today, with no extension needed,
  using the auth method xAI's own docs describe for that surface — just not OAuth.
- **Correction**: Pi does not need a third-party extension to get xAI *OAuth into Pi's
  own credential store* at all — a native `xai` OAuth provider already ships inside
  Pi's bundled `@earendil-works/pi-ai` dependency (confirmed by direct file inspection
  above). What *would* need either a provider extension or a hand-wired `models.json`
  override is redirecting that OAuth-backed traffic to the undocumented
  `cli-chat-proxy.grok.com` host with its custom headers — i.e. the extension/override
  is about the non-standard **endpoint**, not about obtaining OAuth credentials in the
  first place. The live-verified setup used the `models.json`-only path (see below), not
  a provider extension, with the credential supplied by the official Grok CLI's own
  login rather than Pi's native `/login` for `xai`.
- A **provider with a custom protocol or authentication flow** (token refresh, custom
  headers, non-standard endpoint) is explicitly called out as needing a **provider
  extension**, not `models.json`: "Use an extension when the provider needs custom
  streaming, model discovery, or authentication behavior" (`docs/models.md`,
  "Add a custom provider" section; see `docs/custom-provider.md` for the extension
  contract).
- `models.json` *can* hold a credential via a `!command` for `apiKey` (run at request
  time, not cached) and can set arbitrary extra headers with env/command interpolation.
  This is exactly what the live-verified setup used: a `models.json` entry
  (`api: "openai-responses"`, `baseUrl: "https://cli-chat-proxy.grok.com/v1"`,
  an `apiKey` command running the token helper to read the Grok CLI's own `~/.grok/auth.json`,
  plus static `X-XAI-Token-Auth` / `x-grok-client-identifier: pi` /
  `x-grok-client-version` headers) — confirmed working for real inference and a tool
  call, per the session log cited above. No provider extension was required for that
  specific, already-logged-in, no-refresh-needed case; a provider extension would add
  proper refresh/locking semantics and is what a follow-on implementation report
  (`~/.cache/grok-research/worktrees/auth/docs/research/grok-pi-auth-implementation.md`,
  not yet merged into this repo) builds, wrapping Pi's native `xai` provider rather than
  reimplementing OAuth from scratch. Either way, `cli-chat-proxy.grok.com` itself remains
  an **undocumented** xAI endpoint — nothing in xAI's published docs describes it, grants
  it, or forbids it for non-CLI clients.

## Recommendation

- For Grok access in Pi backed only by xAI's publicly documented surface: use the
  `api.x.ai` Inference API with an `XAI_API_KEY` via `models.json` (or Pi's native `xai`
  provider's API-key path). This is the one path fully described in xAI's own docs. It
  is **not** proven to be the only permitted path, nor is OAuth-via-`cli-chat-proxy.grok.com`
  proven impermissible — it is simply the one xAI documents, so it is the lowest-
  ambiguity choice if that matters more than avoiding per-token billing.
- If the goal is to ride a Grok subscription instead of metered billing (the
  "like Claude-via-Pro-OAuth" ask): this has now been **demonstrated working**, live, via
  a `models.json` entry pointed at `cli-chat-proxy.grok.com` using a token sourced from
  the official Grok CLI's own login, with Pi honestly identifying itself
  (`x-grok-client-identifier: pi`). This is a real, functioning option today, not merely
  theoretical — but it depends on an **undocumented** xAI backend that could change
  without notice, and no source found in this research confirms xAI's position (for or
  against) on non-CLI clients using it. Treat it as "works today, unsupported and
  unconfirmed-permitted," not as "ToS-clean" or as "against the rules" — neither claim
  is backed by a located xAI source. See `grok-oauth-pi-community.md` for the detailed
  mechanics, the distinction from the impersonation-style community provider, and
  caveats.

## Sources

- https://docs.x.ai/docs/overview — accessed 2026-10-02, content dated 2026-08-22
- https://docs.x.ai/docs/tutorial — accessed 2026-10-02, content dated 2026-09-25
- https://docs.x.ai/docs/api-reference — accessed 2026-10-02, content dated 2026-09-14
- https://docs.x.ai/build/overview — accessed 2026-10-02, content dated 2026-03-02
- https://x.ai/cli — accessed 2026-10-02, content dated 2026-01-01
- https://www.npmjs.com/package/@xai-official/grok — accessed 2026-10-02, content dated
  2026-09-30
- Pi docs: `docs/models.md`, `docs/custom-provider.md` (local install, read 2026-10-02)
- `https://docs.x.ai/docs/guides/authentication` — checked, returns HTTP 404 (no such
  page; ruled out as a source of an "OAuth" doc).
- `@earendil-works/pi-ai` installed package, `dist/auth/oauth/xai.js` and
  `dist/providers/xai.js` — read directly on this host, 2026-10-02 (primary source: the
  actual shipped code, not a secondhand claim about it).
- `~/.cache/grok-research/PROOF.md`, `~/.cache/grok-research/pi-agent/models.json`,
  `~/.cache/grok-research/oauth-token.py`, and the session log at
  `~/.cache/grok-research/pi-agent/sessions/--home-gustaf--/*.jsonl` — all read directly
  on this host, 2026-10-02. The session log's internal structure (response ids, usage
  accounting, matching tool-call/tool-result pair) was cross-checked for consistency
  rather than taking the prose summary in `PROOF.md` at face value.
- `~/.cache/grok-research/worktrees/auth/docs/research/grok-pi-auth-implementation.md` —
  read 2026-10-02; a parallel work product, not independently re-verified line-by-line
  beyond the client-id/host facts cross-checked against the `pi-ai` source directly.
