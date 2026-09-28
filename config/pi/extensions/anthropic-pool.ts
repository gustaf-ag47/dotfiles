// anthropic-pool: make plain `pi` use the local claude-token-proxy for every
// Anthropic request, so no wrapper (`pi-claude-sub`) is needed.
//
// What this replaces (bin/pi-claude-sub, retired 2026-09-27):
//   1. `--api-key sk-ant-oat01-…` placeholder: pi decides "subscription auth" from
//      the `sk-ant-oat` prefix (Claude Code identity system block + OAuth beta
//      header). Registering the placeholder as the anthropic provider's apiKey
//      triggers the same path, but provider-scoped: a Codex or DeepSeek session
//      never sees it, and `/model anthropic/…` works mid-session.
//   2. anthropic-token-proxy.ts: baseUrl → proxy; `x-cc-proxy-fallback: none` so
//      an exhausted pool surfaces as an error llm-failover.ts can act on instead
//      of being silently served (and billed) by DeepSeek. `x-cc-proxy-session`
//      names this pi session so the proxy can keep it on one account (prompt
//      cache) while spreading concurrent sessions across accounts.
//   3. anthropic-oauth-claude-code-identity.ts: Anthropic rejects OAuth requests
//      that carry pi's harness prompt as a second system block, so keep only the
//      Claude Code identity in `system` and move the harness prompt into the
//      first user message. Scoped to anthropic requests here.
//
// Opt out (direct Anthropic with your own credential): PI_ANTHROPIC_POOL=off.
// Override the proxy: PI_ANTHROPIC_PROXY_URL=http://127.0.0.1:8790 or CC_PROXY_PORT
// (same variables llm-failover.ts reads, so both always agree on the origin).
//
// Pure helpers are exported for tests/unit/test_anthropic_pool.mjs.
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export const ANTHROPIC = "anthropic";
/** Never a real credential: the proxy drops the inbound Authorization and injects its own. */
export const PLACEHOLDER_KEY = "sk-ant-oat01-proxy-injects-the-real-credential";
export const CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude.";
export const STATUS_TIMEOUT_MS = 1_500;
export const SESSION_HEADER = "x-cc-proxy-session";

/** Proxy origin from the environment, or null when the operator opted out of the pool. */
export function proxyOrigin(env: NodeJS.ProcessEnv = process.env): string | null {
	const pool = (env.PI_ANTHROPIC_POOL ?? "on").trim().toLowerCase();
	if (["0", "off", "none", "false", "no"].includes(pool)) return null;
	return new URL(env.PI_ANTHROPIC_PROXY_URL || `http://127.0.0.1:${env.CC_PROXY_PORT || "8788"}`).origin;
}

type SystemBlock = { type?: string; text?: string };
type Payload = { system?: SystemBlock[]; messages?: any[] };

/**
 * Keep only the Claude Code identity in `system`; prepend the second system
 * block (pi's harness prompt) to the first user message. Returns null when the
 * payload is not the OAuth shape this workaround targets.
 */
export function moveHarnessPromptIntoFirstMessage(payload: unknown): Payload | null {
	const p = payload as Payload;
	if (!p || !Array.isArray(p.system) || !Array.isArray(p.messages)) return null;
	if (p.system[0]?.text !== CLAUDE_CODE_IDENTITY) return null;
	const harness = p.system[1]?.text;
	if (typeof harness !== "string" || !harness.trim()) return null;

	const next = structuredClone(p) as Required<Payload>;
	next.system = [next.system[0]];
	const prefix = `${harness}\n\n`;
	const first = next.messages[0];
	if (!first) {
		next.messages = [{ role: "user", content: prefix.trim() }];
	} else if (typeof first.content === "string") {
		first.content = prefix + first.content;
	} else if (Array.isArray(first.content) && first.content[0]?.type === "text") {
		first.content[0] = { ...first.content[0], text: prefix + (first.content[0].text || "") };
	} else {
		next.messages.unshift({ role: "user", content: prefix.trim() });
	}
	return next;
}

/** Stable per-session key for proxy affinity; never includes user content. */
export function sessionKey(ctx: { sessionManager?: { getSessionId?: () => string } }, fallback: string): string {
	try {
		const id = ctx.sessionManager?.getSessionId?.();
		if (typeof id === "string" && id) return `pi-${id}`;
	} catch { /* fall through */ }
	return fallback;
}

/** One-line verdict for the startup check; null means nothing to say. */
export function statusLine(status: { available?: number; tokens?: unknown[] } | null, origin: string): string | null {
	if (status === null) return `⚠ anthropic pool: claude-token-proxy not reachable at ${origin} — Anthropic models will fail; Codex/DeepSeek unaffected (systemctl --user start claude-token-proxy)`;
	if ((status.available ?? 0) <= 0) return "⚠ anthropic pool: no OAuth account is currently available (run llm-usage for reset times)";
	return null;
}

export async function fetchStatus(origin: string, fetchImpl: typeof fetch = fetch, timeoutMs = STATUS_TIMEOUT_MS) {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const res = await fetchImpl(`${origin}/_status`, { signal: controller.signal, headers: { accept: "application/json" } });
		if (!res.ok) return null;
		return (await res.json()) as { available?: number; tokens?: unknown[] };
	} catch {
		return null;
	} finally {
		clearTimeout(timer);
	}
}

export default function anthropicPool(pi: ExtensionAPI) {
	const origin = proxyOrigin();
	if (origin === null) return; // explicit opt-out: pi's built-in anthropic provider, your own credential

	pi.registerProvider(ANTHROPIC, {
		baseUrl: origin,
		apiKey: PLACEHOLDER_KEY,
		headers: { "x-cc-proxy-fallback": "none" },
	});

	// One key per pi session (falls back to one per process). Sent only to the
	// proxy: the anthropic provider is the only one whose baseUrl is the proxy.
	const processKey = `pi-${process.pid}-${Date.now().toString(36)}`;
	pi.on("before_provider_headers", (event, ctx: ExtensionContext) => {
		if (ctx.model?.provider !== ANTHROPIC) return;
		event.headers[SESSION_HEADER] = sessionKey(ctx, processKey);
	});

	pi.on("before_provider_request", (event, ctx: ExtensionContext) => {
		if (ctx.model?.provider !== ANTHROPIC) return;
		return moveHarnessPromptIntoFirstMessage(event.payload) ?? undefined;
	});

	// Fail loudly, not closed: Codex/DeepSeek sessions must start even when the
	// proxy is down, and a warning is enough for an Anthropic session to act on.
	pi.on("session_start", async (_event, ctx: ExtensionContext) => {
		if (ctx.model?.provider !== ANTHROPIC) return;
		const line = statusLine(await fetchStatus(origin), origin);
		if (!line) return;
		if (ctx.hasUI) ctx.ui.notify(line, "warning");
		else console.error(line);
	});
}
