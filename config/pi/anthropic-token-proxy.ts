import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function anthropicTokenProxy(pi: ExtensionAPI) {
	const url = process.env.PI_ANTHROPIC_PROXY_URL || "http://127.0.0.1:8788";
	pi.registerProvider("anthropic", { baseUrl: url });
}
