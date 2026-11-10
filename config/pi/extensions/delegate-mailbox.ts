// Session-ID-only delivery. Pane/window fields are diagnostics, never authority.
// A new/forked chat cannot consume a previous occupant's mail; resuming the same
// session elsewhere can. Legacy records are copied to quarantine/, not ack/; originals stay intact.
// Pi 1.5.2 replaces the extension runtime and its queues on new/resume/fork.
// Async verification must also check its generation before send or ack.
// Knob: PI_DELEGATE_MAILBOX (default ~/.pi/agent/delegate-mailbox).

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { execFile } from "node:child_process";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const MAILBOX = process.env.PI_DELEGATE_MAILBOX || path.join(os.homedir(), ".pi/agent/delegate-mailbox");
const ACK_DIR = path.join(MAILBOX, "ack");
const STATE_DIR = path.join(MAILBOX, "state");
// Settle delay before reading a freshly created record: watch-child writes it
// with a shell redirect, so an event can fire before the content lands.
const SETTLE_MS = 300;

export default function (pi: ExtensionAPI) {
	let watcher: fs.FSWatcher | null = null;
	const delivered = new Set<string>();
	let sessionId = "";
	let context: ExtensionContext | undefined;
	let generation = 0;
	const base = process.env.XDG_STATE_HOME || path.join(os.homedir(), ".local/state");
	const readyFile = path.join(base, "pi-panes", `${process.pid}.mailbox`);
	function publishReady() {
		const stat = fs.readFileSync(`/proc/${process.pid}/stat`, "utf8").split(") ").at(-1)!.split(" ");
		fs.mkdirSync(path.dirname(readyFile), { recursive: true });
		fs.writeFileSync(`${readyFile}.tmp`, JSON.stringify({ protocol: 2, session_id: sessionId, mailbox: fs.realpathSync(MAILBOX),
			start_ticks: stat[19], boot_id: fs.readFileSync("/proc/sys/kernel/random/boot_id", "utf8").trim() }), { mode: 0o600 });
		fs.renameSync(`${readyFile}.tmp`, readyFile);
	}
	const validId = (id: unknown): id is string => typeof id === "string" && /^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$/.test(id);
	const recipient = (content: string): string => {
		const fields = [...content.matchAll(/^- recipient_session_id: `([^`]+)`$/gm)];
		return fields.length === 1 && validId(fields[0][1]) ? fields[0][1] : "";
	};
	const current = (epoch: number): boolean => !closed && epoch === generation &&
		!!sessionId && context?.sessionManager.getSessionId() === sessionId;
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
		fs.writeFileSync(`${target}.tmp`, JSON.stringify({ state: status, recipient_session_id: sessionId, pane: process.env.TMUX_PANE || "", at: new Date().toISOString() }) + "\n");
		fs.renameSync(`${target}.tmp`, target);
	}

	function ack(file: string) {
		fs.mkdirSync(ACK_DIR, { recursive: true });
		fs.renameSync(file, path.join(ACK_DIR, path.basename(file)));
	}

	function deliver(file: string, content: string): boolean {
		const waitingOnCI = /^- verdict: \*\*waiting on CI\*\*$/m.test(content);
		const message = {
			customType: "delegate-mailbox",
			content: steering(content)
				? `DELEGATION STEERING — record ${file}. Apply these instructions at this turn boundary.\n\n${content}`
				: waitingOnCI
					? `DELEGATION WAITING ON CI — record ${file} (auto-acked to ${ACK_DIR}; do not mv it).\n` +
						`The child has an active CI watch and has not finished.\n\n${content}`
					: `DELEGATION FINISHED — record ${file} (auto-acked to ${ACK_DIR}; do not mv it).\n` +
						`Process the completion below: verify the child's claims, then decide next steps.\n\n${content}`,
			details: { record: file, steering: steering(content), recipient_session_id: sessionId },
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
				return false; // leave durable; never fall back to pane keystrokes
			}
		}
		return true;
	}

	async function scan() {
		if (!current(generation)) return;
		if (scanning) { rescan = true; return; }
		scanning = true;
		try {
		await scanRecords(generation);
		} finally {
			scanning = false;
			if (rescan && !closed) { rescan = false; void scan(); }
		}
	}

	async function scanRecords(epoch: number) {
		let names: string[];
		try {
			names = fs.readdirSync(MAILBOX).filter((n) => n.endsWith(".mail") || n.endsWith(".md"));
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
			if (!current(epoch)) return;
			const to = recipient(content);
			if (!to) {
				// No safe inference from a pane-only record, even if its pane is ours.
				try {
					const quarantine = path.join(MAILBOX, "quarantine");
					fs.mkdirSync(quarantine, { recursive: true });
					// Preserve the original for still-running legacy owners during mixed rollout.
					fs.copyFileSync(file, path.join(quarantine, name), fs.constants.COPYFILE_EXCL);
					if (context?.hasUI) context.ui.setStatus("mailbox-legacy", "Mailbox: legacy/invalid records in quarantine (not delivered)");
				} catch { /* Another consumer may have quarantined it. */ }
				continue;
			}
			if (to !== sessionId) continue;
			const original = content;
			content = await verification(file, content);
			if (!current(epoch)) return;
			try { if (fs.readFileSync(file, "utf8") !== original) continue; } catch { continue; }
			delivered.add(file);
			try {
				state(file, "accepted");
			} catch { delivered.delete(file); continue; }
			if (!deliver(file, content)) {
				delivered.delete(file);
				try { state(file, "queued"); } catch { /* Retry later. */ }
				continue;
			}
			// All records stay durable until Pi actually starts their message.
		}
	}

	pi.on("message_start", async (event, ctx) => {
		const message = event.message;
		if (message.role !== "custom" || message.customType !== "delegate-mailbox") return;
		const details = message.details as { record?: string; recipient_session_id?: string } | undefined;
		if (!current(generation) || ctx.sessionManager.getSessionId() !== sessionId ||
			details?.recipient_session_id !== sessionId || !details.record || !delivered.has(details.record)) return;
		try {
			if (recipient(fs.readFileSync(details.record, "utf8")) !== sessionId) return;
			state(details.record, "delivered");
			ack(details.record);
		} catch { /* The pending record survives for replay after restart. */ }
	});

	pi.on("session_start", async (_event, ctx) => {
		stop();
		closed = false;
		context = ctx;
		const id = ctx.sessionManager.getSessionId();
		sessionId = validId(id) ? id : "";
		delivered.clear();
		if (!sessionId) return; // no identity, no delivery; tmux is not required
		fs.mkdirSync(ACK_DIR, { recursive: true });
		const epoch = generation;
		watcher = fs.watch(MAILBOX, (_type, filename) => {
			if (!filename || !/\.(?:mail|md)$/.test(filename.toString())) return;
			clearTimeout(timer);
			timer = setTimeout(() => { void scan(); }, SETTLE_MS);
		});
		publishReady(); // sender must see BOTH publisher identity and this consumer capability
		await scan(); // watcher first: no gap while verification is running
		if (current(epoch) && ctx.hasUI) ctx.ui.notify(`delegate-mailbox: watching for session ${sessionId}`, "info");
	});

	function stop() {
		generation++;
		closed = true;
		clearTimeout(timer);
		watcher?.close(); // idempotent: close() on a closed watcher is a no-op
		watcher = null;
		try { fs.rmSync(readyFile, { force: true }); } catch { /* no authority after teardown */ }
	}
	pi.on("session_shutdown", async () => { stop(); });
}
