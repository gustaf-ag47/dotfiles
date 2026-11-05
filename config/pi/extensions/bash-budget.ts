// bash-budget.ts — bound bash tool timeouts, refuse waits inside a tool call,
// and tell the model how to run long jobs.
//
// Why (2026-11-01): Anthropic strict tool mode turns pi's optional `timeout`
// into a required field, the description says "no default timeout", and the
// Claude Code identity (anthropic-pool.ts) primes Claude Code's millisecond
// unit. Agents picked 1800-3600 s "ceilings" (and ms-looking values such as
// 300000 s = 83 h), then hid a 10+ minute test run behind `| grep | head`.
// Report: $NOTES/Homelab/agent-runs/2026-11-01-pi-long-timeouts-report.md
//
// Why the sleep block (2026-11-05): with the cap advertised as "900 s", agents
// sized waits to it (`sleep 895` / timeout 900) or to just under 5 min
// (`sleep 280` / timeout 300): 2361 such calls in 3 days. Every sleep-then-check
// round is a full model turn that re-reads the context, and it blocks the
// session. Claude Code blocks foreground sleeps for the same habit
// (anthropics/claude-code#93111). Now a bash call that sleeps >= 30 s in total,
// sleeps >= 10 s per iteration of a loop, or uses `gh ... --watch` / `gh run
// watch` is blocked with a pointer to `ci_wait` / `wait_for` (wait-for.ts),
// which end the turn and wake the agent once.
// Report: $NOTES/Homelab/agent-runs/2026-11-05-pi-sleep-waits-report.md
//
// tool_call: missing/invalid timeout -> 600 s; values >= 10000 are read as
// milliseconds; everything is clamped (not blocked) to PI_BASH_MAX_TIMEOUT
// (default 900 s). event.input is mutable per pi's ToolCallEvent contract and
// the hook also fires for codemode-nested calls. PI_BASH_ALLOW_SLEEP=1 turns
// the sleep block off (operator escape hatch, not for agents).

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const DEFAULT_TIMEOUT_S = 600;
export const DEFAULT_MAX_TIMEOUT_S = 900;
export const MS_THRESHOLD = 10_000;
export const MAX_SLEEP_S = 30; // total of plain sleeps in one call
export const MAX_LOOP_SLEEP_S = 10; // per-iteration sleep inside a loop

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

const UNIT: Record<string, number> = { "": 1, s: 1, m: 60, h: 3600, d: 86400 };

/**
 * Pure: drop the parts of a command that do not run inside this tool call:
 * heredoc bodies (scripts being written), commands handed to tmux, nohup,
 * setsid or systemd-run (they run detached) with their quoted arguments,
 * `cmd &` background jobs, and quoted strings that are data (grep patterns,
 * echo text) rather than code run by `bash -c`, `eval` or `ssh`.
 */
