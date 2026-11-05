// wait-for.ts — `wait_for`: wait for a non-CI condition in the background and
// re-prompt the agent in-band, plus a cache-aware keepalive for every pending
// wait (wait_for and ci_wait).
//
// Why (2026-11-05): after bash-budget.ts capped bash timeouts, Claude agents
// kept waiting inside tool calls: 2361 `sleep >= 30 s` bash calls in 3 days,
// most shaped `sleep 280; <check>` with timeout = sleep + margin, and a
// cluster at `sleep 840-895` / timeout 900 (the advertised cap became the
// target). ci_wait removed the CI share (225 ci_wait vs 31 CI sleeps after it
// landed); the rest waited on logs, merge queues, Ralph loops, rollouts and
// tmux panes, for which there was no wake-up path. Each `sleep; check` round is
// a full model turn that re-reads the whole context from the prompt cache, so
// polling every ~5 min costs ~12 context reads an hour where one wake-up costs
// one. Report: $NOTES/Homelab/agent-runs/2026-11-05-pi-sleep-waits-report.md
//
// wait_for checks the condition once inline (no turn ends if it already
// holds), otherwise registers a watch, terminates the turn, polls outside the
// model and delivers one "WAIT RESOLVED" custom message with triggerTurn.
//
// Keepalive: a wake-up that arrives after the prompt cache expired rewrites the
// whole context (1h tier: 2x input price, ~40x a cache read on Opus). While any
// wait is pending and the agent is idle, one tiny "WAIT KEEPALIVE" turn just
// before expiry refreshes the cache for the price of a read. It only fires
// while the cumulative keepalive spend for the current waiting period stays
// below the cost of one miss, computed from the model's prices and the context
// size; unknown economics means no keepalive. PI_WAIT_KEEPALIVE=off disables.
//
// Contracts: tool result text starts `wait_for registered:` (delegate
// supervisor/watchdog treat the pane as waiting); pi.events "wait-for:state"
// { active, watches } on every change (goal.ts pauses while active); watches
// persist as custom entries (customType "wait-for") and are rebuilt on restart.
//
// Knobs: PI_WAIT_FOR_MAX_MINUTES (default 120, cap for max_minutes 720),
// PI_WAIT_KEEPALIVE (auto|off), PI_CACHE_RETENTION (long -> 1h cache tier).

import { execFile } from "node:child_process";
import * as fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export type Kind = "command" | "file" | "pane" | "pid";
export interface WaitWatch {
	id: string;
	kind: Kind;
	target: string; // command text, file path, tmux pane, pid
	pattern?: string;
	failPattern?: string;
	cwd?: string;
	intervalMs: number;
	maxMs: number;
	note?: string;
	registeredAt: number;
	nextCheckAt?: number;
	checks?: number;
}
export interface ExecResult { code: number; stdout: string; stderr: string }
export type Exec = (file: string, args: string[], opts?: { cwd?: string; timeoutMs?: number }) => Promise<ExecResult>;
export interface Deps {
	exec?: Exec;
	now?: () => number;
	readTail?: (path: string, bytes: number) => string | null;
	pidAlive?: (pid: number) => boolean;
	autoPoll?: boolean; // tests drive tick()/keepaliveTick() by hand
}
interface Outcome { verdict: "met" | "failed" | "gone" | "timed out" | "error"; detail: string[] }

const SEC = 1000;
const MIN = 60 * SEC;
const TAIL_LINES = 40;
const TAIL_BYTES = 256 * 1024;
const KEEPALIVE_OUTPUT_TOKENS = 300; // generous estimate for "still waiting" + adaptive thinking
const num = (v: unknown, d: number) => (v !== undefined && v !== null && v !== "" && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);

