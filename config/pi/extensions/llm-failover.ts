// llm-failover: notify-only cross-provider switch driven by the local proxy's
// route oracle (`GET /_route?model=`). Decisions 2 and 3 in
// docs/research/generic-llm-proxy.md: switch away when the Anthropic pool cannot
// serve, switch back when it recovers, print one line each time, never ask.
//
// Hooks (pi 0.87.1): `turn_end` carries the failed assistant message; the SDK
// throws on a non-2xx response before `after_provider_response` fires, so the
// proxy's 503 body is only visible as `message.errorMessage`. `turn_start` polls
// for recovery. `model_select` detects a manual model change.
//
// Decision 4: when nothing is routable, pi's own retry (retry.maxRetries, 2-8 s
// backoff, Retry-After ignored) gives up within seconds. `agent_before_settle`
// then waits for the earliest cooldown reset, omits the failed attempt with a
// context edit (as pi's own retry does) and continues the same run.
//
// The pure parts (matching, formatting, the state machine) are exported so
// tests/unit/test_llm_failover.mjs can drive them without a pi process.
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export const ANTHROPIC = "anthropic";
/** Substring of the proxy's `unavailable_message()`; see bin/claude-token-proxy. */
export const POOL_EXHAUSTED_MARKER = "no OAuth account can serve";
export const ROUTE_TIMEOUT_MS = 3_000;
/** Minimum gap between recovery polls and between the two confirming polls. */
export const RECOVERY_POLL_MS = 60_000;
/** Do not repeat an identical "nothing routable" line more often than this. */
export const NO_ROUTE_REPEAT_MS = 300_000;
export const DEFAULT_MAX_WAIT_MS = 6 * 3_600_000;
/** Shortest nap before re-polling, so a disagreeing oracle cannot spin. */
export const MIN_NAP_MS = 5_000;
/** Added after a known reset so the proxy has cleared the cooldown. */
export const RESET_GRACE_MS = 5_000;
export const RESET_JITTER_MS = 15_000;

export type Candidate = {
	provider: string;
	model: string;
	routable: boolean;
	reason: string | null;
	reset_at?: string | null;
	quota_left_percent?: number | null;
};

export type RouteAnswer = {
	model: string;
	candidates: Candidate[];
	first_routable: Candidate | null;
};

export type Target = { provider: string; model: string };

export type FailoverDeps = {
	fetchRoute: (model: string) => Promise<RouteAnswer | null>;
	/** Returns false when pi cannot select the model (no auth, unknown id). */
	setModel: (target: Target) => Promise<boolean>;
	notify: (line: string, level: "info" | "warning" | "error") => void;
	now?: () => number;
	/** Resolves after `ms`, or earlier once `cancelled()` turns true. */
	sleep?: (ms: number) => Promise<void>;
	random?: () => number;
	wait?: WaitSettings;
};

export type WaitSettings = { enabled: boolean; maxWaitMs: number; pollMs: number };

export type CooldownReset = { account: string; at: string; epoch: number };

export type WaitPlan =
	| { action: "wait"; until: number | null; deadline: number; account: string | null }
	| { action: "stop"; line: string };

export type FailoverState = {
	enabled: boolean;
	/** Set while switched away from Anthropic. */
	original: Target | null;
	current: Target | null;
	lastPollAt: number;
	lastPollRoutable: boolean;
	lastNoRouteLine: string;
	lastNoRouteAt: number;
	/** Start of the current run of pool-exhausted waits; 0 when not waiting. */
	waitingSince: number;
	cancelWait: boolean;
};

/**
 * PI_FAILOVER_WAIT=0 opts out; PI_FAILOVER_MAX_WAIT_HOURS caps one wait (default 6);
 * PI_FAILOVER_POLL_SECONDS is the oracle re-poll interval while waiting (default 60).
 */
export function waitSettings(env: NodeJS.ProcessEnv = process.env): WaitSettings {
	const hours = Number(env.PI_FAILOVER_MAX_WAIT_HOURS);
	const poll = Number(env.PI_FAILOVER_POLL_SECONDS);
	return {
		enabled: env.PI_FAILOVER_WAIT !== "0",
		maxWaitMs: Number.isFinite(hours) && hours > 0 ? hours * 3_600_000 : DEFAULT_MAX_WAIT_MS,
		pollMs: Number.isFinite(poll) && poll > 0 ? poll * 1000 : RECOVERY_POLL_MS,
	};
}

