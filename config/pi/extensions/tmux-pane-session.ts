// tmux-pane-session: tell tmux-pi-panes which session file this pi process is
// in, so a tmux-resurrect restore can run `pi --session <file>` in the right
// pane. pi does not keep its .jsonl open, so the file is not visible in
// /proc/<pid>/fd, and PI_SESSION_FILE is only set for pi's children.
//
// Writes $XDG_STATE_HOME/pi-panes/<pid> (the session file path) on every
// session_start (startup, new, resume, fork, reload). Not removed on
// session_shutdown: that also fires when the machine shuts down, and the final
// tmux save must still see it. tmux-pi-panes prunes files of dead pids, and
// only reads the file of a pid that is a live pi in a pane. Only inside tmux.
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function stateFile(): string {
	const base = process.env.XDG_STATE_HOME || join(homedir(), ".local/state");
	return join(base, "pi-panes", String(process.pid));
}

export default function (pi: ExtensionAPI) {
	if (!process.env.TMUX_PANE) return;

	pi.on("session_start", async (_event, ctx) => {
		const sessionFile = ctx.sessionManager.getSessionFile();
		const file = stateFile();
		try {
			if (!sessionFile) {
				rmSync(file, { force: true });
				return;
			}
			mkdirSync(join(file, ".."), { recursive: true });
			writeFileSync(file, `${sessionFile}\n`);
		} catch {
			// Best effort: losing the mapping only costs an automatic resume.
		}
	});

}