function defaultExec(): Exec {
	return (file, args, opts) =>
		new Promise((resolve) => {
			execFile(file, args, { cwd: opts?.cwd, timeout: opts?.timeoutMs ?? 60 * SEC, maxBuffer: 4 * 1024 * 1024, killSignal: "SIGKILL" }, (error, stdout, stderr) => {
				const code = error ? (typeof (error as { code?: unknown }).code === "number" ? (error as { code: number }).code : -1) : 0;
				resolve({ code, stdout: String(stdout ?? ""), stderr: String(stderr ?? "") || (error && code === -1 ? error.message : "") });
			});
		});
}

function defaultReadTail(path: string, bytes: number): string | null {
	let fd: number | undefined;
	try {
		fd = fs.openSync(path, "r");
		const size = fs.fstatSync(fd).size;
		const len = Math.min(size, bytes);
		const buf = Buffer.alloc(len);
		fs.readSync(fd, buf, 0, len, size - len);
		return buf.toString("utf8");
	} catch {
		return null;
	} finally {
		if (fd !== undefined) fs.closeSync(fd);
	}
}

function defaultPidAlive(pid: number): boolean {
	try { process.kill(pid, 0); return true; } catch (e) { return (e as NodeJS.ErrnoException).code === "EPERM"; }
}

const tail = (text: string, n = TAIL_LINES) => text.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").trimEnd().split("\n").slice(-n);
export const describe = (w: WaitWatch) =>
	w.kind === "command" ? `command \`${w.target.length > 80 ? `${w.target.slice(0, 77)}...` : w.target}\``
	: w.kind === "file" ? `${w.target} =~ /${w.pattern}/`
	: w.kind === "pane" ? `tmux pane ${w.target}${w.pattern ? ` =~ /${w.pattern}/` : " exits"}`
	: `pid ${w.target} exits`;

/** Pure: prompt-cache lifetime (ms) for the model and retention tier, if known. */
export function cacheTtlMs(model: any, env: Record<string, string | undefined> = process.env): number | undefined {
	const tier = env.PI_CACHE_RETENTION === "long" ? "long" : "short";
	const s = model?.promptCache?.[tier];
	return typeof s === "number" && s > 0 ? s * SEC : undefined;
}

/** Pure: refresh this long after the last request (leave 10% of the TTL, 60 s..5 min, as margin). */
export function keepaliveDelayMs(ttlMs: number): number {
	return ttlMs - Math.min(5 * MIN, Math.max(MIN, ttlMs * 0.1));
}

/**
 * Pure: dollars for one keepalive turn vs one cache miss on wake-up. A miss
 * rewrites the context at the write price of the active tier (1h tier: 2x
 * input) instead of reading it. Null when prices or context size are unknown.
 */
export function keepaliveEconomics(model: any, tokens: number | null | undefined, env: Record<string, string | undefined> = process.env) {
	const c = model?.cost;
	if (!c || !tokens || tokens <= 0) return null;
	const read = (tokens * (c.cacheRead ?? 0)) / 1e6;
	const writePerM = env.PI_CACHE_RETENTION === "long" ? 2 * (c.input ?? 0) : (c.cacheWrite ?? 0);
	const miss = (tokens * writePerM) / 1e6 - read;
	const keepalive = read + (KEEPALIVE_OUTPUT_TOKENS * (c.output ?? 0)) / 1e6;
	if (!(miss > 0) || !(keepalive > 0)) return null;
	return { keepalive, miss };
}

/** Pure: send keepalive number n+1 only while n+1 keepalives cost less than one miss. */
export function keepaliveWorthIt(sent: number, econ: { keepalive: number; miss: number } | null): boolean {
	return !!econ && (sent + 1) * econ.keepalive < econ.miss;
}

