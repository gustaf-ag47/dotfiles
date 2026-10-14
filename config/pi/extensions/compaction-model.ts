// compaction-model.ts — write compaction summaries with a cheaper model.
//
// Why (2026-10-14 cost research, $NOTES/Dotfiles/agent-runs/pi-cost-creators-2026-10-14/16-*):
// a compaction request re-sends the summarised history as serialized text, so it
// cannot hit the prompt cache and is billed at the full input price. On Opus 5.5
// that is ~$1 per 260k-token compaction; Sonnet 5.5 halves it. Pi has no setting
// for the summary model, so this hook runs Pi's own `compact()` (same prompt,
// same file tracking) with a cheaper model from the SAME provider (same auth and
// account pool), and falls back to native compaction on any failure.
//
//   PI_COMPACTION_MODEL=off               disable (native compaction)
//   PI_COMPACTION_MODEL=provider/model-id force a specific summariser

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Preferred summarisers per provider, first available wins. Only used when
// cheaper (input price) than the session's current model.
export const CANDIDATES: Record<string, string[]> = {
	anthropic: ["claude-sonnet-5-5", "claude-sonnet-5"],
	// gpt-6-astra is $10/MTok input; 6.1-sol is $2 on the same ChatGPT login.
	"openai-codex": ["gpt-6.1-sol", "gpt-6-sol"],
};

// The summary budget is min(0.8 * reserveTokens, maxTokens). A large
// reserveTokens override (used to compact early on 1M-window models) would
// otherwise allow a 128k-token summary; keep Pi's default ~13k budget.
export const SUMMARY_RESERVE_TOKENS = 16384;

type ModelLike = { provider: string; id: string; cost?: { input?: number } };
type Registry = { find(provider: string, id: string): ModelLike | undefined };

export function pickSummaryModel(current: ModelLike | undefined, registry: Registry, env: Record<string, string | undefined>): ModelLike | undefined {
	const override = (env.PI_COMPACTION_MODEL ?? "").trim();
	if (override === "off") return undefined;
	if (override) {
		const slash = override.indexOf("/");
		if (slash <= 0) return undefined;
		return registry.find(override.slice(0, slash), override.slice(slash + 1));
	}
	if (!current) return undefined;
	const currentPrice = current.cost?.input ?? 0;
	for (const id of CANDIDATES[current.provider] ?? []) {
		if (id === current.id) return undefined;
		const model = registry.find(current.provider, id);
		if (model && (model.cost?.input ?? Infinity) < currentPrice) return model;
	}
	return undefined;
}

type CompactFn = (preparation: any, model: any, apiKey?: string, headers?: any, customInstructions?: string, signal?: AbortSignal, thinkingLevel?: any, streamFn?: any, env?: Record<string, string>) => Promise<any>;

export function createCompactionModel(loadCompact: () => Promise<CompactFn>, env: Record<string, string | undefined> = process.env) {
	return function (pi: ExtensionAPI) {
		pi.on("session_before_compact", async (event: any, ctx: any) => {
			const model = pickSummaryModel(ctx.model, ctx.modelRegistry, env);
			if (!model) return;
			try {
				const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
				if (!auth?.ok) return;
				const target = auth.baseUrl ? { ...model, baseUrl: auth.baseUrl } : model;
				const preparation = {
					...event.preparation,
					settings: { ...event.preparation.settings, reserveTokens: SUMMARY_RESERVE_TOKENS },
				};
				const compact = await loadCompact();
				const compaction = await compact(preparation, target, auth.apiKey, auth.headers, event.customInstructions, event.signal, undefined, undefined, auth.env);
				ctx.ui?.notify?.(`Compaction summary written by ${model.provider}/${model.id}`, "info");
				return { compaction };
			} catch (error) {
				if (event.signal?.aborted) return;
				const message = error instanceof Error ? error.message : String(error);
				ctx.ui?.notify?.(`compaction-model: ${message}; using native compaction`, "warning");
				return;
			}
		});
	};
}

export default createCompactionModel(async () => (await import("@earendil-works/pi-coding-agent")).compact);
