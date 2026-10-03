// merge-blockers.ts — inject merge-hygiene guidelines into every pi session
// that runs inside a git repository.
//
// Why (2026-10-03): an agent merged PR #20 into a master whose CI was already
// red, the PR itself added an unformatted Lua file that a workflow gates on
// (StyLua), and the next PR was declared "done" without anyone running
// `gh pr checks`. Three misses, one cause: nothing in the agent's context told
// it that merge blockers exist and must be checked — the knowledge lived only
// in the operator's head.
//
// This appends a few guideline bullets to the system prompt (via
// before_agent_start → systemPromptOptions.promptGuidelines, the
// cache-friendly mechanism the docs recommend over prompt replacement).
// Guidelines are advice the model sees every turn of the session; they cost
// ~70 tokens and only when the session is inside a git repo.

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const GUIDELINES = [
	"Merge blockers: before opening a PR, merging one, or reporting branch work as done, check CI — `gh pr checks <n>` for the PR and `gh run list --branch <base> -L1` for the target branch. A red base branch is a blocker you inherit: investigate it first, never merge onto it silently.",
	"After you merge, confirm the post-merge run on the base branch is green before building anything on top of it.",
	"Run the formatters and linters that CI gates on (check the workflows under .github/workflows) locally before committing — a clean local test run does not imply a clean lint/format gate.",
	"Do not report delegated or sub-agent work as complete from its own claims; verify against the repo's gates (tests, linters, CI) yourself.",
];

// Pure-fs walk-up: is `dir` inside a git repo/worktree? No subprocess in the
// prompt-build hot path. `.git` is a dir in a normal checkout, a file in
// worktrees/submodules — existsSync covers both.
function insideGitRepo(dir: string): boolean {
	let current = path.resolve(dir);
	for (;;) {
		if (fs.existsSync(path.join(current, ".git"))) return true;
		const parent = path.dirname(current);
		if (parent === current) return false;
		current = parent;
	}
}

export default function (pi: ExtensionAPI) {
	const cache = new Map<string, boolean>();

	pi.on("before_agent_start", async (event, ctx) => {
		const cwd = ctx.cwd || process.cwd();
		let inRepo = cache.get(cwd);
		if (inRepo === undefined) {
			inRepo = insideGitRepo(cwd);
			cache.set(cwd, inRepo);
		}
		if (!inRepo) return;
		for (const g of GUIDELINES) {
			if (!event.systemPromptOptions.promptGuidelines.includes(g)) {
				event.systemPromptOptions.promptGuidelines.push(g);
			}
		}
	});
}
