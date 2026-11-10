// ci-wait.ts — register a CI watch, poll it with `gh` in the background, and
// re-prompt the agent in-band when the state becomes actionable.
//
// Why: agents are told never to sleep/poll CI inside a tool call
// (merge-blockers.ts), so after a push they end the turn and nothing woke them;
// the operator had to come back and say "check CI". This extension closes the
// loop: `ci_wait` registers a watch and terminates the turn; a background
// poller (started in session_start, stopped in session_shutdown) reads CI with
// `gh` and, once there is something to act on, injects a custom message with
// pi.sendMessage(..., { triggerTurn: true }) — the same in-band path as
// delegate-mailbox.ts.
//
// Contracts other code depends on:
// - The tool result text starts `ci_wait registered:` (supervise-children.py and
//   bin/delegate-watchdog treat a pane showing it as waiting, not stalled).
// - pi.events "ci-wait:state" { active, watches } is emitted on every change;
//   goal.ts pauses its evaluator while a wait is active.
// - Watches persist as custom entries (customType "ci-wait": registered /
//   updated / resolved / cancelled) and are rebuilt from the branch on restart.
//
// Check interpretation mirrors bin/delegate-watchdog: only the newest
// check-run per name gates, so a name with any pass/pending/skipping sibling is
// not red (CI-concurrency cancels), a lone cancel is never red, `--required` is
// retried without the flag when the repo has no required checks, and gh/API
// failures are "unknown", never green.
//
// Head SHA changes (someone pushed) re-arm the watch: the new head's checks are
// what gate, and the change is listed in the eventual resolution message.
//
// Knobs: PI_CI_WAIT_POLL_SECS (fixed interval; default 30s, 120s after 10 min),
// PI_CI_WAIT_MAX_HOURS (default 3), PI_CI_WAIT_MAX_FAILURES (default 10),
// PI_CI_WAIT_GH (gh binary, default "gh").

import { execFile } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Until = "checks" | "merged" | "post-merge";
export interface Watch {
	id: string;
	repo: string;
	pr?: number;
	run?: number;
	branch?: string;
	until: Until;
	note?: string;
	registeredAt: number;
	// Mutable progress (headSha/mergeSha/base are persisted via "updated").
	headSha?: string;
	autoMerge?: boolean;
	mergeSha?: string;
	base?: string;
	mergedAt?: number;
	failures?: number;
	lastError?: string;
	progress?: string;
	events?: string[];
}
export interface ExecResult { code: number; stdout: string; stderr: string }
export type Exec = (args: string[], opts?: { cwd?: string }) => Promise<ExecResult>;
export interface Deps {
	exec?: Exec;
	now?: () => number;
	autoPoll?: boolean; // tests drive tick() by hand
}
interface Verdict { verdict: string; red?: boolean; body: string[]; next: string[]; logRun?: number }

