import { uuidv7 } from "@earendil-works/pi-ai";
import type {
	ExtensionAPI,
	ExtensionContext,
	ExtensionCommandContext,
} from "@earendil-works/pi-coding-agent";

type GoalState = {
	condition: string;
	turns: number;
	startedAt: number;
	lastReason: string;
	spendUsd: number;
};

type Verdict = {
	met: boolean;
	impossible: boolean;
	reason: string;
};

type ContentBlock = { type?: string; text?: string; name?: string; arguments?: unknown };
type SessionEntry = { type: string; message?: { role?: string; content?: unknown } };

const MAX_TURNS = Number(process.env.PI_GOAL_MAX_TURNS ?? "25");
const TRANSCRIPT_CHAR_BUDGET = Number(process.env.PI_GOAL_TRANSCRIPT_CHARS ?? "14000");

let goal: GoalState | null = null;
let evaluating = false;

const extractText = (content: unknown): string => {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	const parts: string[] = [];
	for (const raw of content) {
		if (!raw || typeof raw !== "object") continue;
		const block = raw as ContentBlock;
		if (block.type === "text" && typeof block.text === "string") parts.push(block.text);
		if (block.type === "toolCall" && typeof block.name === "string")
			parts.push(`[tool ${block.name} ${JSON.stringify(block.arguments ?? {})}]`);
	}
	return parts.join("\n");
};

const buildTranscript = (entries: SessionEntry[]): string => {
	const lines: string[] = [];
	const label: Record<string, string> = {
		user: "User",
		assistant: "Assistant",
		toolResult: "ToolResult",
	};
	for (const entry of entries) {
		if (entry.type !== "message" || !entry.message?.role) continue;
		const role = entry.message.role;
		if (!(role in label)) continue;
		const text = extractText(entry.message.content).trim();
		if (text) lines.push(`${label[role]}: ${text}`);
	}
	const joined = lines.join("\n\n");
	return joined.length > TRANSCRIPT_CHAR_BUDGET ? joined.slice(-TRANSCRIPT_CHAR_BUDGET) : joined;
};

const evaluatorPrompt = (condition: string, transcript: string): string =>
	[
		"You are a strict completion evaluator for an autonomous coding agent.",
		"Judge ONLY from what the agent has surfaced in the transcript below — do not assume work you cannot see.",
		"",
		`COMPLETION CONDITION: ${condition}`,
		"",
		"Reply with a SINGLE JSON object and nothing else:",
		'{"met": <bool>, "impossible": <bool>, "reason": "<one sentence>"}',
		'- "met": true only if the transcript demonstrably proves the condition holds.',
		'- "impossible": true only if the condition can never be satisfied (contradiction, missing capability).',
		'- "reason": what still blocks completion, or how it was proven met.',
		"",
		"<transcript>",
		transcript || "(empty)",
		"</transcript>",
	].join("\n");

const parseVerdict = (raw: string): Verdict => {
	const start = raw.indexOf("{");
	const end = raw.lastIndexOf("}");
	if (start === -1 || end === -1 || end < start)
		return { met: false, impossible: false, reason: "evaluator returned no JSON" };
	try {
		const obj = JSON.parse(raw.slice(start, end + 1)) as Partial<Verdict>;
		return {
			met: Boolean(obj.met),
			impossible: Boolean(obj.impossible),
			reason: typeof obj.reason === "string" ? obj.reason : "no reason given",
		};
	} catch {
		return { met: false, impossible: false, reason: "evaluator JSON parse failed" };
	}
};

const pickEvaluatorModel = (ctx: ExtensionContext) => {
	const spec = process.env.PI_GOAL_MODEL;
	if (spec && spec.includes("/")) {
		const [provider, id] = [spec.slice(0, spec.indexOf("/")), spec.slice(spec.indexOf("/") + 1)];
		const found = ctx.modelRegistry.find(provider, id);
		if (found && ctx.modelRegistry.hasConfiguredAuth(found)) return found;
	}
	return ctx.model;
};

const setGoalStatus = (ctx: ExtensionContext) => {
	if (!goal) {
		ctx.ui.setStatus("goal", "");
		return;
	}
	const mins = Math.floor((Date.now() - goal.startedAt) / 60000);
	ctx.ui.setStatus("goal", `◎ goal ${goal.turns}t/${mins}m $${goal.spendUsd.toFixed(3)}`);
};

