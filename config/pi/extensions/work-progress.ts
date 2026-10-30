import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { STAGES, autoBind, clean, discover, laneTask, lines, readJson, restore, task, validId } from "../lib/work-progress.mjs";

// Exported injection seam keeps lifecycle tests independent of installed Pi packages.
export function setup(pi: ExtensionAPI, Type: any, truncateToWidth: (s: string, w: number) => string) {
	const registry = process.env.PI_DELEGATE_REGISTRY || join(homedir(), ".pi/agent/delegate-lanes");
	const mailbox = process.env.PI_DELEGATE_MAILBOX || join(homedir(), ".pi/agent/delegate-mailbox");
	const pane = process.env.TMUX_PANE || "";
	let active: any;
	let timer: ReturnType<typeof setInterval> | undefined;

	function persist(a: any) {
		pi.appendEntry("work-progress", structuredClone(a.state));
	}

	function draw(a: any) {
		if (active !== a || a.ctx.mode !== "tui") return;
		if (a.state.hidden) { a.ctx.ui.setWidget("work-progress", undefined); return; }
		a.ctx.ui.setWidget("work-progress", () => ({
			render(width: number) {
				return [...(a.error ? ["Work: unknown/error — metadata unavailable or malformed"] : []),
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
			let changed = false, error = a.restoreError;
			// Legacy lanes lack parent session IDs. Only auto-bind lanes created while
			// this runtime is active in this pane. Older lanes need explicit attachment.
			for (const name of await discover(registry)) {
				if (a.state.bindings.length >= 50) break;
				try {
					const { data } = await readJson(join(registry, name));
					if (autoBind(data, pane, a.startedAt, Date.now()) && name === `${data.run_id}.json` &&
						!a.state.bindings.includes(data.run_id) && !a.state.dismissed.includes(data.run_id)) {
						a.state.bindings.push(data.run_id); changed = true;
					}
				} catch { /* Cannot attribute a corrupt unbound lane; never import it. */ }
			}
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
			a.rows = [...rows.values()]; a.error = error;
			if (changed) persist(a);
		} catch { if (active === a) { a.error = true; a.rows = []; } }
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
		const { state, error } = restore(ctx.sessionManager.getBranch(), ctx.sessionManager.getSessionId());
		const a = { ctx, state, restoreError: error, error, rows: [], scanning: false, startedAt: Date.now() };
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
			action: Type.Union(["update", "remove", "list"].map(v => Type.Literal(v))),
			id: Type.Optional(Type.String()), title: Type.Optional(Type.String()),
			stage: Type.Optional(Type.Union(STAGES.map((v: string) => Type.Literal(v)))),
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
					if (a.state.bindings.includes(params.id) && !a.state.dismissed.includes(params.id)) {
						if (a.state.dismissed.length >= 2000) throw new Error("Dismissed lane limit reached");
						a.state.dismissed.push(params.id);
					}
					a.state.bindings = a.state.bindings.filter((id: string) => id !== params.id);
				}
				a.state.tasks = remaining;
				persist(a);
			}
			await a.scanDone;
			await refresh(a);
			return { content: [{ type: "text", text: JSON.stringify({ tasks: a.rows, metadataError: a.error }) }], details: { tasks: a.rows } };
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
				if (ctx.hasUI) ctx.ui.notify(a.rows.map((t: any) =>
					`${clean(t.id)}: ${t.stage} — ${clean(t.evidence, 500)}`).join("\n") || "No tracked tasks", "info");
			} else if (ctx.hasUI) ctx.ui.notify("Usage: /work-progress show|hide|toggle|list|attach <run-id>", "warning");
		},
	});
}

export default async function (pi: ExtensionAPI) {
	const [{ Type }, { truncateToWidth }] = await Promise.all([import("typebox"), import("@earendil-works/pi-tui")]);
	setup(pi, Type, truncateToWidth);
}