/** Earliest future `cooldown until <ISO> for <model>` in the proxy's 503 body. */
export function earliestCooldown(errorMessage: string | undefined, model: string, now: number): CooldownReset | null {
	if (!isPoolExhausted(errorMessage)) return null;
	let best: CooldownReset | null = null;
	for (const line of (errorMessage as string).split(/\\n|\n/)) {
		const m = /^- (\S+)(?: \(([^)]+)\))?: cooldown until (\S+) for ([^;\s]+)/.exec(line.trim());
		if (!m || m[4] !== model) continue;
		const epoch = Date.parse(m[3]);
		if (Number.isNaN(epoch) || epoch <= now) continue;
		if (!best || epoch < best.epoch) best = { account: m[2] || m[1], at: m[3], epoch };
	}
	return best;
}

/** Wait for the earliest known reset (body or oracle), unless it lies past the cap. */
export function planWait(opts: {
	errorMessage: string | undefined; model: string; route: RouteAnswer | null;
	now: number; waitingSince: number; maxWaitMs: number;
}): WaitPlan {
	const { now, model } = opts;
	const deadline = (opts.waitingSince || now) + opts.maxWaitMs;
	const body = earliestCooldown(opts.errorMessage, model, now);
	const oracleAt = Date.parse(opts.route?.candidates.find((c) => c.provider === ANTHROPIC)?.reset_at ?? "");
	const oracle = Number.isNaN(oracleAt) || oracleAt <= now ? null : oracleAt;
	const until = body && (oracle === null || body.epoch <= oracle) ? body.epoch : oracle;
	const account = body && until === body.epoch ? body.account : null;
	if (now >= deadline) {
		return { action: "stop", line: `✗ anthropic pool still exhausted after ${hoursText(opts.maxWaitMs)} of waiting — giving up` };
	}
	if (until !== null && until > deadline) {
		return { action: "stop", line: `✗ anthropic pool exhausted; next reset ${clockText(until)} (${relativeTime(new Date(until).toISOString(), now)})`
			+ ` is past the ${hoursText(opts.maxWaitMs)} wait cap — not waiting` };
	}
	return { action: "wait", until, deadline, account };
}

function hoursText(ms: number): string {
	const h = ms / 3_600_000;
	return Number.isInteger(h) ? `${h}h` : `${Math.round(ms / 60_000)}m`;
}

/** "00:39:59Z", with the date when it is not today (UTC). */
export function clockText(epoch: number, now = Date.now()): string {
	const iso = new Date(epoch).toISOString();
	const clock = `${iso.slice(11, 19)}Z`;
	return iso.slice(0, 10) === new Date(now).toISOString().slice(0, 10) ? clock : `${iso.slice(0, 10)} ${clock}`;
}

export function waitLine(model: string, plan: Extract<WaitPlan, { action: "wait" }>, now: number,
	pollMs = RECOVERY_POLL_MS): string {
	if (plan.until === null) {
		return `⏳ anthropic pool exhausted for ${model}; reset unknown, polling every ${pollMs / 1000}s`
			+ ` (at most until ${clockText(plan.deadline, now)}; type a message or /failover off to stop)`;
	}
	const who = plan.account ? ` for ${plan.account}` : "";
	return `⏳ anthropic pool exhausted for ${model}; waiting until ${clockText(plan.until, now)}`
		+ ` (${relativeTime(new Date(plan.until).toISOString(), now)})${who} to reset, then resuming`
		+ ` (type a message or /failover off to stop)`;
}

export function proxyOrigin(env: NodeJS.ProcessEnv = process.env): string {
	const raw = env.PI_ANTHROPIC_PROXY_URL || `http://127.0.0.1:${env.CC_PROXY_PORT || "8788"}`;
	return new URL(raw).origin;
}

/** True only for the proxy's "no OAuth account can serve" error, not any 5xx. */
export function isPoolExhausted(errorMessage: string | undefined): boolean {
	return typeof errorMessage === "string" && errorMessage.includes(POOL_EXHAUSTED_MARKER);
}

export function shortProvider(provider: string): string {
	return provider === "openai-codex" ? "codex" : provider;
}

