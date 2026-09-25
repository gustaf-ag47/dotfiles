import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { Model } from "@earendil-works/pi-ai";
import { anthropicProvider } from "@earendil-works/pi-ai/providers/anthropic";
import { PROXY_CREDENTIAL, proxyOptions, proxyUrl } from "../lib/anthropic-route.mjs";

export default function (pi: ExtensionAPI) {
  // The compatibility launcher owns its explicit auto/force/direct route.
  if (process.env.PI_DOTFILES_LEGACY_CLAUDE_PID === String(process.pid)) return;
  const native = anthropicProvider();
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