export function foregroundPart(command: string): string {
	let s = command.replace(/<<-?\s*(['"]?)([A-Za-z_][\w]*)\1[^\n]*\n[\s\S]*?\n[ \t]*\2[ \t]*(?=\n|$)/g, "<<heredoc");
	const quoted = String.raw`(?:'[^']*'|"(?:\\.|[^"\\])*"|[^'"\n;&|])*`;
	s = s.replace(new RegExp(String.raw`\b(?:tmux\s+(?:new-window|neww|split-window|splitw|new-session|new|send-keys|send|respawn-pane|respawnp|respawn-window|respawnw|run-shell|run)|nohup|setsid|systemd-run|disown)\b${quoted}`, "g"), " detached ");
	s = s.replace(/'([^']*)'|"((?:\\.|[^"\\])*)"/g, (m, sq: string | undefined, dq: string | undefined, offset: number) => {
		const before = s.slice(Math.max(0, offset - 80), offset);
		const runs = /(?:\b(?:ba|z|da)?sh\s+(?:-\w+\s+)*-\w*c\s*|\beval\s+|\bssh\b[^;\n|&'"]*)$/.test(before);
		return runs ? ` ${sq ?? dq} ` : "''";
	});
	// `( ... ) &` / `{ ...; } &` groups and `cmd ... &` (a lone &, not &&, |&,
	// 2>&1 or &>) run in the background.
	s = s.replace(/\((?:[^()]|\([^()]*\))*\)\s*&(?![&>\d-])|\{[^{}]*\}\s*&(?![&>\d-])/g, " detached ");
	s = s.replace(/(^|[\n;]|&&|\|\|)([^\n;&|]*?)(?<![&|<>])&(?![&>\d-])/g, "$1 detached ");
	return s;
}

/**
 * Pure: why this command waits inside the tool call, or null. Sleeps with a
 * variable argument are ignored (no false positives on `sleep "$n"`).
 */
export function waitReason(command: string, maxSleep = MAX_SLEEP_S, maxLoopSleep = MAX_LOOP_SLEEP_S): string | null {
	const s = foregroundPart(command);
	if (/\bgh\s+(?:pr\s+checks\b[^\n;|&]*--watch|run\s+watch\b)/.test(s)) return "`gh ... --watch` / `gh run watch` holds the call open until CI finishes";
	let depth = 0;
	let total = 0;
	let longest = 0;
	const re = /\b(do|done)\b|\bsleep\s+((?:\d+(?:\.\d+)?[smhd]?\s*)+)(?=$|[\s;&|)`])/g;
	for (let m: RegExpExecArray | null; (m = re.exec(s)); ) {
		if (m[1] === "do") { depth++; continue; }
		if (m[1] === "done") { depth = Math.max(0, depth - 1); continue; }
		const secs = m[2].trim().split(/\s+/).reduce((a, part) => {
			const p = part.match(/^(\d+(?:\.\d+)?)([smhd]?)$/);
			return p ? a + Number(p[1]) * UNIT[p[2]] : a;
		}, 0);
		if (depth > 0 && secs >= maxLoopSleep) return `\`sleep ${m[2].trim()}\` inside a loop polls from within the tool call`;
		total += secs;
		longest = Math.max(longest, secs);
	}
	if (total >= maxSleep) return total === longest ? `\`sleep ${longest}\` holds the tool call open to wait` : `sleeps totalling ${total}s hold the tool call open to wait`;
	return null;
}

export function blockMessage(reason: string): string {
	return [
		`Blocked by bash-budget: ${reason}.`,
		"Do not wait inside a tool call. It blocks the session, and every sleep-then-check round is another model turn that re-reads the whole context; a single wake-up costs one cache read.",
		"Instead, end your turn after registering a wait - you are re-prompted when it resolves:",
		"- CI, PRs, merges, post-merge runs: ci_wait { pr | run | branch, until }",
		"- anything else: wait_for { command: \"<quick check that exits 0 when done>\" } | { file, pattern, fail_pattern } | { pane: \"%12\", pattern } | { pid }",
		"- long jobs: start them in a tmux window with output tee'd to a log, then wait_for the log's completion line or the pane exiting.",
		`Short settles (< ${MAX_SLEEP_S}s total) and tight until-loops (< ${MAX_LOOP_SLEEP_S}s per iteration, bounded by the timeout) are fine. Do not split a long sleep into shorter calls.`,
	].join("\n");
}

export const GUIDELINES = [
	"Bash `timeout` is in SECONDS (not milliseconds). Size it to the expected runtime plus margin (most commands: 30-120).",
	"Prefer targeted checks (one package, one test) over full suites; the pre-commit hook and CI are the full checks.",
	"Never wait inside a tool call (`sleep N; check`, sleep/poll loops, `--watch`); such calls are blocked. Register the wait and end your turn: `ci_wait` for CI/PRs, `wait_for` for anything else (log line, command succeeding, tmux pane or process exit). One wake-up reads the prompt cache once; polling re-reads the whole context every round.",
	"Long jobs (over ~5 minutes): start them in their own tmux window with output tee'd to a log on persistent disk, then `wait_for` the log's completion line or the pane exiting.",
	"Never filter a long run's output to nothing (`| grep FAIL | head`): tee the full output to a log and print a progress line per step so the operator can see it is alive.",
];

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event) => {
		if (event.toolName !== "bash") return;
		const input = event.input as { timeout?: unknown; command?: unknown };
		input.timeout = budgetTimeout(input.timeout);
		if (process.env.PI_BASH_ALLOW_SLEEP === "1" || typeof input.command !== "string") return;
		const reason = waitReason(input.command);
		if (reason) return { block: true, reason: blockMessage(reason) };
	});

	pi.on("before_agent_start", async (event) => {
		for (const g of GUIDELINES) {
			if (!event.systemPromptOptions.promptGuidelines.includes(g)) {
				event.systemPromptOptions.promptGuidelines.push(g);
			}
		}
	});
}