/** "in 3h 12m" / "in 45m" / "now" / "unknown". */
export function relativeTime(iso: string | null | undefined, now: number): string {
	if (!iso) return "unknown";
	const at = Date.parse(iso);
	if (Number.isNaN(at)) return "unknown";
	const seconds = Math.round((at - now) / 1000);
	if (seconds <= 0) return "now";
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	if (h > 0) return `in ${h}h ${String(m).padStart(2, "0")}m`;
	if (m > 0) return `in ${m}m`;
	return `in ${seconds}s`;
}

export function switchedLine(target: Target, anthropic: Candidate | undefined, now: number): string {
	return `↪ switched to ${target.provider}/${target.model}: anthropic pool exhausted`
		+ ` (next reset ${relativeTime(anthropic?.reset_at, now)})`;
}

export function backLine(original: Target): string {
	return `↩ back to ${original.provider}/${original.model}: pool recovered`;
}

export function noRouteLine(candidates: Candidate[]): string {
	const parts = candidates.map((c) => `${shortProvider(c.provider)} ${c.routable ? "routable" : c.reason || "unknown"}`);
	return `✗ no provider routable — ${parts.join(", ") || "oracle unreachable"}`;
}

export function rankingLines(answer: RouteAnswer | null): string[] {
	if (!answer) return ["  (oracle unreachable)"];
	return answer.candidates.map((c) => {
		const state = c.routable ? "routable" : c.reason || "unknown";
		const quota = typeof c.quota_left_percent === "number" ? ` ${c.quota_left_percent}% left` : "";
		const reset = c.reset_at ? ` reset ${c.reset_at}` : "";
		return `  ${c.routable ? "•" : "·"} ${c.provider}/${c.model}: ${state}${quota}${reset}`;
	});
}

/** Loopback GET with a hard timeout; never inherits an HTTP proxy. */
export async function fetchRoute(origin: string, model: string, fetchImpl: typeof fetch = fetch,
	timeoutMs = ROUTE_TIMEOUT_MS): Promise<RouteAnswer | null> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeoutMs);
	try {
		const url = `${origin}/_route?model=${encodeURIComponent(model)}`;
		const res = await fetchImpl(url, { signal: controller.signal, headers: { accept: "application/json" } });
		if (!res.ok) return null;
		const body = (await res.json()) as Partial<RouteAnswer>;
		if (!Array.isArray(body.candidates)) return null;
		return { model: body.model ?? model, candidates: body.candidates, first_routable: body.first_routable ?? null };
	} catch {
		return null;
	} finally {
		clearTimeout(timer);
	}
}

