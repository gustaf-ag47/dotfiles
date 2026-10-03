// delegate-mailbox.ts — in-band delivery for delegation completion records.
//
// Problem (measured 2026-10-03): watch-child.sh notifies the parent pi session
// with tmux send-keys, and a TUI swallows keystrokes without trace — a child
// finished, 8 nudges fired, none reached the parent's context; the human closed
// the loop. The mailbox backstop is pull-only: nothing wakes an idle parent.
//
// Fix: this extension runs INSIDE the parent pi session and watches the mailbox
// directory itself. When a record appears whose `parent:` pane matches this
// session's $TMUX_PANE, it injects the record as a custom message via
// pi.sendMessage(..., { triggerTurn: true }) — no keystrokes involved — and
// acks it by moving it to ack/, which stops watch-child's keystroke re-nudges
// (they remain as fallback for parents without this extension).
//
// Scope rules:
// - Only records addressed to this pane are ingested; a machine-global mailbox
//   with several pi sessions must not cross-deliver or cross-ack.
// - Sweep on session_start (catch-up after restart/reboot), fs.watch afterward.
// - Watcher starts in session_start, never in the factory; closed idempotently
//   in session_shutdown (docs/extensions.md lifecycle contract).
//
// Knobs: PI_DELEGATE_MAILBOX (default ~/.pi/agent/delegate-mailbox).

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MAILBOX = process.env.PI_DELEGATE_MAILBOX || path.join(os.homedir(), ".pi/agent/delegate-mailbox");
const ACK_DIR = path.join(MAILBOX, "ack");
// Settle delay before reading a freshly created record: watch-child writes it
// with a shell redirect, so an event can fire before the content lands.
const SETTLE_MS = 300;

export default function (pi: ExtensionAPI) {
	const pane = process.env.TMUX_PANE || "";
	let watcher: fs.FSWatcher | null = null;
	const delivered = new Set<string>();

	const addressedToUs = (content: string): boolean =>
		pane !== "" && content.includes(`- parent: \`${pane}\``);

	function deliver(file: string, content: string): boolean {
		const message = {
			customType: "delegate-mailbox",
			content:
				`DELEGATION FINISHED — record ${file} (auto-acked to ${ACK_DIR}; do not mv it).\n` +
				`Process the completion below: verify the child's claims, then decide next steps.\n\n` +
				content,
			display: true,
		};
		try {
			pi.sendMessage(message, { triggerTurn: true });
		} catch {
			// Mid-stream and triggerTurn alone was rejected: queue behind the turn.
			try {
				pi.sendMessage(message, { triggerTurn: true, deliverAs: "followUp" });
			} catch {
				return false; // leave unacked; keystroke fallback still applies
			}
		}
		return true;
	}

	function scan() {
		let names: string[];
		try {
			names = fs.readdirSync(MAILBOX).filter((n) => n.endsWith(".md"));
		} catch {
			return; // mailbox may not exist yet
		}
		for (const name of names.sort()) {
			const file = path.join(MAILBOX, name);
			if (delivered.has(file)) continue;
			let content = "";
			try {
				content = fs.readFileSync(file, "utf-8");
			} catch {
				continue; // raced with an ack/removal
			}
			if (!addressedToUs(content)) continue;
			if (!deliver(file, content)) continue;
			delivered.add(file);
			try {
				fs.mkdirSync(ACK_DIR, { recursive: true });
				fs.renameSync(file, path.join(ACK_DIR, name));
			} catch {
				// Ack failed; watch-child re-nudges keep the at-least-once contract.
			}
		}
	}

	pi.on("session_start", async (_event, ctx) => {
		if (pane === "") return; // not under tmux: no delegations can address us
		fs.mkdirSync(ACK_DIR, { recursive: true });
		scan(); // catch up on records that arrived while no session was running
		watcher = fs.watch(MAILBOX, (_type, filename) => {
			if (!filename || !filename.toString().endsWith(".md")) return;
			setTimeout(scan, SETTLE_MS);
		});
		if (ctx.hasUI) ctx.ui.notify(`delegate-mailbox: watching ${MAILBOX} for ${pane}`, "info");
	});

	pi.on("session_shutdown", async () => {
		watcher?.close(); // idempotent: close() on a closed watcher is a no-op
		watcher = null;
	});
}
