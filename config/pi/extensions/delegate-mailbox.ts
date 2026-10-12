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
import { execFile } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MAILBOX = process.env.PI_DELEGATE_MAILBOX || path.join(os.homedir(), ".pi/agent/delegate-mailbox");
const ACK_DIR = path.join(MAILBOX, "ack");
const STATE_DIR = path.join(MAILBOX, "state");
// Settle delay before reading a freshly created record: watch-child writes it
// with a shell redirect, so an event can fire before the content lands.
const SETTLE_MS = 300;

export default function (pi: ExtensionAPI) {
	const pane = process.env.TMUX_PANE || "";
	let watcher: fs.FSWatcher | null = null;
	const delivered = new Set<string>();

	const addressedToUs = (content: string): boolean =>
		pane !== "" && content.match(/^- parent: `([^`]+)`$/m)?.[1] === pane;
	const steering = (content: string): boolean =>
		content.split("\n\n", 1)[0].split("\n").includes('- kind: `steer`');
	let closed = false;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let scanning = false;
	let rescan = false;

	async function verification(file: string, content: string): Promise<string> {
		if (steering(content) || !/^\s*[^<>\n]+: DONE (?:[a-fA-F0-9]{7,40}|none) - [^\s<>]+(?: ci:[0-9]+)?(?: pr:[1-9][0-9]*)?\s*$/m.test(content)) return content;
		const evidence = await new Promise<string>((resolve) => {
			execFile(process.env.PI_DELEGATE_VERIFY || "delegate-verify", ["--record", file],
				{ timeout: 90_000, maxBuffer: 64 * 1024 }, (error, stdout, stderr) => {
					resolve(error ? `FAIL: ${stdout || stderr || error.message}` : stdout);
				});
		});
		return `AUTOMATIC DONE VERIFICATION: ${evidence.trim()}\nClaims remain subject to the parent's repository gates.\n\n${content}`;
	}

	function state(file: string, status: string) {
		fs.mkdirSync(STATE_DIR, { recursive: true });
		const target = path.join(STATE_DIR, `${path.basename(file)}.json`);
		fs.writeFileSync(`${target}.tmp`, JSON.stringify({ state: status, pane, at: new Date().toISOString() }) + "\n");
		fs.renameSync(`${target}.tmp`, target);
	}

	function ack(file: string) {
		fs.mkdirSync(ACK_DIR, { recursive: true });
		fs.renameSync(file, path.join(ACK_DIR, path.basename(file)));
	}

	function deliver(file: string, content: string): boolean {
		const message = {
			customType: "delegate-mailbox",
			content: steering(content)
				? `DELEGATION STEERING — record ${file}. Apply these instructions at this turn boundary.\n\n${content}`
				: `DELEGATION FINISHED — record ${file} (auto-acked to ${ACK_DIR}; do not mv it).\n` +
					`Process the completion below: verify the child's claims, then decide next steps.\n\n` + content,
			details: { record: file, steering: steering(content) },
			display: true,
		};
		try {
			pi.sendMessage(message, steering(content)
				? { triggerTurn: true, deliverAs: "steer" }
				: { triggerTurn: true });
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

	async function scan() {
		if (closed) return;
		if (scanning) { rescan = true; return; }
		scanning = true;
		try {
		await scanRecords();
		} finally {
			scanning = false;
			if (rescan && !closed) { rescan = false; void scan(); }
		}
	}

	async function scanRecords() {
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
			content = await verification(file, content);
			if (closed) return;
			delivered.add(file);
			try {
				if (steering(content)) state(file, "accepted");
			} catch { delivered.delete(file); continue; }
			if (!deliver(file, content)) {
				delivered.delete(file);
				try { if (steering(content)) state(file, "queued"); } catch { /* Retry later. */ }
				continue;
			}
			try {
				// Steering stays durable until Pi actually starts its custom message.
				// A restart before that boundary replays the pending record.
				if (!steering(content)) ack(file);
			} catch {
				// Ack failed; watch-child re-nudges keep the at-least-once contract.
			}
		}
	}

	pi.on("message_start", async (event) => {
		const message = event.message;
		if (message.role !== "custom" || message.customType !== "delegate-mailbox") return;
		const details = message.details as { record?: string; steering?: boolean } | undefined;
		if (!details?.steering || !details.record || !delivered.has(details.record)) return;
		try {
			state(details.record, "delivered");
			ack(details.record);
		} catch { /* The pending record survives for replay after restart. */ }
	});

	pi.on("session_start", async (_event, ctx) => {
		closed = false;
		delivered.clear();
		if (pane === "") return; // not under tmux: no delegations can address us
		fs.mkdirSync(ACK_DIR, { recursive: true });
		await scan(); // catch up on records that arrived while no session was running
		watcher = fs.watch(MAILBOX, (_type, filename) => {
			if (!filename || !filename.toString().endsWith(".md")) return;
			clearTimeout(timer);
			timer = setTimeout(() => { void scan(); }, SETTLE_MS);
		});
		if (ctx.hasUI) ctx.ui.notify(`delegate-mailbox: watching ${MAILBOX} for ${pane}`, "info");
	});

	pi.on("session_shutdown", async () => {
		closed = true;
		clearTimeout(timer);
		watcher?.close(); // idempotent: close() on a closed watcher is a no-op
		watcher = null;
	});
}