export function createFailover(deps: FailoverDeps) {
	const now = deps.now ?? (() => Date.now());
	const state: FailoverState = {
		enabled: true,
		original: null,
		current: null,
		lastPollAt: 0,
		lastPollRoutable: false,
		lastNoRouteLine: "",
		lastNoRouteAt: 0,
		waitingSince: 0,
		cancelWait: false,
	};
	const wait = deps.wait ?? waitSettings();
	const random = deps.random ?? Math.random;
	const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));

	function sayNoRoute(candidates: Candidate[]): void {
		const line = noRouteLine(candidates);
		const t = now();
		if (line === state.lastNoRouteLine && t - state.lastNoRouteAt < NO_ROUTE_REPEAT_MS) return;
		state.lastNoRouteLine = line;
		state.lastNoRouteAt = t;
		deps.notify(line, "error");
	}

	/** Called with the failed request's provider/model. Returns true when switched. */
	async function onPoolExhausted(current: Target): Promise<boolean> {
		if (!state.enabled || current.provider !== ANTHROPIC) return false;
		const answer = await deps.fetchRoute(current.model);
		if (!answer) {
			sayNoRoute([]);
			return false;
		}
		const anthropic = answer.candidates.find((c) => c.provider === ANTHROPIC);
		const others = answer.candidates.filter((c) => c.routable && c.provider !== ANTHROPIC);
		if (answer.first_routable?.provider === ANTHROPIC) {
			// The oracle disagrees with the request that just failed; pi's own retry handles it.
			return false;
		}
		for (const candidate of others) {
			const target = { provider: candidate.provider, model: candidate.model };
			if (!(await deps.setModel(target))) continue;
			state.original = state.original ?? current;
			state.current = target;
			state.lastPollAt = now();
			state.lastPollRoutable = false;
			deps.notify(switchedLine(target, anthropic, now()), "warning");
			return true;
		}
		sayNoRoute(answer.candidates);
		return false;
	}

	/** Called before each turn while switched. Returns true when switched back. */
	async function onTurnStart(): Promise<boolean> {
		if (!state.enabled || !state.original) return false;
		const t = now();
		if (t - state.lastPollAt < RECOVERY_POLL_MS) return false;
		state.lastPollAt = t;
		const answer = await deps.fetchRoute(state.original.model);
		const anthropic = answer?.candidates.find((c) => c.provider === ANTHROPIC);
		const routable = anthropic?.routable === true;
		const confirmed = routable && state.lastPollRoutable;
		state.lastPollRoutable = routable;
		if (!confirmed) return false;
		const original = state.original;
		if (!(await deps.setModel(original))) return false;
		state.original = null;
		state.current = original;
		state.lastPollRoutable = false;
		deps.notify(backLine(original), "info");
		return true;
	}

	/**
	 * Called when a run settles on the pool-exhausted error. Waits for the earliest
	 * reset, re-polling the oracle every `wait.pollMs`, and returns true when the
	 * failed turn should be resumed (pool recovered, or switched to a substitute).
	 */
	async function onSettledExhausted(current: Target, errorMessage: string | undefined,
		cancelled: () => boolean = () => false): Promise<boolean> {
		if (!state.enabled || !wait.enabled || current.provider !== ANTHROPIC) return false;
		state.cancelWait = false;
		const stop = () => state.cancelWait || !state.enabled || cancelled();
		const first = now();
		state.waitingSince = state.waitingSince || first;
		const plan = planWait({ errorMessage, model: current.model, route: await deps.fetchRoute(current.model),
			now: first, waitingSince: state.waitingSince, maxWaitMs: wait.maxWaitMs });
		if (plan.action === "stop") {
			state.waitingSince = 0;
			deps.notify(plan.line, "error");
			return false;
		}
		deps.notify(waitLine(current.model, plan, first, wait.pollMs), "warning");
		const wakeAt = plan.until === null ? null : plan.until + RESET_GRACE_MS + Math.floor(random() * RESET_JITTER_MS);
		for (;;) {
			const t = now();
			if (t >= plan.deadline) {
				state.waitingSince = 0;
				deps.notify(`✗ anthropic pool still exhausted after ${hoursText(wait.maxWaitMs)} of waiting — giving up`, "error");
				return false;
			}
			const untilWake = wakeAt === null || wakeAt <= t ? wait.pollMs : wakeAt - t;
			const nap = Math.max(Math.min(MIN_NAP_MS, wait.pollMs), Math.min(wait.pollMs, untilWake));
			await sleep(Math.min(plan.deadline - t, nap));
			if (stop()) {
				state.waitingSince = 0;
				deps.notify("⏹ stopped waiting for the anthropic pool", "info");
				return false;
			}
			const answer = await deps.fetchRoute(current.model);
			if (answer?.candidates.find((c) => c.provider === ANTHROPIC)?.routable) {
				deps.notify(`▶ anthropic pool recovered; resuming ${current.provider}/${current.model}`, "info");
				return true;
			}
			if (answer?.candidates.some((c) => c.routable && c.provider !== ANTHROPIC)) {
				if (await onPoolExhausted(current)) return true;
			}
		}
	}

	/** A turn completed normally: the next exhaustion starts a fresh wait budget. */
	function onTurnSucceeded(): void {
		state.waitingSince = 0;
	}

	/** The user picked a model by hand: stop tracking, never fight them. */
	function onManualModelSelect(target: Target): void {
		state.original = null;
		state.current = target;
		state.lastPollRoutable = false;
	}

	function setEnabled(enabled: boolean): void {
		state.enabled = enabled;
		if (!enabled) state.cancelWait = true;
	}

	return { state, onPoolExhausted, onTurnStart, onManualModelSelect, setEnabled, onSettledExhausted, onTurnSucceeded };
}

type AssistantLike = { role?: string; stopReason?: string; errorMessage?: string };

