import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { Model } from "@earendil-works/pi-ai";
// Use the explicitly aliased entrypoint in Pi's extension loader.
import { builtinProviders } from "@earendil-works/pi-ai/providers/all";
import { PROXY_CREDENTIAL, proxyOptions, proxyUrl } from "./anthropic-route.mjs";

// Provider FACTORY for SDK embedders (jev-ultrafast's _pi_text_worker), not a
// live pi extension: anthropic-pool.ts owns the anthropic provider in real pi
// sessions. Living in lib/ keeps pi-setup from linking it into extensions/,
// which double-registered the provider with load-order-dependent results.
export default function (pi: ExtensionAPI) {
  const native = builtinProviders().find((provider) => provider.id === "anthropic");
  if (!native) throw new Error("Installed Pi does not include the anthropic provider");
  // Invalid config must fail on a request, not unload this extension and expose
  // the native direct route. Offline listing and unrelated providers still work.
  let endpoint = "http://127.0.0.1:9";
  try { endpoint = proxyUrl(); } catch { /* validated again before sending */ }
  const routed = (model: Model<"anthropic-messages">) => ({
    ...model,
    baseUrl: endpoint,
    headers: Object.fromEntries(Object.entries(model.headers || {})
      .filter(([key]) => !["authorization", "x-api-key"].includes(key.toLowerCase()))),
  });
  pi.registerProvider({
    ...native,
    name: "Anthropic (local subscription pool)",
    baseUrl: endpoint,
    auth: {
      apiKey: {
        name: "Local Claude proxy (credentials managed by claude-token-proxy)",
        async login() { return { type: "api_key" as const, key: PROXY_CREDENTIAL }; },
        async resolve() {
          return { auth: { apiKey: PROXY_CREDENTIAL }, source: "local Claude proxy" };
        },
      },
    },
    getModels: () => native.getModels().map(routed),
    stream: (model, context, options) => native.stream(routed(model), context, proxyOptions(options)),
    streamSimple: (model, context, options) => native.streamSimple(routed(model), context, proxyOptions(options)),
  });
}
