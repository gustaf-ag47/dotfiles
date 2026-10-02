/**
 * Jev shadow classifier — Pi control surface.
 *
 * Shares one implementation (../lib/jev.mjs) with bin/jev-classify, the CLI
 * the delegate shell wrapper calls. This extension adds `/jev` for manual,
 * explicit use inside a Pi session:
 *
 *   /jev status            — mode, today's call/cost/error counts, config
 *   /jev off                — this session only: force mode to "off"
 *   /jev observe            — this session only: clear the session override
 *                              (falls back to PI_JEV_MODE / config file)
 *   /jev classify <text>    — classify an explicit, typed task description
 *
 * Deliberately NOT implemented, per the shadow-only brief:
 *   - No automatic classification on turn_start, session_start, or any other
 *     lifecycle event. Every classify() call here is a direct result of the
 *     user typing `/jev classify ...` — nothing classifies a real user
 *     message, file, or conversation without that explicit command. This
 *     avoids duplicate/unapproved charges beyond what a human explicitly
 *     asks for in this session.
 *   - `/jev off` and `/jev observe` only set an in-memory override for the
 *     running session; they never touch config/llm-proxy/jev.json, never
 *     change PI_JEV_MODE for any other process, and have no effect on the
 *     separate `bin/jev-classify` CLI invocations the delegate shell wrapper
 *     makes in its own process.
 *   - No model/tool/routing change of any kind. `classify()` results are
 *     only ever displayed to the user via `ctx.ui.notify`.
 *   - No codemode enablement; this extension never registers a tool.
 */
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { classifyTask, getStatus, MAX_TASK_CHARS } from "../lib/jev.mjs";

/** Session-local mode override. Never persisted; lost on restart. */
let sessionModeOverride: "off" | undefined;

function effectiveEnv(): NodeJS.ProcessEnv {
	if (sessionModeOverride === "off") return { ...process.env, PI_JEV_MODE: "off" };
	return process.env;
}

function formatStatus(status: ReturnType<typeof getStatus>): string {
	const lines = [
		`jev: mode ${status.mode}${sessionModeOverride ? " (session override: off)" : ""}, model ${status.model}, key ${status.keyConfigured ? "configured" : "missing"}`,
		...(status.configValid ? [] : [`config: invalid (${status.configError}); every call abstains until fixed`]),
		`today: ok ${status.today.ok}, abstained ${status.today.abstained}, error ${status.today.error}, skipped ${status.today.skipped}, cache_hit ${status.today.cache_hit}`,
		`budget: ${status.budget.calls}/${status.budget.maxCallsPerDay} calls, $${status.budget.costUsd.toFixed(6)}/$${status.budget.maxCostPerDayUsd} (${status.budget.date})${status.budget.corrupt ? " [corrupt: failing closed]" : ""}`,
		`cache: ${status.cacheEntries} entries`,
	];
	return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
	pi.registerCommand("jev", {
		description: "Jev shadow classifier: status | off | observe | classify <text>",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const trimmed = args.trim();
			const [sub, ...rest] = trimmed.split(/\s+/);

			if (sub === "off") {
				sessionModeOverride = "off";
				ctx.ui.notify("jev: this session set to off (classify/delegate CLI in other processes unaffected)", "info");
				return;
			}

			if (sub === "observe") {
				sessionModeOverride = undefined;
				ctx.ui.notify("jev: session override cleared (falls back to PI_JEV_MODE / config)", "info");
				return;
			}

			if (sub === "classify") {
				const task = trimmed.slice("classify".length).trim();
				if (!task) {
					ctx.ui.notify("Usage: /jev classify <short task description>", "info");
					return;
				}
				if (task.length > MAX_TASK_CHARS) {
					ctx.ui.notify(`jev: task too long (${task.length} > ${MAX_TASK_CHARS} chars); not sent`, "warning");
					return;
				}
				const result = await classifyTask({ task, source: "pi", env: effectiveEnv() });
				if (result.status === "ok" || result.status === "cache_hit") {
					ctx.ui.notify(`jev (${result.status}): ${result.suggestion} (confidence ${result.confidence?.toFixed(2)})`, "info");
				} else if (result.status === "abstained") {
					ctx.ui.notify(`jev: abstained (${result.reason}, confidence ${result.confidence?.toFixed(2)})`, "info");
				} else {
					ctx.ui.notify(`jev: ${result.status} (${result.reason ?? "no reason"})`, "info");
				}
				return;
			}

			// Default / "status"
			void rest;
			const status = getStatus({ env: effectiveEnv() });
			ctx.ui.notify(formatStatus(status), "info");
		},
	});
}