const clearGoal = (ctx: ExtensionContext, note: string) => {
	goal = null;
	setGoalStatus(ctx);
	if (ctx.hasUI) ctx.ui.notify(note, "info");
};

const runEvaluator = async (ctx: ExtensionContext): Promise<void> => {
	if (!goal || evaluating || !ctx.isIdle()) return;
	evaluating = true;
	try {
		const model = pickEvaluatorModel(ctx);
		if (!model || !ctx.modelRegistry.hasConfiguredAuth(model)) {
			clearGoal(ctx, "Goal cleared: no evaluator model with configured auth");
			return;
		}
		const transcript = buildTranscript(ctx.sessionManager.getBranch() as SessionEntry[]);
		const response = await ctx.modelRegistry.complete(
			model,
			{
				messages: [
					{
						role: "user" as const,
						content: [{ type: "text" as const, text: evaluatorPrompt(goal.condition, transcript) }],
						timestamp: Date.now(),
					},
				],
			},
			{ reasoningEffort: "low", cacheRetention: "none", sessionId: uuidv7() },
		);
		const text = response.content
			.filter((c): c is { type: "text"; text: string } => c.type === "text")
			.map((c) => c.text)
			.join("\n");
		const verdict = parseVerdict(text);
		if (!goal) return;
		goal.spendUsd += response.usage?.cost?.total ?? 0;
		goal.lastReason = verdict.reason;

		if (verdict.met) {
			clearGoal(ctx, `✓ Goal met: ${goal.condition} — ${verdict.reason}`);
			return;
		}
		if (verdict.impossible) {
			clearGoal(ctx, `⚠ Goal unreachable: ${verdict.reason}`);
			return;
		}
		if (goal.turns >= MAX_TURNS) {
			clearGoal(ctx, `⚠ Goal stopped after ${MAX_TURNS} turns: ${verdict.reason}`);
			return;
		}
		goal.turns += 1;
		setGoalStatus(ctx);
		if (ctx.hasUI) ctx.ui.notify(`◎ goal continuing (turn ${goal.turns}): ${verdict.reason}`, "info");
		pi.sendUserMessage(
			[
				`The goal is not yet met. Keep working toward it — do NOT stop and ask me.`,
				`GOAL: ${goal.condition}`,
				`Evaluator says still blocking: ${verdict.reason}`,
				`When you believe the goal holds, state the concrete evidence that proves it.`,
			].join("\n"),
		);
	} catch (err) {
		clearGoal(ctx, `⚠ Goal cleared (evaluator error): ${(err as Error).message}`);
	} finally {
		evaluating = false;
	}
};

let pi!: ExtensionAPI;

export default function (api: ExtensionAPI) {
	pi = api;

	pi.on("agent_settled", async (_event, ctx) => {
		await runEvaluator(ctx);
	});

	pi.on("session_start", async (_event, ctx) => {
		setGoalStatus(ctx);
	});

	pi.registerCommand("goal", {
		description: "Set a completion condition; pi keeps working until an evaluator confirms it",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const arg = args.trim();

			if (arg === "" ) {
				if (!goal) {
					ctx.ui.notify("No goal set. Use /goal <condition>.", "info");
					return;
				}
				const mins = Math.floor((Date.now() - goal.startedAt) / 60000);
				ctx.ui.notify(
					`◎ goal: ${goal.condition}\n${goal.turns} turns · ${mins}m · $${goal.spendUsd.toFixed(3)}\nlast: ${goal.lastReason || "(not evaluated yet)"}`,
					"info",
				);
				return;
			}

			if (arg === "clear") {
				if (!goal) {
					ctx.ui.notify("No goal set", "info");
					return;
				}
				const cond = goal.condition;
				clearGoal(ctx, `Goal cleared: ${cond}`);
				return;
			}

			goal = { condition: arg, turns: 0, startedAt: Date.now(), lastReason: "", spendUsd: 0 };
			setGoalStatus(ctx);
			ctx.ui.notify(`◎ goal set: ${arg}`, "info");
			if (ctx.isIdle()) {
				pi.sendUserMessage(
					[
						`Work autonomously toward this goal until it is satisfied. Do not stop to ask me.`,
						`GOAL: ${arg}`,
						`When you believe it holds, state the concrete evidence that proves it.`,
					].join("\n"),
				);
			}
		},
	});
}
