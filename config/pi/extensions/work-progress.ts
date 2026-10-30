import { stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { STAGES, autoBind, clean, discover, label, laneTask, lines, readJson, restore, task, validId } from "../lib/work-progress.mjs";

const MAX_BINDINGS = 50;
// Uncached lane reads per refresh; a large backlog is worked through over later ticks.
const SCAN_BUDGET = 200;

// Exported injection seam keeps lifecycle tests independent of installed Pi packages.
export function setup(pi: ExtensionAPI, Type: any, truncateToWidth: (s: string, w: number) => string) {
	const registry = process.env.PI_DELEGATE_REGISTRY || join(homedir(), ".pi/agent/delegate-lanes");
	const mailbox = process.env.PI_DELEGATE_MAILBOX || join(homedir(), ".pi/agent/delegate-mailbox");
	const pane = process.env.TMUX_PANE || "";
	let active: any;
	let timer: ReturnType<typeof setInterval> | undefined;
	// First runtime start per session ID, so a session_tree restart keeps the auto-bind window.
	const firstStart = new Map<string, number>();
	// StringEnum shape (plain string enum): providers such as Google reject anyOf/const unions.
	const stringEnum = (values: string[]) => Type.Unsafe({ type: "string", enum: values });

	function persist(a: any) {
		pi.appendEntry("work-progress", structuredClone(a.state));
		// A valid entry now supersedes any corrupt one, so a reload would restore cleanly.
		a.restoreError = false;
	}

	async function isLane(id: string) {
		try { return (await stat(join(registry, `${id}.json`))).isFile(); } catch { return false; }
	}

	function problems(a: any) {
		return [...(a.restoreError ? ["saved work-progress state was malformed and was reset"] : []), ...a.errors];
	}

	function draw(a: any) {
		if (active !== a || a.ctx.mode !== "tui") return;
		if (a.state.hidden) { a.ctx.ui.setWidget("work-progress", undefined); return; }
		a.ctx.ui.setWidget("work-progress", () => ({
			render(width: number) {
				return [...problems(a).map(p => `Work: error — ${p}`),
					...lines(a.rows)].map(line => truncateToWidth(line, Math.max(0, width)));
			},
			invalidate() {},
		}), { placement: "aboveEditor" });
	}

	async function refresh(a: any) {
		if (active !== a || a.scanning) return;
		a.scanning = true;
		let finish!: () => void;
		a.scanDone = new Promise<void>(resolve => { finish = resolve; });
		try {
			let changed = false;
			const errors: string[] = [];
			// Legacy lanes lack parent session IDs. Only auto-bind lanes created while
			// this runtime is active in this pane. Older lanes need explicit attachment.
			// Discovery failures must not hide manual or already bound tasks.
			try {
				let budget = SCAN_BUDGET;
				const names = await discover(registry);
				const listed = new Set(names);
				for (const name of a.waiting) if (!listed.has(name)) a.waiting.delete(name);
				// Newest first: run IDs are timestamp-prefixed and only recent lanes can bind.
				for (const name of names.reverse()) {
					if (a.settled.has(name)) continue;
					if (budget-- <= 0) break;
					a.waiting.delete(name);
					try {
						const { data } = await readJson(join(registry, name));
						const created = Date.parse(data?.created_at);
						const id = data?.run_id;
						if (autoBind(data, pane, a.startedAt, Date.now()) && name === `${id}.json` &&
							!a.state.bindings.includes(id) && !a.state.dismissed.includes(id)) {
							if (a.state.bindings.length >= MAX_BINDINGS) { a.waiting.add(name); continue; }
							a.state.bindings.push(id); changed = true; a.settled.add(name);
						} else if (!pane || data?.parent_pane !== pane || !Number.isFinite(created) ||
							created < a.startedAt || !validId(id) ||
							name !== `${id}.json` || a.state.bindings.includes(id) || a.state.dismissed.includes(id)) {
							// Immutable lane identity: this file can never auto-bind; skip rereading it.
							a.settled.add(name);
						}
					} catch {
						// Cannot attribute a corrupt unbound lane; never import it. Retry a few ticks
						// (a writer may be mid-update), then stop spending scan budget on it.
						const failures = (a.failures.get(name) || 0) + 1;
						a.failures.set(name, failures);
						if (failures >= 3) a.settled.add(name);
					}
				}
			} catch { errors.push("lane registry unreadable; new delegate lanes are not being detected"); }
			if (a.waiting.size) errors.push(`lane limit (${MAX_BINDINGS}) reached; new lanes are not tracked — remove finished ones`);
			const rows = new Map(a.state.tasks.map((t: any) => [t.id, t]));
			for (const id of a.state.bindings) {
				let row;
				try { row = await laneTask(registry, mailbox, id); }
				catch { row = { id, title: id, stage: "error", reason: "Lane unavailable or corrupt",
					source: "delegate lane", updatedAt: NaN }; }
				const manual: any = rows.get(id);
				// New lane evidence invalidates older parent attestations. Missing/corrupt
				// evidence also wins over a previously verified manual record.
				if (!manual || !Number.isFinite(row.updatedAt) || row.updatedAt > manual.updatedAt) rows.set(id, row);
			}
			if (active !== a) return;
			a.rows = [...rows.values()]; a.errors = errors;
			if (changed) persist(a);
		} catch {
			// Last resort: keep previous rows visible rather than blanking the panel.
			if (active === a) a.errors = ["work progress refresh failed; rows may be outdated"];
		}
		finally { a.scanning = false; draw(a); finish(); }
	}

	function stop() {
		if (timer) clearInterval(timer);
		timer = undefined;
		if (active?.ctx.mode === "tui") active.ctx.ui.setWidget("work-progress", undefined);
		active = undefined;
	}

	function start(_event: any, ctx: any) {
		stop();
		const session = ctx.sessionManager.getSessionId();
		const { state, error } = restore(ctx.sessionManager.getBranch(), session);
		// Lane created_at has second precision; floor so a lane started in the same second binds.
		if (!firstStart.has(session)) firstStart.set(session, Math.floor(Date.now() / 1000) * 1000);
		const a = { ctx, state, restoreError: error, errors: [] as string[], rows: [], scanning: false,
			startedAt: firstStart.get(session)!, settled: new Set<string>(), failures: new Map<string, number>(), waiting: new Set<string>() };
		active = a;
		void refresh(a);
		// No background timer in print/RPC mode. Tools still persist session state.
		if (ctx.mode === "tui") { timer = setInterval(() => void refresh(a), 5000); timer.unref?.(); }
	}
	pi.on("session_start", start);
	pi.on("session_tree", start);
	pi.on("session_shutdown", stop);

	pi.registerTool({
		name: "work_progress", label: "Work progress", executionMode: "sequential",
		description: "Persist an honest task stage in this session's work widget. Use stable IDs; for attached delegates use their run ID. Actions: update, remove, list. Awaiting stages require a reason. Evidence and source are required for updates. 'reported-complete' is a claim; 'verified' means this parent independently checked the stated evidence, never child DONE/PASS alone. Named milestones are explicit accomplishments, not percent/ETA. Do not store secrets. Use /work-progress attach <run-id> for older delegated lanes.",
		parameters: Type.Object({
			action: stringEnum(["update", "remove", "list"]),
			id: Type.Optional(Type.String()), title: Type.Optional(Type.String()),
			stage: Type.Optional(stringEnum(STAGES)),
			reason: Type.Optional(Type.String()), evidence: Type.Optional(Type.String()), source: Type.Optional(Type.String()),
			milestones: Type.Optional(Type.Array(Type.Object({ label: Type.String(), done: Type.Boolean() }), { maxItems: 8 })),
		}),
		async execute(_id: string, params: any) {
			const a = active;
			if (!a) throw new Error("No active work-progress session");
			if (params.action !== "list") {
				if (!validId(params.id)) throw new Error("Use a simple alphanumeric task ID (hyphens/underscores allowed)");
				const remaining = a.state.tasks.filter((t: any) => t.id !== params.id);
				if (params.action === "update") {
					if (remaining.length >= 50) throw new Error("Task limit reached; remove old tasks");
					remaining.push(task({ ...params, updatedAt: Date.now() }));
				} else {
					// Dismiss even if not yet bound, so a pending auto-bind cannot resurrect it.
					// Manual-only IDs are not dismissed, and a full list drops its oldest entry,
					// so removing a task can never be blocked.
					if (!a.state.dismissed.includes(params.id) &&
						(a.state.bindings.includes(params.id) || await isLane(params.id))) {
						if (active !== a) throw new Error("Session changed; retry");
						a.state.dismissed = [...a.state.dismissed, params.id].slice(-2000);
					}
					a.state.bindings = a.state.bindings.filter((id: string) => id !== params.id);
				}
				a.state.tasks = remaining;
				persist(a);
			}
			await a.scanDone;
			await refresh(a);
			return { content: [{ type: "text", text: JSON.stringify({ tasks: a.rows, metadataErrors: problems(a) }) }], details: { tasks: a.rows } };
		},
	});

	pi.registerCommand("work-progress", {
		description: "Work panel: show, hide, toggle, list, attach <run-id> (explicit session ownership)",
		handler: async (args: string, ctx: any) => {
			const a = active;
			if (!a) return;
			const [command = "toggle", id] = args.trim().split(/\s+/).filter(Boolean);
			if (["toggle", "show", "hide"].includes(command)) {
				a.state.hidden = command === "toggle" ? !a.state.hidden : command === "hide";
				persist(a); draw(a);
			} else if (command === "attach") {
				if (!validId(id)) throw new Error("Expected a delegate run ID");
				const { data } = await readJson(join(registry, `${id}.json`));
				if (!pane || data.run_id !== id || data.parent_pane !== pane) throw new Error("Lane is not addressed to this pane");
				if (active !== a) return;
				if (!a.state.bindings.includes(id)) {
					if (a.state.bindings.length >= 50) throw new Error("Lane limit reached");
					a.state.bindings.push(id);
					a.state.dismissed = a.state.dismissed.filter((value: string) => value !== id);
					persist(a);
				}
				await a.scanDone;
				await refresh(a);
			} else if (command === "list") {
				await a.scanDone;
				await refresh(a);
				if (ctx.hasUI) ctx.ui.notify([...problems(a).map(p => `error: ${p}`), ...a.rows.map((t: any) =>
					`${clean(t.id)}: ${label(t.stage)} — ${clean(t.evidence, 500)}`)].join("\n") || "No tracked tasks", "info");
			} else if (ctx.hasUI) ctx.ui.notify("Usage: /work-progress show|hide|toggle|list|attach <run-id>", "warning");
		},
	});
}

export default async function (pi: ExtensionAPI) {
	const [{ Type }, { truncateToWidth }] = await Promise.all([import("typebox"), import("@earendil-works/pi-tui")]);
	setup(pi, Type, truncateToWidth);
}
