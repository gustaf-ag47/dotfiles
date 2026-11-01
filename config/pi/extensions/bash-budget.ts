// bash-budget.ts — bound bash tool timeouts and tell the model how to run long jobs.
//
// Why (2026-11-01): Anthropic strict tool mode turns pi's optional `timeout`
// into a required field, the description says "no default timeout", and the
// Claude Code identity (anthropic-pool.ts) primes Claude Code's millisecond
// unit. Agents picked 1800-3600 s "ceilings" (and ms-looking values such as
// 300000 s = 83 h), then hid a 10+ minute test run behind `| grep | head`.
// Report: $NOTES/Homelab/agent-runs/2026-11-01-pi-long-timeouts-report.md
//
// tool_call: missing/invalid timeout -> 600 s; values >= 10000 are read as
// milliseconds; everything is clamped (not blocked) to PI_BASH_MAX_TIMEOUT
// (default 900 s). event.input is mutable per pi's ToolCallEvent contract and
// also fires for codemode-nested calls.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const DEFAULT_TIMEOUT_S = 600;
export const DEFAULT_MAX_TIMEOUT_S = 900;
export const MS_THRESHOLD = 10_000;

export function maxTimeout(env: Record<string, string | undefined> = process.env): number {
	const raw = Number(env.PI_BASH_MAX_TIMEOUT);
	return env.PI_BASH_MAX_TIMEOUT && Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_MAX_TIMEOUT_S;
}

/** Pure: the timeout (seconds) pi should actually use for a requested value. */
export function budgetTimeout(requested: unknown, cap: number = maxTimeout()): number {
	let t =
		typeof requested === "number" && Number.isFinite(requested) && requested > 0
			? requested
			: DEFAULT_TIMEOUT_S;
	if (t >= MS_THRESHOLD) t = Math.ceil(t / 1000); // Claude Code habit: milliseconds
	return Math.min(t, cap);
}

export const GUIDELINES = [
	"Bash `timeout` is in SECONDS (not milliseconds). Size it to the expected runtime plus margin (most commands: 30-120). Values above the cap (default 900 s) are clamped.",
	"Prefer targeted checks (one package, one test) over full suites; the pre-commit hook and CI are the full checks.",
	"Anything expected to run longer than ~5 minutes: start it in its own tmux window with output tee'd to a log on persistent disk, return immediately, and check the log tail later. Never block a tool call on sleep/poll loops (CI included).",
	"Never filter a long run's output to nothing (`| grep FAIL | head`): tee the full output to a log and print a progress line per step so the operator can see it is alive.",
];

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		if (event.toolName !== "bash") return;
		const input = event.input as { timeout?: unknown };
		input.timeout = budgetTimeout(input.timeout);
	});

	pi.on("before_agent_start", async (event) => {
		for (const g of GUIDELINES) {
			if (!event.systemPromptOptions.promptGuidelines.includes(g)) {
				event.systemPromptOptions.promptGuidelines.push(g);
			}
		}
	});
}