const MIN = 60_000;
const num = (v: string | undefined, d: number) => (v && Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
const LOG_LINES = 60;
const NO_CHECKS_GRACE_MS = 10 * MIN;

function ghExec(bin: string): Exec {
	return (args, opts) =>
		new Promise((resolve) => {
			execFile(bin, args, { cwd: opts?.cwd, timeout: 60_000, maxBuffer: 4 * 1024 * 1024 }, (error, stdout, stderr) => {
				const code = error ? (typeof (error as { code?: unknown }).code === "number" ? (error as { code: number }).code : -1) : 0;
				resolve({ code, stdout: String(stdout ?? ""), stderr: String(stderr ?? "") || (error?.message ?? "") });
			});
		});
}

export const label = (w: Watch) =>
	w.pr ? `${w.repo}#${w.pr}` : w.run ? `${w.repo} run ${w.run}` : `${w.repo}@${w.branch}`;

// --- check interpretation (shared semantics with bin/delegate-watchdog) ------
interface Check { name: string; bucket?: string; state?: string; link?: string; workflow?: string }
export function summarizeChecks(checks: Check[]) {
	const byName = new Map<string, Check[]>();
	for (const c of checks) byName.set(c.name, [...(byName.get(c.name) ?? []), c]);
	const failed: Check[] = [], pending: string[] = [], cancelled: string[] = [];
	let passed = 0;
	for (const [name, runs] of byName) {
		const buckets = new Set(runs.map((r) => r.bucket ?? ""));
		if (buckets.has("pending")) pending.push(name);
		else if (buckets.has("fail") && !["pass", "skipping"].some((b) => buckets.has(b))) failed.push(runs.find((r) => r.bucket === "fail")!);
		else if (buckets.has("pass") || buckets.has("skipping")) passed++;
		else cancelled.push(name); // a lone cancel is never red
	}
	return { total: byName.size, passed, failed, pending, cancelled };
}

const runIdFromLink = (link?: string) => Number(link?.match(/\/actions\/runs\/(\d+)/)?.[1]) || undefined;
const GREEN = new Set(["success", "skipped", "neutral"]);

export function setup(pi: ExtensionAPI, deps: Deps = {}) {
	const exec = deps.exec ?? ghExec(process.env.PI_CI_WAIT_GH || "gh");
	const now = deps.now ?? Date.now;
	const fixedPoll = process.env.PI_CI_WAIT_POLL_SECS ? num(process.env.PI_CI_WAIT_POLL_SECS, 30) * 1000 : 0;
	const maxMs = num(process.env.PI_CI_WAIT_MAX_HOURS, 3) * 60 * MIN;
	const maxFailures = num(process.env.PI_CI_WAIT_MAX_FAILURES, 10);
	const watches = new Map<string, Watch>();
	let ctxRef: any = null;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let ticking = false;
	let closed = true;
	let seq = 0;

	const json = (r: ExecResult) => JSON.parse(r.stdout || "null");
	const gh = async (args: string[]) => {
		const r = await exec(args, { cwd: ctxRef?.cwd });
		return r;
	};

	function emitState() {
		const list = [...watches.values()].map((w) => ({ id: w.id, target: label(w), until: w.until }));
		pi.events?.emit?.("ci-wait:state", { active: list.length > 0, watches: list });
		if (ctxRef?.hasUI) {
			const text = [...watches.values()].map((w) => `⏳ ci ${w.pr ? `#${w.pr}` : w.run ? `run ${w.run}` : w.branch}${w.progress ? ` ${w.progress}` : ""}`).join("  ");
			try { ctxRef.ui.setStatus("ci-wait", text || undefined); } catch { /* UI gone */ }
		}
	}

	function deliver(content: string, details: unknown) {
		const message = { customType: "ci-wait", content, details, display: true };
		const busy = typeof ctxRef?.isIdle === "function" && !ctxRef.isIdle();
		try {
			pi.sendMessage(message, busy ? { triggerTurn: true, deliverAs: "followUp" } : { triggerTurn: true });
		} catch {
			// Mid-stream and triggerTurn alone was rejected: queue behind the turn.
			try { pi.sendMessage(message, { triggerTurn: true, deliverAs: "followUp" }); } catch { return false; }
		}
		return true;
	}

	async function resolve(w: Watch, v: Verdict) {
		const lines = [`CI WAIT RESOLVED - ${label(w)}: ${v.verdict}`];
		if (w.note) lines.push(`note: ${w.note}`);
		lines.push(...v.body);
		if (w.events?.length) lines.push("", "Seen while waiting:", ...w.events.map((e) => `- ${e}`));
		if (v.logRun) {
			const log = await gh(["run", "view", String(v.logRun), "-R", w.repo, "--log-failed"]);
			const tail = (log.stdout || log.stderr).trimEnd().split("\n").slice(-LOG_LINES);
			if (tail.join("").trim()) lines.push("", `Failed log tail (run ${v.logRun}, last ${tail.length} lines):`, "```", ...tail, "```");
		}
		if (v.next.length) lines.push("", "Next:", ...v.next.map((c) => `  ${c}`));
		if (!watches.has(w.id)) return; // cancelled while we fetched logs
		if (!deliver(lines.join("\n"), { id: w.id, target: label(w), verdict: v.verdict, red: !!v.red })) return; // retry next tick
		watches.delete(w.id);
		pi.appendEntry("ci-wait", { op: "resolved", id: w.id, verdict: v.verdict });
		emitState();
	}

	// --- evaluation --------------------------------------------------------
	async function evalRuns(w: Watch, branch: string, sha: string | undefined, since: number): Promise<Verdict | null | "unknown"> {
		// Scheduled/dispatch runs at this SHA do not establish push CI health.
		const args = ["run", "list", "-R", w.repo, "--branch", branch, "--event", "push", "-L", "50", "--json", "databaseId,workflowName,status,conclusion,url,headSha,createdAt,event"];
		if (sha) args.push("--commit", sha);
		const r = await gh(args);
		if (r.code !== 0) { w.lastError = r.stderr.trim() || `gh run list exit ${r.code}`; return "unknown"; }
		let runs = (json(r) ?? []) as { databaseId: number; workflowName: string; status: string; conclusion: string; url: string; headSha: string; createdAt: string; event: string }[];
		runs = runs.filter((r) => r.event === "push");
		if (!sha) {
			// Branch watch: pin to the newest head at first sight; re-arm on a new push.
			const head = runs[0]?.headSha;
			if (head && w.headSha && head !== w.headSha) { w.events = [...(w.events ?? []), `new head ${head.slice(0, 7)} (was ${w.headSha.slice(0, 7)})`]; }
			if (head && head !== w.headSha) { w.headSha = head; persistUpdate(w); }
			runs = runs.filter((x) => x.headSha === w.headSha);
		}
		// Newest run per workflow gates (list is newest first).
		const latest = new Map<string, (typeof runs)[number]>();
		for (const x of runs) if (!latest.has(x.workflowName)) latest.set(x.workflowName, x);
		const all = [...latest.values()];
		if (!all.length) {
			if (now() - since > NO_CHECKS_GRACE_MS) return { verdict: `no workflow runs for ${sha ? sha.slice(0, 7) : branch} after ${Math.round((now() - since) / MIN)} min`, body: [], next: [`gh run list -R ${w.repo} --branch ${branch} -L5`] };
			w.progress = "0/0";
			return null;
		}
		const done = all.filter((x) => x.status === "completed");
		w.progress = `${done.length}/${all.length}`;
		const red = done.filter((x) => !GREEN.has(x.conclusion) && x.conclusion !== "cancelled");
		if (done.length < all.length && !red.length) return null;
		const cancelled = done.filter((x) => x.conclusion === "cancelled");
		const where = `${branch}${sha || w.headSha ? ` @ ${(sha || w.headSha)!.slice(0, 7)}` : ""}`;
		if (red.length) {
			return {
				verdict: `red - ${red.map((x) => x.workflowName).join(", ")} on ${where}`, red: true,
				body: ["", "Failing runs:", ...red.map((x) => `- ${x.workflowName}: ${x.conclusion} ${x.url}`)],
				next: [`gh run view ${red[0].databaseId} -R ${w.repo} --log-failed`, "fix, push, then call ci_wait again"],
				logRun: red[0].databaseId,
			};
		}
		return {
			verdict: `green - ${done.length - cancelled.length}/${all.length} workflow runs on ${where}${cancelled.length ? ` (${cancelled.length} cancelled/superseded)` : ""}`,
			body: ["", ...all.map((x) => `- ${x.workflowName}: ${x.conclusion} ${x.url}`)],
			next: w.pr ? ["continue with the post-merge work"] : [`gh run list -R ${w.repo} --branch ${branch} -L3`],
		};
	}

	async function evalRun(w: Watch): Promise<Verdict | null | "unknown"> {
		const r = await gh(["run", "view", String(w.run), "-R", w.repo, "--json", "status,conclusion,jobs,url,workflowName,headSha"]);
		if (r.code !== 0) { w.lastError = r.stderr.trim() || `gh run view exit ${r.code}`; return "unknown"; }
		const run = json(r) as { status: string; conclusion: string; url: string; workflowName: string; jobs?: { name: string; status: string; conclusion: string; url: string }[] };
		const jobs = run.jobs ?? [];
		w.progress = `${jobs.filter((j) => j.status === "completed").length}/${jobs.length}`;
		if (run.status !== "completed") return null;
		if (GREEN.has(run.conclusion)) return { verdict: `green - ${run.workflowName} ${run.conclusion}`, body: [run.url], next: [] };
		const bad = jobs.filter((j) => j.status === "completed" && !GREEN.has(j.conclusion));
		return {
			verdict: `${run.conclusion === "cancelled" ? "cancelled" : "red"} - ${run.workflowName} ${run.conclusion}`, red: run.conclusion !== "cancelled",
			body: [run.url, ...(bad.length ? ["", "Failing jobs:", ...bad.map((j) => `- ${j.name}: ${j.conclusion} ${j.url}`)] : [])],
			next: [`gh run view ${w.run} -R ${w.repo} --log-failed`, `gh run rerun ${w.run} -R ${w.repo} --failed  # if flaky`],
			logRun: run.conclusion === "cancelled" ? undefined : w.run,
		};
	}

	async function evalPr(w: Watch): Promise<Verdict | null | "unknown"> {
		if (w.mergeSha && w.until === "post-merge") return evalRuns(w, w.base!, w.mergeSha, w.mergedAt ?? w.registeredAt);
		const n = String(w.pr);
		const v = await gh(["pr", "view", n, "-R", w.repo, "--json", "state,mergedAt,mergeCommit,mergeable,mergeStateStatus,autoMergeRequest,headRefOid,isDraft,baseRefName,url"]);
		if (v.code !== 0) { w.lastError = v.stderr.trim() || `gh pr view exit ${v.code}`; return "unknown"; }
		const pr = json(v) as { state: string; mergedAt?: string; mergeCommit?: { oid: string } | null; mergeable: string; mergeStateStatus: string; autoMergeRequest: unknown; headRefOid: string; baseRefName: string; url: string };
		const base = pr.baseRefName;
		if (pr.state === "MERGED") {
			const sha = pr.mergeCommit?.oid ?? "";
			if (w.until === "post-merge" && sha) {
				w.mergeSha = sha; w.base = base; w.mergedAt = now();
				w.events = [...(w.events ?? []), `merged as ${sha.slice(0, 7)}`];
				persistUpdate(w);
				return evalRuns(w, base, sha, w.mergedAt);
			}
			return { verdict: `merged${sha ? ` as ${sha.slice(0, 7)}` : ""}`, body: [pr.url], next: [`gh run list -R ${w.repo} --branch ${base} -L3  # confirm the post-merge run`, `or: ci_wait { pr: ${w.pr}, repo: "${w.repo}", until: "post-merge" }`] };
		}
		if (pr.state === "CLOSED") return { verdict: "closed without merge", red: true, body: [pr.url], next: [`gh pr view ${n} -R ${w.repo}`] };
		if (w.headSha && pr.headRefOid !== w.headSha) w.events = [...(w.events ?? []), `new head ${pr.headRefOid.slice(0, 7)} (was ${w.headSha.slice(0, 7)}); re-armed`];
		if (pr.headRefOid !== w.headSha) { w.headSha = pr.headRefOid; persistUpdate(w); }
		const auto = !!pr.autoMergeRequest;
		if (pr.mergeable === "CONFLICTING" || pr.mergeStateStatus === "DIRTY")
			return { verdict: "merge conflict with base", red: true, body: [pr.url], next: [`git fetch origin && git rebase origin/${base}`, "resolve, push, then call ci_wait again"] };
		if (pr.mergeStateStatus === "BEHIND" && !auto)
			return { verdict: `behind ${base} (auto-merge not set)`, red: true, body: [pr.url], next: [`gh pr update-branch ${n} -R ${w.repo}  # or rebase`, "then call ci_wait again"] };
		if (w.autoMerge && !auto)
			return { verdict: "auto-merge was disabled", red: true, body: [pr.url, `mergeStateStatus: ${pr.mergeStateStatus}`], next: [`gh pr view ${n} -R ${w.repo} --json mergeStateStatus,autoMergeRequest`] };
		if (w.autoMerge === undefined || auto) w.autoMerge = auto;

		let c = await gh(["pr", "checks", n, "-R", w.repo, "--required", "--json", "name,state,bucket,link,workflow"]);
		if (/no required checks/i.test(c.stderr)) c = await gh(["pr", "checks", n, "-R", w.repo, "--json", "name,state,bucket,link,workflow"]);
		let checks: Check[] = [];
		if (/no checks reported/i.test(c.stderr)) checks = [];
		else if (![0, 1, 8].includes(c.code)) { w.lastError = c.stderr.trim() || `gh pr checks exit ${c.code}`; return "unknown"; }
		else {
			try { checks = (json(c) ?? []) as Check[]; } catch { w.lastError = "gh pr checks: unparseable output"; return "unknown"; }
		}
		const s = summarizeChecks(checks);
		w.progress = `${s.passed}/${s.total}`;
		if (s.failed.length) {
			return {
				verdict: `red - ${s.failed.map((f) => f.name).join(", ")}`, red: true,
				body: [pr.url, "", "Failing checks:", ...s.failed.map((f) => `- ${f.name}${f.workflow ? ` (${f.workflow})` : ""}: ${f.state ?? "fail"} ${f.link ?? ""}`.trimEnd())],
				next: [...(runIdFromLink(s.failed[0].link) ? [`gh run view ${runIdFromLink(s.failed[0].link)} -R ${w.repo} --log-failed`] : [`gh pr checks ${n} -R ${w.repo}`]), "fix, push, then call ci_wait again"],
				logRun: runIdFromLink(s.failed[0].link),
			};
		}
		if (s.total === 0) {
			if (now() - w.registeredAt > NO_CHECKS_GRACE_MS) return { verdict: `no checks reported after ${Math.round((now() - w.registeredAt) / MIN)} min`, body: [pr.url], next: [`gh pr checks ${n} -R ${w.repo}`] };
			return null;
		}
		if (s.pending.length) return null;
		const extra = s.cancelled.length ? ` (cancelled, not counted red: ${s.cancelled.join(", ")})` : "";
		if (w.until === "checks")
			return { verdict: `green - ${s.passed}/${s.total} checks${extra}`, body: [pr.url], next: [`gh pr checks ${n} -R ${w.repo}`, `gh run list -R ${w.repo} --branch ${base} -L1  # base must be green before merging`] };
		if (!auto) return { verdict: `checks green but auto-merge is not set (until: ${w.until})${extra}`, body: [pr.url, `mergeStateStatus: ${pr.mergeStateStatus}`], next: [`merge it, then ci_wait { pr: ${w.pr}, until: "post-merge" }`] };
		return null; // green with auto-merge on: GitHub is about to merge
	}

	async function check(w: Watch) {
		if (now() - w.registeredAt > maxMs) {
			return resolve(w, { verdict: `timed out after ${Math.round((now() - w.registeredAt) / MIN)} min (last: ${w.progress ?? "no data"})`, body: [], next: [w.pr ? `gh pr checks ${w.pr} -R ${w.repo}` : `gh run list -R ${w.repo} -L5`] });
		}
		let v: Verdict | null | "unknown";
		try {
			v = w.pr ? await evalPr(w) : w.run ? await evalRun(w) : await evalRuns(w, w.branch!, undefined, w.registeredAt);
		} catch (e) {
			w.lastError = (e as Error).message;
			v = "unknown";
		}
		if (v === "unknown") {
			w.failures = (w.failures ?? 0) + 1;
			if (w.failures >= maxFailures)
				return resolve(w, { verdict: `cannot read CI (${w.failures} consecutive gh failures)`, body: [`last error: ${w.lastError}`], next: ["gh auth status", w.pr ? `gh pr checks ${w.pr} -R ${w.repo}` : `gh run list -R ${w.repo} -L5`] });
			return;
		}
		w.failures = 0;
		if (v) return resolve(w, v);
	}

	async function tick() {
		if (ticking) return;
		ticking = true;
		try {
			for (const w of [...watches.values()]) await check(w);
			emitState();
		} finally {
			ticking = false;
		}
	}

	function interval() {
		if (fixedPoll) return fixedPoll;
		const youngest = Math.min(...[...watches.values()].map((w) => now() - (w.mergedAt ?? w.registeredAt)));
		return youngest < 10 * MIN ? 30_000 : 120_000;
	}

	function schedule(ms?: number) {
		if (closed || deps.autoPoll === false) return;
		clearTimeout(timer);
		if (!watches.size) return;
		timer = setTimeout(async () => {
			await tick().catch(() => {});
			schedule();
		}, ms ?? interval());
		(timer as { unref?: () => void }).unref?.();
	}

	function persistUpdate(w: Watch) {
		pi.appendEntry("ci-wait", { op: "updated", id: w.id, headSha: w.headSha, mergeSha: w.mergeSha, base: w.base, mergedAt: w.mergedAt });
	}

	function rebuild(entries: any[]) {
		watches.clear();
		let maxSeen = 0;
		for (const e of entries) {
			if (e?.type !== "custom" || e.customType !== "ci-wait" || !e.data) continue;
			const d = e.data;
			if (d.op === "registered" && d.watch) {
				watches.set(d.watch.id, { ...d.watch });
				maxSeen = Math.max(maxSeen, Number(String(d.watch.id).replace(/\D/g, "")) || 0);
			}
			else if (d.op === "updated" && watches.has(d.id)) {
				const w = watches.get(d.id)!;
				for (const k of ["headSha", "mergeSha", "base", "mergedAt"] as const) if (d[k] !== undefined) (w as any)[k] = d[k];
			} else if (d.op === "resolved" || d.op === "cancelled") watches.delete(d.id);
		}
		seq = maxSeen;
	}

	function cancel(id: string) {
		const ids = id === "all" ? [...watches.keys()] : watches.has(id) ? [id] : [];
		for (const i of ids) { watches.delete(i); pi.appendEntry("ci-wait", { op: "cancelled", id: i }); }
		emitState();
		return ids;
	}

	pi.registerTool({
		name: "ci_wait",
		label: "CI wait",
		description:
			"Register a background CI watch and end the turn. Exactly one target: pr (PR number), run (workflow run id) or branch. " +
			"until: 'checks' (default; wake when required checks are all green or any is red), 'merged' (wake on merge, red, conflict or close), " +
			"'post-merge' (after merge, wake when the base-branch workflow runs at the merge commit finish). " +
			"You are re-prompted in-band with a 'CI WAIT RESOLVED' message; do not poll or sleep yourself.",
		promptSnippet: "Wait for CI in the background and get re-prompted when it is actionable",
		promptGuidelines: ["After pushing or enabling auto-merge, use ci_wait instead of sleeping/polling for CI, then end your turn."],
		parameters: {
			type: "object",
			properties: {
				pr: { type: "integer", description: "Pull request number" },
				run: { type: "integer", description: "GitHub Actions run id" },
				branch: { type: "string", description: "Branch whose newest head's workflow runs to wait for" },
				repo: { type: "string", description: "owner/name; default: the repo of the current directory" },
				until: { type: "string", enum: ["checks", "merged", "post-merge"], description: "When to wake (default checks)" },
				note: { type: "string", description: "Reminder of what to do next, echoed in the wake-up message" },
			},
			additionalProperties: false,
		} as any,
		async execute(_id: string, params: any, _signal: unknown, _onUpdate: unknown, ctx: any) {
			if (ctx) ctxRef = ctx;
			const targets = ["pr", "run", "branch"].filter((k) => params[k] !== undefined && params[k] !== "");
			if (targets.length !== 1) throw new Error("ci_wait needs exactly one of pr, run or branch");
			const until: Until = params.until ?? "checks";
			if (until !== "checks" && !params.pr) throw new Error(`until: "${until}" needs a pr`);
			let repo: string = params.repo ?? "";
			if (!repo) {
				const r = await exec(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], { cwd: ctx?.cwd });
				repo = r.stdout.trim();
				if (r.code !== 0 || !repo) throw new Error(`ci_wait: cannot determine repo (pass repo: "owner/name"): ${r.stderr.trim()}`);
			}
			if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error(`ci_wait: repo must be owner/name, got ${repo}`);
			const watch: Watch = { id: `w${++seq}`, repo, until, registeredAt: now(), ...(params.note ? { note: params.note } : {}) };
			if (params.pr) watch.pr = Number(params.pr);
			if (params.run) watch.run = Number(params.run);
			if (params.branch) watch.branch = String(params.branch);
			// A new watch on the same target replaces the old one (typical after a fix-up push).
			for (const w of [...watches.values()]) if (label(w) === label(watch)) { watches.delete(w.id); pi.appendEntry("ci-wait", { op: "cancelled", id: w.id }); }
			watches.set(watch.id, watch);
			pi.appendEntry("ci-wait", { op: "registered", watch });
			emitState();
			schedule(5_000);
			const text = `ci_wait registered: ${watch.id} ${label(watch)} until ${until}. Waiting on CI in the background; ` +
				`you will be re-prompted with "CI WAIT RESOLVED" when it is actionable. End your turn now; do not poll. (/ci-wait to list or cancel)`;
			return { content: [{ type: "text", text }], details: { watch }, terminate: true };
		},
	} as any);

	pi.registerCommand("ci-wait", {
		description: "List active CI watches; /ci-wait cancel <id|all>",
		handler: async (args: string, ctx: any) => {
			const [cmd, id] = args.trim().split(/\s+/);
			if (cmd === "cancel") {
				const gone = cancel(id || "all");
				ctx.ui.notify(gone.length ? `ci-wait: cancelled ${gone.join(", ")}` : `ci-wait: no watch ${id}`, "info");
				return;
			}
			const list = [...watches.values()].map((w) => `${w.id} ${label(w)} until ${w.until} - ${w.progress ?? "pending"}, ${Math.round((now() - w.registeredAt) / MIN)} min${w.failures ? `, ${w.failures} gh failures` : ""}`);
			ctx.ui.notify(list.length ? list.join("\n") : "ci-wait: no active watches", "info");
		},
	});

	pi.on("session_start", async (_event: unknown, ctx: any) => {
		ctxRef = ctx;
		closed = false;
		try { rebuild(ctx.sessionManager?.getBranch?.() ?? []); } catch { watches.clear(); }
		emitState();
		schedule(5_000);
	});

	pi.on("session_shutdown", async () => {
		closed = true;
		clearTimeout(timer);
		timer = undefined;
	});

	return { tick, watches, rebuild };
}

export default function (pi: ExtensionAPI) {
	setup(pi);
}
