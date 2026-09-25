// This compatibility rewrite belongs to the Anthropic transport, not a global
// turn hook: registry calls (e.g. /goal evaluators) need the same behavior.
export const PROXY_CREDENTIAL = "sk-ant-oat01-proxy-injects-the-real-credential";

export function proxyUrl(env = process.env) {
  const url = new URL(env.PI_ANTHROPIC_PROXY_URL || `http://127.0.0.1:${env.CC_PROXY_PORT || "8788"}`);
  if (url.protocol !== "http:" || !["127.0.0.1", "[::1]"].includes(url.hostname)
      || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("Pi Anthropic proxy must be an HTTP loopback origin (127.0.0.1 or [::1]). No direct fallback.");
  }
  return url.origin;
}

export function claudeIdentityPayload(payload) {
  if (!payload || !Array.isArray(payload.system) || !Array.isArray(payload.messages)
      || payload.system[0]?.text !== "You are Claude Code, Anthropic's official CLI for Claude."
      || payload.system.length < 2) return payload;
  const instructions = payload.system.slice(1).map(block => block.text || "").join("\n\n").trim();
  if (!instructions) return payload;
  const next = structuredClone(payload);
  next.system = [next.system[0]];
  const first = next.messages[0];
  const prefix = `${instructions}\n\n`;
  if (first?.role === "user" && typeof first.content === "string") {
    first.content = prefix + first.content;
  } else if (first?.role === "user" && Array.isArray(first.content) && first.content[0]?.type === "text") {
    first.content[0].text = prefix + first.content[0].text;
  } else {
    next.messages.unshift({ role: "user", content: prefix.trim() });
  }
  return next;
}

export function proxyOptions(options = {}, env = process.env) {
  // Drop any caller-supplied auth headers before adding the local placeholder.
  const headers = Object.fromEntries(Object.entries(options.headers || {})
    .filter(([key]) => !["authorization", "x-api-key"].includes(key.toLowerCase())));
  return {
    ...options,
    apiKey: PROXY_CREDENTIAL,
    headers,
    onPayload: async (payload, model) => {
      proxyUrl(env); // Reject unsafe config at request time, never fall back.
      const transformed = await options.onPayload?.(payload, model);
      return claudeIdentityPayload(transformed === undefined ? payload : transformed);
    },
  };
}
