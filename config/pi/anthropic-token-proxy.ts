import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// pi does its own cross-provider failover (extensions/llm-failover.ts), so ask the
// proxy NOT to silently serve an exhausted pool from DeepSeek: that answer would be
// labelled and priced as Claude and the extension would never see the error.
export default function anthropicTokenProxy(pi: ExtensionAPI) {
	const url = process.env.PI_ANTHROPIC_PROXY_URL || "http://127.0.0.1:8788";
	pi.registerProvider("anthropic", { baseUrl: url, headers: { "x-cc-proxy-fallback": "none" } });
}
