// grok-build: Pi provider for the Grok CLI's own OAuth-gated inference backend
// (cli-chat-proxy.grok.com), *not* the paid api.x.ai endpoint. Verified live
// 2026-10-02: GET https://cli-chat-proxy.grok.com/v1/models returned HTTP 200
// for an OAuth bearer carrying X-XAI-Token-Auth: xai-grok-cli with model
// grok-4.7 (api_backend=responses, 256000 context, 500000 optional). See
// operator notes: grok-pi-auth-implementation.md.
//
// Pi's bundled @earendil-works/pi-ai already ships a native "xai" provider
// (providers/xai.ts) whose OAuth flow uses the *same* client_id
// (b1a00492-073a-47ea-816f-4c329264a828), the same auth.x.ai device-code/token
// endpoints, and a scope that includes "grok-cli:access" -- the official Grok
// CLI's own OAuth app registration. That flow's login/refresh/token-storage is
// tested, cross-process-locked code (Pi's CredentialStore.modify) that we do
// not want to reimplement. We reuse it unmodified under the distinct provider
// id "grok-build", so credentials live in exactly one place (Pi's own
// ~/.pi/agent/auth.json, keyed by provider id) instead of a second store that
// could race the Grok CLI's own refresh of ~/.grok/auth.json.
//
// NOTE: logging in via `/login grok-build` performs Pi's own device-code OAuth
// round trip against auth.x.ai; it does not read `grok login`'s token. That a
// Pi-obtained token is accepted by cli-chat-proxy.grok.com has not been
// live-tested from this provider -- only a `grok login --device-auth` token
// was proven live. Flagged for live verification; see the report.
//
// A secondary, strictly read-only credential path is also offered: the
// `apiKey` command bridge below shells out to `bin/grok-oauth-token`, which
// reads the Grok CLI's own `$GROK_HOME/auth.json` (default `~/.grok`) and
// prints its current access token. That script never writes to the CLI's auth
// file and never refreshes it -- the Grok CLI remains the sole owner of that
// file's refresh/rotation. Pi re-reads it fresh on every request instead of
// caching a copy, so a given token is still refreshed in only one place.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { Model, ProviderHeaders, RefreshModelsContext } from "@earendil-works/pi-ai";
// Pi's extension loader aliases providers/all explicitly; individual provider
// imports can be shadowed by its pi-ai root -> compat.js alias.
import { builtinProviders } from "@earendil-works/pi-ai/providers/all";
import { existsSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { resolveGrokCliBridgeToken } from "../lib/grok-cli-bridge.mjs";

export const GROK_BUILD_PROVIDER_ID = "grok-build";
export const GROK_BUILD_BASE_URL = "https://cli-chat-proxy.grok.com/v1";
// Matches the official Grok CLI release this was verified against. Bump this
// alongside re-verification against a newer `grok --version`; do not guess.
export const GROK_CLI_VERSION = "1.0.46";

export const GROK_BUILD_HEADERS: ProviderHeaders = {
  "X-XAI-Token-Auth": "xai-grok-cli",
  "x-grok-client-identifier": "pi",
  "x-grok-client-version": GROK_CLI_VERSION,
};

// Static baseline so the provider lists a model offline/pre-refresh, matching
// the live /models response recorded in operator notes: grok-pi-auth-implementation.md.
// No cost fields: this is a subscription-gated CLI backend, not metered
// api.x.ai billing, and we must not imply a price that doesn't apply here.
export const GROK_4_7_MODEL: Model<"openai-responses"> = {
  id: "grok-4.7",
  name: "Grok 4.7 (CLI OAuth)",
  api: "openai-responses",
  provider: GROK_BUILD_PROVIDER_ID,
  baseUrl: GROK_BUILD_BASE_URL,
  headers: GROK_BUILD_HEADERS,
  reasoning: true,
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 256000,
  maxTokens: 8192,
  thinkingLevelMap: {
    off: null,
    minimal: null,
    low: "low",
    medium: "medium",
    high: "high",
    xhigh: "xhigh",
    max: null,
  },
};

export function routeToGrokBuild(model: Model<"openai-responses">): Model<"openai-responses"> {
  return {
    ...model,
    provider: GROK_BUILD_PROVIDER_ID,
    baseUrl: GROK_BUILD_BASE_URL,
    headers: { ...model.headers, ...GROK_BUILD_HEADERS },
  };
}

// `context.credential` in refreshModels is the stored credential, not the
// resolved apiKey.resolve() output -- for the CLI bridge method the stored
// value is only a marker (see apiKey.login() below), so resolve a real token
// the same way apiKey.resolve() does rather than sending the marker as a
// bearer token.
function credentialApiKey(credential: RefreshModelsContext["credential"], bridgeScript: string): string | undefined {
  if (!credential) return undefined;
  if (credential.type === "oauth") return credential.access;
  if (credential.type === "api_key") {
    try {
      return resolveGrokCliBridgeToken(bridgeScript);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

// Guard: only ever fetch a model catalog from the fixed, known cli-chat-proxy
// host, and never follow a redirect off it.
export async function fetchGrokModels(
  signal: AbortSignal,
  apiKey: string | undefined,
): Promise<Model<"openai-responses">[] | null> {
  if (!apiKey) return null;
  let response: Response;
  try {
    response = await fetch(`${GROK_BUILD_BASE_URL}/models`, {
      method: "GET",
      redirect: "error",
      signal,
      headers: { Authorization: `Bearer ${apiKey}`, ...GROK_BUILD_HEADERS },
    });
  } catch {
    return null; // offline or network error: caller keeps the prior/static list
  }
  if (!response.ok) return null;
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return null;
  }
  const list = Array.isArray((body as { data?: unknown[] })?.data) ? (body as { data: unknown[] }).data : null;
  if (!list) return null;
  const models: Model<"openai-responses">[] = [];
  for (const entry of list) {
    const id = (entry as { id?: unknown })?.id;
    if (typeof id !== "string" || !id) continue;
    // Only trust full capability metadata for the model we have verified live;
    // list any other id conservatively rather than inventing cost/context
    // numbers we have not confirmed.
    models.push(id === GROK_4_7_MODEL.id ? GROK_4_7_MODEL : { ...GROK_4_7_MODEL, id, name: `${id} (CLI OAuth)` });
  }
  return models.length > 0 ? models : null;
}

export default function (pi: ExtensionAPI) {
  const native = builtinProviders().find((provider) => provider.id === "xai");
  if (!native) throw new Error("Installed Pi does not include the xai provider");
  const bridgeScript = resolve(dirname(realpathSync(__filename)), "../../../bin/grok-oauth-token");

  let models: Model<"openai-responses">[] = [GROK_4_7_MODEL];

  pi.registerProvider({
    ...native,
    id: GROK_BUILD_PROVIDER_ID,
    name: "Grok CLI (OAuth, cli-chat-proxy.grok.com)",
    baseUrl: GROK_BUILD_BASE_URL,
    headers: GROK_BUILD_HEADERS,
    models: [GROK_4_7_MODEL],
    auth: {
      // Primary: Pi's own OAuth login/refresh, reusing the native xai flow
      // object wholesale (same client_id/scope/endpoints, tested refresh and
      // cross-process locking). Stored under this provider's own id, so it
      // never collides with a separately configured "xai" credential.
      oauth: native.auth.oauth!,
      // Secondary: read-only bridge to an existing `grok login` session. The
      // Grok CLI remains the sole writer/refresher of ~/.grok/auth.json; we
      // only ever execute the bridge script to read its current access
      // token, fresh, on every request -- nothing is stored or cached here.
      apiKey: {
        name: "Grok CLI session (read-only, ~/.grok/auth.json via $GROK_HOME)",
        async login() {
          // Records that this method was selected; carries no secret. resolve()
          // ignores stored credential content and always re-executes the script.
          return { type: "api_key" as const, key: "grok-cli-session-bridge" };
        },
        async resolve() {
          // Auth contract: `undefined` means "not configured". A missing Grok
          // CLI auth file is "never ran grok login", not a failure - without
          // this check pi's startup availability refresh executed the bridge
          // and printed its error banner in every session on machines that
          // simply don't use Grok (2026-10-03). A present-but-broken file
          // still throws loudly below, which is the correct signal.
          const grokHome = process.env.GROK_HOME || join(homedir(), ".grok");
          if (!existsSync(join(grokHome, "auth.json"))) return undefined;
          return { auth: { apiKey: resolveGrokCliBridgeToken(bridgeScript) }, source: "Grok CLI session (grok login)" };
        },
      },
    },
    getModels: () => models,
    async refreshModels(context: RefreshModelsContext) {
      if (!context.allowNetwork) return;
      const apiKey = credentialApiKey(context.credential, bridgeScript);
      const fetched = await fetchGrokModels(context.signal, apiKey);
      if (!fetched) return; // keep the static/prior list on failure or when unconfigured
      const next = fetched;
      await context.publish({ update: () => { models = next; } });
    },
    stream: (model: Model<"openai-responses">, context, options) => native.stream(routeToGrokBuild(model), context, options),
    streamSimple: (model: Model<"openai-responses">, context, options) =>
      native.streamSimple(routeToGrokBuild(model), context, options),
  });
}