export function setup(pi: ExtensionAPI, deps: Deps = {}) {
	const exec = deps.exec ?? defaultExec();
	const now = deps.now ?? Date.now;
	const readTail = deps.readTail ?? defaultReadTail;
	const pidAlive = deps.pidAlive ?? defaultPidAlive;
	const defaultMaxMin = num(process.env.PI_WAIT_FOR_MAX_MINUTES, 120);
	const keepaliveOff = ["off", "0", "false", "no"].includes((process.env.PI_WAIT_KEEPALIVE ?? "auto").toLowerCase());
	const watches = new Map<string, WaitWatch>();
	let ciActive: { target: string }[] = [];
	let ctxRef: any = null;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let kaTimer: ReturnType<typeof setInterval> | undefined;
	let ticking = false;
	let closed = true;
	let seq = 0;
	let lastRequestAt = now();
	let keepalivesSent = 0;

	const pending = () => watches.size > 0 || ciActive.length > 0;

	function emitState() {
		const list = [...watches.values()].map((w) => ({ id: w.id, target: describe(w) }));
		pi.events?.emit?.("wait-for:state", { active: list.length > 0, watches: list });
		if (ctxRef?.hasUI) {
			const text = [...watches.values()].map((w) => `⏳ ${w.id} ${w.kind}`).join("  ");
			try { ctxRef.ui.setStatus("wait-for", text || undefined); } catch { /* UI gone */ }
		}
		if (!pending()) keepalivesSent = 0;
		scheduleKeepalive();
	}

	function deliver(customType: string, content: string, details: unknown, display = true) {
		const message = { customType, content, details, display };
		const busy = typeof ctxRef?.isIdle === "function" && !ctxRef.isIdle();
		try {
			pi.sendMessage(message, busy ? { triggerTurn: true, deliverAs: "followUp" } : { triggerTurn: true });
		} catch {
			try { pi.sendMessage(message, { triggerTurn: true, deliverAs: "followUp" }); } catch { return false; }
		}
		return true;
	}

	// --- condition evaluation -------------------------------------------------
	async function evaluate(w: WaitWatch): Promise<Outcome | null> {
		if (w.kind === "command") {
			const r = await exec("bash", ["-c", w.target], { cwd: w.cwd, timeoutMs: 60 * SEC });
			if (r.code === 0) return { verdict: "met", detail: tail(r.stdout + r.stderr) };
			return null;
		}
		if (w.kind === "file") {
			const text = readTail(w.target, TAIL_BYTES);
			if (text === null) return null; // not created yet
			if (w.failPattern && new RegExp(w.failPattern, "m").test(text)) return { verdict: "failed", detail: [`fail_pattern /${w.failPattern}/ matched`, ...tail(text)] };
			if (new RegExp(w.pattern!, "m").test(text)) return { verdict: "met", detail: tail(text) };
			return null;
		}
		if (w.kind === "pid") {
			return pidAlive(Number(w.target)) ? null : { verdict: "met", detail: [`process ${w.target} is gone`] };
		}
		// tmux pane
		const info = await exec("tmux", ["display-message", "-p", "-t", w.target, "#{pane_dead} #{pane_dead_status}"]);
		if (info.code !== 0) return { verdict: "gone", detail: [`tmux pane ${w.target} no longer exists`] };
		const [dead, status] = info.stdout.trim().split(/\s+/);
		const cap = await exec("tmux", ["capture-pane", "-p", "-J", "-t", w.target, "-S", "-200"]);
		const text = cap.code === 0 ? cap.stdout : "";
		if (w.failPattern && new RegExp(w.failPattern, "m").test(text)) return { verdict: "failed", detail: [`fail_pattern /${w.failPattern}/ matched`, ...tail(text)] };
		if (w.pattern && new RegExp(w.pattern, "m").test(text)) return { verdict: "met", detail: tail(text) };
		if (dead === "1") return { verdict: w.pattern ? "gone" : "met", detail: [`pane exited${status ? ` with status ${status}` : ""}`, ...tail(text)] };
		return null;
	}

	function resolveText(w: WaitWatch, o: Outcome) {
		const mins = Math.round((now() - w.registeredAt) / MIN);
		const lines = [`WAIT RESOLVED - ${w.id} ${describe(w)}: ${o.verdict} after ${mins} min`];
		if (w.note) lines.push(`note: ${w.note}`);
		const detail = o.detail.join("\n").trim() ? o.detail : [];
		if (detail.length) lines.push("", "```", ...detail, "```");
		return lines.join("\n");
	}

	function finish(w: WaitWatch, o: Outcome) {
		if (!watches.has(w.id)) return;
		if (!deliver("wait-for", resolveText(w, o), { id: w.id, verdict: o.verdict })) return; // retry next tick
		watches.delete(w.id);
		pi.appendEntry("wait-for", { op: "resolved", id: w.id, verdict: o.verdict });
		emitState();
	}

	async function check(w: WaitWatch) {
		if (now() - w.registeredAt > w.maxMs) return finish(w, { verdict: "timed out", detail: [`still not met after ${Math.round(w.maxMs / MIN)} min (${w.checks ?? 0} checks)`] });
		if ((w.nextCheckAt ?? 0) > now()) return;
		w.nextCheckAt = now() + w.intervalMs;
		w.checks = (w.checks ?? 0) + 1;
		let o: Outcome | null;
		try { o = await evaluate(w); } catch (e) { o = { verdict: "error", detail: [(e as Error).message] }; }
		if (o) finish(w, o);
	}

	async function tick() {
		if (ticking) return;
		ticking = true;
		try { for (const w of [...watches.values()]) await check(w); } finally { ticking = false; }
	}

	function schedule(ms?: number) {
		if (closed || deps.autoPoll === false) return;
		clearTimeout(timer);
		if (!watches.size) return;
		const next = Math.min(...[...watches.values()].map((w) => (w.nextCheckAt ?? now()) - now()));
		timer = setTimeout(async () => { await tick().catch(() => {}); schedule(); }, ms ?? Math.max(SEC, next));
		(timer as { unref?: () => void }).unref?.();
	}

	// --- cache keepalive --------------------------------------------------------
	/** Returns what it did, for tests and /wait-for. */
	function keepaliveTick(): string {
		if (keepaliveOff) return "off";
		if (!pending()) return "no pending wait";
		if (!ctxRef || typeof ctxRef.isIdle !== "function" || !ctxRef.isIdle()) return "agent busy";
		const ttl = cacheTtlMs(ctxRef.model);
		if (!ttl) return "cache lifetime unknown";
		const due = lastRequestAt + keepaliveDelayMs(ttl);
		if (now() < due) return `next at +${Math.round((due - now()) / SEC)}s`;
		if (now() > lastRequestAt + ttl) return "cache already expired";
		let tokens: number | null | undefined;
		try { tokens = ctxRef.getContextUsage?.()?.tokens; } catch { tokens = undefined; }
		const econ = keepaliveEconomics(ctxRef.model, tokens);
		if (!keepaliveWorthIt(keepalivesSent, econ)) return econ ? `not worth it (${keepalivesSent} sent)` : "economics unknown";
		const what = [...[...watches.values()].map((w) => `${w.id} ${describe(w)}`), ...ciActive.map((c) => `ci_wait ${c.target}`)];
		const text = [
			`WAIT KEEPALIVE - still waiting on: ${what.join("; ")}.`,
			"This turn only refreshes the prompt cache so the wake-up reads it instead of rewriting it.",
			"Reply with one short line and end the turn: no tool calls, no checking, no polling. You will be re-prompted when a wait resolves.",
		].join("\n");
		if (!deliver("wait-keepalive", text, { keepalive: keepalivesSent + 1, ...econ })) return "deliver failed";
		keepalivesSent++;
		lastRequestAt = now(); // the turn about to start refreshes it; avoid double sends
		return "sent";
	}

	function scheduleKeepalive() {
		if (closed || deps.autoPoll === false) return;
		if (pending() && !keepaliveOff) {
			if (!kaTimer) {
				kaTimer = setInterval(() => { try { keepaliveTick(); } catch { /* best effort */ } }, 30 * SEC);
				(kaTimer as { unref?: () => void }).unref?.();
			}
		} else if (kaTimer) { clearInterval(kaTimer); kaTimer = undefined; }
	}

	// --- persistence ------------------------------------------------------------
	function rebuild(entries: any[]) {
		watches.clear();
		let maxSeen = 0;
		for (const e of entries) {
			if (e?.type !== "custom" || e.customType !== "wait-for" || !e.data) continue;
			const d = e.data;
			if (d.op === "registered" && d.watch) {
				watches.set(d.watch.id, { ...d.watch, nextCheckAt: undefined });
				maxSeen = Math.max(maxSeen, Number(String(d.watch.id).replace(/\D/g, "")) || 0);
			} else if (d.op === "resolved" || d.op === "cancelled") watches.delete(d.id);
		}
		seq = Math.max(seq, maxSeen);
	}

	function cancel(id: string) {
		const ids = id === "all" ? [...watches.keys()] : watches.has(id) ? [id] : [];
		for (const i of ids) { watches.delete(i); pi.appendEntry("wait-for", { op: "cancelled", id: i }); }
		emitState();
		return ids;
	}

	pi.registerTool({
		name: "wait_for",
		label: "Wait for",
		description:
			"Wait in the background for a condition, end the turn, and get re-prompted with 'WAIT RESOLVED' when it holds. " +
			"Use this instead of sleep or poll loops inside bash (CI and PRs: use ci_wait). Exactly one target: " +
			"command (shell check, met when it exits 0; keep it quick), file + pattern (regex appears in the file, e.g. a log's completion line), " +
			"pane (tmux pane id like %12: met when it exits, or when pattern appears in its output), or pid (met when the process exits). " +
			"fail_pattern (file/pane) resolves early as failed. The condition is checked once right away; if it already holds the result returns now. " +
			"One wake-up costs one prompt-cache read, while every sleep-then-check round re-reads the whole context.",
		promptSnippet: "Wait in the background for a log line, command, tmux pane or process, then get re-prompted",
		promptGuidelines: [
			"To wait for anything that is not CI (a log line, a command that must succeed, a tmux pane or process exiting, a rollout), call `wait_for` and end your turn; never hold a bash call open with sleep or a poll loop.",
		],
		parameters: {
			type: "object",
			properties: {
				command: { type: "string", description: "Shell check run with bash -c in the current directory; met when it exits 0. Must finish in < 60 s." },
				file: { type: "string", description: "File to watch (e.g. a log); needs pattern" },
				pane: { type: "string", description: "tmux pane id or target (e.g. %12 or session:window)" },
				pid: { type: "integer", description: "Process id; met when it exits" },
				pattern: { type: "string", description: "Regex (multiline) that means done, for file or pane" },
				fail_pattern: { type: "string", description: "Regex that means failed, for file or pane" },
				interval_seconds: { type: "integer", description: "Check interval (default 30, min 5)" },
				max_minutes: { type: "integer", description: "Give up and wake after this long (default 120, max 720)" },
				note: { type: "string", description: "Reminder of what to do next, echoed in the wake-up message" },
			},
			additionalProperties: false,
		} as any,
		async execute(_id: string, params: any, _signal: unknown, _onUpdate: unknown, ctx: any) {
			if (ctx) ctxRef = ctx;
			const given = (k: string) => params[k] !== undefined && params[k] !== null && params[k] !== "";
			const kinds = (["command", "file", "pane", "pid"] as Kind[]).filter(given);
			if (kinds.length !== 1) throw new Error("wait_for needs exactly one of command, file, pane or pid");
			const kind = kinds[0];
			if (kind === "file" && !given("pattern")) throw new Error("wait_for: file needs pattern (the line that means done)");
			for (const k of ["pattern", "fail_pattern"]) {
				if (given(k)) { try { new RegExp(params[k], "m"); } catch (e) { throw new Error(`wait_for: bad ${k}: ${(e as Error).message}`); } }
			}
			if (kind === "pid" && !(Number(params.pid) > 1)) throw new Error("wait_for: pid must be a process id");
			const maxMin = Math.min(720, num(params.max_minutes, defaultMaxMin));
			const watch: WaitWatch = {
				id: `wf${++seq}`, kind, target: String(params[kind]), cwd: ctx?.cwd,
				intervalMs: Math.max(5, num(params.interval_seconds, 30)) * SEC, maxMs: maxMin * MIN, registeredAt: now(),
				...(given("pattern") ? { pattern: String(params.pattern) } : {}),
				...(given("fail_pattern") ? { failPattern: String(params.fail_pattern) } : {}),
				...(given("note") ? { note: String(params.note) } : {}),
			};
			let first: Outcome | null;
			try { first = await evaluate(watch); } catch (e) { first = { verdict: "error", detail: [(e as Error).message] }; }
			if (first) {
				seq--; // nothing registered
				return { content: [{ type: "text", text: `wait_for: already ${first.verdict} - ${describe(watch)}\n${first.detail.join("\n")}` }], details: { watch, verdict: first.verdict } };
			}
			watch.checks = 1;
			watch.nextCheckAt = now() + watch.intervalMs;
			watches.set(watch.id, watch);
			const { nextCheckAt: _n, checks: _c, ...persisted } = watch;
			pi.appendEntry("wait-for", { op: "registered", watch: persisted });
			emitState();
			schedule();
			const text = `wait_for registered: ${watch.id} ${describe(watch)} (every ${watch.intervalMs / SEC}s, up to ${maxMin} min). ` +
				`Waiting in the background; you will be re-prompted with "WAIT RESOLVED". End your turn now; do not poll. (/wait-for to list or cancel)`;
			return { content: [{ type: "text", text }], details: { watch }, terminate: true };
		},
	} as any);

	pi.registerCommand("wait-for", {
		description: "List pending waits and keepalive state; /wait-for cancel <id|all>",
		handler: async (args: string, ctx: any) => {
			const [cmd, id] = args.trim().split(/\s+/);
			if (cmd === "cancel") {
				const gone = cancel(id || "all");
				ctx.ui.notify(gone.length ? `wait-for: cancelled ${gone.join(", ")}` : `wait-for: no watch ${id}`, "info");
				return;
			}
			const list = [...watches.values()].map((w) => `${w.id} ${describe(w)} - ${w.checks ?? 0} checks, ${Math.round((now() - w.registeredAt) / MIN)} min`);
			const ttl = cacheTtlMs(ctxRef?.model ?? ctx.model);
			list.push(`keepalive: ${keepaliveOff ? "off" : `${keepalivesSent} sent; cache ttl ${ttl ? `${ttl / MIN} min` : "unknown"}; last request ${Math.round((now() - lastRequestAt) / SEC)}s ago`}`);
			ctx.ui.notify(list.join("\n"), "info");
		},
	});

	pi.events?.on?.("ci-wait:state", (state: any) => {
		ciActive = Array.isArray(state?.watches) ? state.watches : [];
		if (!pending()) keepalivesSent = 0;
		scheduleKeepalive();
	});

	// Every model request reads (and so refreshes) the prompt cache.
	pi.on("turn_start", async () => { lastRequestAt = now(); });

	pi.on("session_start", async (_event: unknown, ctx: any) => {
		ctxRef = ctx;
		closed = false;
		lastRequestAt = now();
		try { rebuild(ctx.sessionManager?.getBranch?.() ?? []); } catch { watches.clear(); }
		emitState();
		schedule(5 * SEC);
	});

	pi.on("session_shutdown", async () => {
		closed = true;
		clearTimeout(timer);
		timer = undefined;
		if (kaTimer) clearInterval(kaTimer);
		kaTimer = undefined;
	});

	return { tick, keepaliveTick, watches, rebuild, state: () => ({ lastRequestAt, keepalivesSent, ciActive }) };
}

export default function (pi: ExtensionAPI) {
	setup(pi);
}