export default function llmFailover(pi: ExtensionAPI) {
	const origin = proxyOrigin();
	let applying = false;
	let ctxRef: ExtensionContext | undefined;
	let shuttingDown = false;
	const seen = new WeakSet<object>();
	const interrupted = () => shuttingDown || ctxRef?.signal?.aborted === true || ctxRef?.hasPendingMessages() === true;

	const say = (line: string, level: "info" | "warning" | "error") => {
		const ctx = ctxRef;
		if (ctx?.hasUI) ctx.ui.notify(line, level);
		else if (ctx?.mode === "print") console.log(line);
		else console.error(line);
	};

	const core = createFailover({
		fetchRoute: (model) => fetchRoute(origin, model),
		setModel: async (target) => {
			const model = ctxRef?.modelRegistry.find(target.provider, target.model);
			if (!model) return false;
			applying = true;
			try {
				return await pi.setModel(model);
			} catch {
				return false;
			} finally {
				applying = false;
			}
		},
		notify: say,
		sleep: async (ms) => {
			const end = Date.now() + ms;
			while (Date.now() < end && !core.state.cancelWait && !interrupted()) {
				await new Promise((resolve) => setTimeout(resolve, Math.min(1_000, end - Date.now())));
			}
		},
	});

	async function handleFailed(message: AssistantLike, ctx: ExtensionContext): Promise<void> {
		if (message.role !== "assistant" || message.stopReason !== "error") return;
		if (seen.has(message)) return;
		seen.add(message);
		if (!isPoolExhausted(message.errorMessage)) return;
		const model = ctx.model;
		if (!model) return;
		ctxRef = ctx;
		await core.onPoolExhausted({ provider: model.provider, model: model.id });
	}

	pi.on("turn_end", async (event, ctx) => {
		const message = event.message as AssistantLike;
		if (message.role === "assistant" && message.stopReason !== "error" && message.stopReason !== "aborted") {
			core.onTurnSucceeded();
		}
		await handleFailed(message, ctx);
	});

	// Every retry is spent and nothing is routable: wait for the earliest reset,
	// drop the failed attempt from the model context, and continue the run.
	pi.on("agent_before_settle", async (event, ctx) => {
		if (event.outcome !== "error") return;
		const entry = [...event.context.contextEntries].reverse().find((e) => e.messages.length > 0);
		const failed = entry?.messages.at(-1) as AssistantLike | undefined;
		if (!entry || failed?.role !== "assistant" || failed.stopReason !== "error") return;
		if (!isPoolExhausted(failed.errorMessage)) return;
		const model = ctx.model;
		if (!model) return;
		ctxRef = ctx;
		const resume = await core.onSettledExhausted({ provider: model.provider, model: model.id }, failed.errorMessage, interrupted);
		if (!resume) return;
		return { entries: [{ type: "context_edit", targetId: entry.sourceEntry.id, replacement: null }], continue: true };
	});

	pi.on("session_shutdown", () => {
		shuttingDown = true;
	});

	// Backstop: a failed turn that never reached the turn_end boundary still ends the run.
	pi.on("agent_end", async (event, ctx) => {
		const last = [...event.messages].reverse().find((m) => (m as AssistantLike).role === "assistant");
		if (last) await handleFailed(last as AssistantLike, ctx);
	});

	pi.on("turn_start", async (_event, ctx) => {
		ctxRef = ctx;
		await core.onTurnStart();
	});

	pi.on("model_select", (event, ctx) => {
		ctxRef = ctx;
		if (applying) return;
		core.onManualModelSelect({ provider: event.model.provider, model: event.model.id });
	});

	pi.registerCommand("failover", {
		description: "Cross-provider failover: status | on | off (off also stops a pool-reset wait)",
		handler: async (args, ctx) => {
			ctxRef = ctx;
			const sub = (args || "status").trim().split(/\s+/)[0];
			if (sub === "off" || sub === "on") {
				core.setEnabled(sub === "on");
				say(`failover auto-switch ${sub}`, "info");
				return;
			}
			const s = core.state;
			const model = ctx.model;
			const probe = s.original?.model ?? (model?.provider === ANTHROPIC ? model.id : undefined);
			const lines = [
				`failover: ${s.enabled ? "on" : "off"}; `
				+ (s.original ? `switched ${s.original.provider}/${s.original.model} → ${s.current?.provider}/${s.current?.model}`
					: `on ${model ? `${model.provider}/${model.id}` : "unknown"}`),
				`oracle: ${origin}/_route?model=${probe ?? "?"}`,
				`pool-reset wait: ${waitSettings().enabled ? `on, cap ${hoursText(waitSettings().maxWaitMs)}` : "off (PI_FAILOVER_WAIT=0)"}`
				+ (s.waitingSince ? `; waiting since ${new Date(s.waitingSince).toISOString()}` : ""),
			];
			if (probe) lines.push(...rankingLines(await fetchRoute(origin, probe)));
			say(lines.join("\n"), "info");
		},
	});
}
