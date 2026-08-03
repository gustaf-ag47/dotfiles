import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

/**
 * Workaround for Anthropic OAuth subscription tokens in pi.
 *
 * Anthropic appears to reject OAuth subscription requests as "third-party apps"
 * when pi sends its normal harness/system prompt as a second system block after
 * the Claude Code identity block.
 *
 * This extension keeps only the official Claude Code identity in `system` and
 * moves pi's harness prompt into the first user message.
 */
export default function anthropicOauthClaudeCodeIdentityPatch(pi: ExtensionAPI) {
	pi.on("before_provider_request", (event) => {
		const payload: any = event.payload;
		if (!payload || !Array.isArray(payload.system) || !Array.isArray(payload.messages)) return;

		const firstSystem = payload.system[0]?.text;
		const secondSystem = payload.system[1]?.text;

		if (firstSystem !== "You are Claude Code, Anthropic's official CLI for Claude.") return;
		if (typeof secondSystem !== "string" || !secondSystem.trim()) return;

		const next = structuredClone(payload);
		next.system = [next.system[0]];

		const prefix = `${secondSystem}\n\n`;
		const firstMessage = next.messages[0];

		if (!firstMessage) {
			next.messages = [{ role: "user", content: prefix.trim() }];
			return next;
		}

		if (typeof firstMessage.content === "string") {
			firstMessage.content = prefix + firstMessage.content;
			return next;
		}

		if (
			Array.isArray(firstMessage.content) &&
			firstMessage.content.length > 0 &&
			firstMessage.content[0]?.type === "text"
		) {
			firstMessage.content[0] = {
				...firstMessage.content[0],
				text: prefix + (firstMessage.content[0].text || ""),
			};
			return next;
		}

		next.messages.unshift({ role: "user", content: prefix.trim() });
		return next;
	});
}
