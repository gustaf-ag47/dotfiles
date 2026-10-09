/**
 * Jev context-efficiency extension: file scouting + freshness-aware
 * duplicate-read suppression.
 *
 * See operator notes: jev-context-extension-implementation.md for the full brief
 * and writeup (API verification notes, retention design, known limitations).
 *
 * Default is OFF: no tool is declared to the model, no network call is ever
 * made, and nothing runs at startup beyond registering (inactive) tools and
 * event listeners.
 *
 *   /jev-context status   -- mode + stats, UI-only, no model messages
 *   /jev-context local    -- duplicate-read suppression only, no network ever
 *   /jev-context on       -- also enables scout_files (sends explicit goal +
 *                             explicit allowed file list to TypeSafe); asks
 *                             for confirmation via ctx.ui when available,
 *                             requires PI_JEV_CONTEXT=on in noninteractive
 *                             modes (no silent acceptance)
 *   /jev-context off      -- deactivates both tools, aborts any in-flight
 *                             scouting, clears retained read-cache state
 *
 * Deliberately NOT implemented here, per the brief:
 *   - No automatic file collection of any kind; scout_files only ever sees
 *     the explicit, bounded file list the model (acting on user intent)
 *     passes it.
 *   - No conflation with /jev (config/pi/extensions/jev.ts): that extension's
 *     task-class observation is a separate, pre-existing feature with its own
 *     consent model. Enabling scouting here never enables or implies it, and
 *     vice versa.
 *   - No safety-gate automation, no goal-completion or compaction behavior
 *     changes, no new implicit model choice.
 */
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import fs from "node:fs";
import path from "node:path";
import { Type } from "typebox";
import { resolveMode as resolveJevApiMode } from "../lib/jev.mjs";
import {
  buildDedupMarker,
  canonicalizeCwd,
  clearConsentCwd,
  clearRetention,
  consentValidForCwd,
  createCacheState,
  digestContent,
  formatStatusLines,
  isDedupWorthwhile,
  isImagePath,
  lookupCache,
  makeCacheKey,
  mergeScoutStats,
  readFileBounded,
  recomputeVisibility,
  recordConsentCwd,
  recordDedupedRead,
  recordFullRead,
  recordScoutError,
  resolveEnvOptIn,
  sha256Hex,
  sumTextLength,
} from "../lib/jev-context.mjs";

type Mode = "off" | "local" | "on";

const READ_TOOL_NAME = "read_context";
const SCOUT_TOOL_NAME = "scout_files";

const SCOUT_MODULE_URL = new URL("../lib/jev-scout.mjs", import.meta.url).href;

const PRIVACY_EXPLANATION =
	"Enabling scouting adds a scout_files tool that sends your explicit goal text and the content of " +
	"files you (or the model, acting on your request) explicitly list -- tracked repo files only, no " +
	"globs, max 8 paths per call -- to TypeSafe (typesafe.ai) for relevance triage. Nothing is collected " +
	"automatically: every file sent is named in that call's argument list. Local duplicate-read " +
	"suppression (read_context) stays available either way and never sends anything externally.";

const ReadContextParams = Type.Object({
	path: Type.String({ description: "Path to the file to read (relative or absolute)" }),
	offset: Type.Optional(Type.Number({ description: "Line number to start reading from (1-indexed)" })),
	limit: Type.Optional(Type.Number({ description: "Maximum number of lines to read" })),
	force: Type.Optional(
		Type.Boolean({ description: "Force a fresh full read even if an unchanged cached result is visible" }),
	),
});

const ScoutFilesParams = Type.Object({
	goal: Type.String({ maxLength: 1000, description: "Explicit, short description of what you're trying to find or confirm (<=1000 chars)" }),
	paths: Type.Array(Type.String(), {
		minItems: 1,
		maxItems: 8,
		description: "Explicit list of tracked repo file paths to triage for relevance (no globs, max 8)",
	}),
});

interface ReadContextDetails {
	dedup: boolean;
	path: string;
	offset?: number;
	limit?: number;
	contentHash?: string;
	priorToolCallId?: string;
	bypassReason?: string;
}

export default function (
	pi: ExtensionAPI,
	loadScoutModule: () => Promise<any> = () => import(/* @vite-ignore */ SCOUT_MODULE_URL),
) {
	let mode: Mode = "off";
	const cacheState = createCacheState();
	let scoutController: AbortController | null = null;

	function setToolActive(name: string, active: boolean) {
		const current = pi.getActiveTools();
		const has = current.includes(name);
		if (active && !has) pi.setActiveTools([...current, name]);
		else if (!active && has) pi.setActiveTools(current.filter((n) => n !== name));
	}

	/** Never activate/keep read_context active when the native `read` tool isn't active: a wrapper
	 * around a tool the user has deliberately turned off would either be useless or, worse, give the
	 * model a path back to file contents the user disabled -- and per the brief this extension must
	 * never re-enable a user-disabled read. */
	function nativeReadAvailable(): boolean {
		return pi.getActiveTools().includes("read");
	}

	function abortScouting() {
		if (scoutController) {
			scoutController.abort();
			scoutController = null;
		}
	}

	function activateLocal(ctx: { ui: { notify: (m: string, l?: "info" | "warning" | "error") => void } }) {
		mode = "local";
		if (nativeReadAvailable()) {
			setToolActive(READ_TOOL_NAME, true);
		} else {
			ctx.ui.notify("jev-context: native read tool is disabled; read_context stays inactive", "warning");
		}
		setToolActive(SCOUT_TOOL_NAME, false);
		abortScouting();
		clearConsentCwd(cacheState);
	}

	function activateOn(ctx: { ui: { notify: (m: string, l?: "info" | "warning" | "error") => void } }, canonicalCwd: string) {
		mode = "on";
		abortScouting(); // never let an earlier controller survive a second activation
		if (nativeReadAvailable()) {
			setToolActive(READ_TOOL_NAME, true);
		} else {
			ctx.ui.notify("jev-context: native read tool is disabled; read_context stays inactive", "warning");
		}
		setToolActive(SCOUT_TOOL_NAME, true);
		scoutController = new AbortController();
		recordConsentCwd(cacheState, canonicalCwd);
	}

	function deactivate() {
		mode = "off";
		setToolActive(READ_TOOL_NAME, false);
		setToolActive(SCOUT_TOOL_NAME, false);
		abortScouting();
		clearConsentCwd(cacheState);
		clearRetention(cacheState);
	}

	/** Resets any command-granted "on" consent without disturbing an explicit local mode. Used on
	 * session switch/fork/reload so a file-upload consent granted in one repo/session never silently
	 * carries into another (see operator notes: jev-context-extension-implementation.md, consent scope). */
	function resetConsentOnLifecycleBoundary() {
		abortScouting();
		clearConsentCwd(cacheState);
		if (mode === "on") {
			mode = "local";
			setToolActive(SCOUT_TOOL_NAME, false);
		}
		clearRetention(cacheState);
	}

	function scoutConfidenceLabel(confidence: unknown): string {
		return typeof confidence === "number" && Number.isFinite(confidence) ? ` (${confidence.toFixed(2)})` : "";
	}

	async function attemptEnableOn(ctx: { hasUI: boolean; ui: { confirm: (t: string, m: string) => Promise<boolean>; notify: (m: string, l?: "info" | "warning" | "error") => void }; cwd: string }): Promise<boolean> {
		const jevApiMode = resolveJevApiMode({ env: process.env });
		if (jevApiMode === "off") {
			ctx.ui.notify("jev-context: Jev API disabled via PI_JEV_MODE=off; local mode still available", "warning");
			return false;
		}
		const envOptIn = resolveEnvOptIn(process.env);
		if (ctx.hasUI) {
			const confirmed = await ctx.ui.confirm("Enable Jev file scouting?", PRIVACY_EXPLANATION);
			if (!confirmed) {
				ctx.ui.notify("jev-context: scouting not enabled", "info");
				return false;
			}
		} else if (envOptIn !== "on") {
			ctx.ui.notify(
				"jev-context: noninteractive mode requires PI_JEV_CONTEXT=on to enable scouting (no silent acceptance); staying local/off",
				"warning",
			);
			return false;
		}
		activateOn(ctx, canonicalizeCwd(fs, ctx.cwd));
		return true;
	}

	function jevApiStatusNote(): string {
		const jevApiMode = resolveJevApiMode({ env: process.env });
		return jevApiMode === "off" ? "disabled (PI_JEV_MODE=off)" : "available";
	}

	// -------------------------------------------------------------------------
	// read_context: wraps the built-in `read` tool via ctx.executeTool so Pi's
	// own read stays the single source of truth for file access, truncation,
	// and error behavior. Only adds freshness-aware dedup on top.
	// -------------------------------------------------------------------------
	pi.registerTool({
		name: READ_TOOL_NAME,
		label: "Read (context-aware)",
		description:
			"Read a file exactly like the built-in read tool (path, offset, limit), but suppresses an unchanged " +
			"duplicate of a full result still visible in this conversation and returns a short marker instead. " +
			"Pass force:true to force a fresh full read regardless of cache state. Falls through to a plain read " +
			"for images, unreadable paths, or anything that can't be safely hashed.",
		promptSnippet: "Prefer read_context over read: suppresses safe duplicate re-reads of unchanged files",
		parameters: ReadContextParams,
		exposure: "direct",
		defaultActive: false,
		prepareLoadout(loadout) {
			if (mode === "off") return undefined;
			const readDeclared = loadout.declared.some((t) => t.name === "read");
			if (!readDeclared) return undefined;
			return { hiddenDeclarations: ["read"] };
		},
		async execute(toolCallId, params, signal, onUpdate, ctx) {
			const { path: requestedPath, offset, limit, force } = params;
			const absPath = path.resolve(ctx.cwd, requestedPath);

			// Never call the native read tool if it isn't actually callable (user disabled it): surface a
			// clear error instead of silently reaching for a tool the user turned off, and do this before
			// any filesystem hashing so a disabled read short-circuits as cheaply as possible.
			const readCallable = ctx.tools.some((t) => t.name === "read");
			if (!readCallable) {
				return {
					content: [{ type: "text" as const, text: "read_context: the native read tool is disabled; nothing to delegate to" }],
					details: { dedup: false, path: absPath, offset, limit, bypassReason: "read_disabled" } as ReadContextDetails,
					isError: true,
				};
			}

			const execReadOptions = { signal, onUpdate: onUpdate as any };
			const passthrough = async (bypassReason: string) => {
				const outcome = await ctx.executeTool("read", { path: requestedPath, offset, limit }, execReadOptions);
				return {
					...outcome.result,
					isError: outcome.isError,
					details: { dedup: false, path: absPath, offset, limit, bypassReason } as ReadContextDetails,
				};
			};

			if (isImagePath(absPath)) return passthrough("image");

			const preRead = readFileBounded(fs, absPath, undefined);
			if (!preRead.ok) return passthrough(preRead.reason);

			const preHash = sha256Hex(preRead.buffer);
			const key = makeCacheKey(absPath, offset, limit);

			if (!force) {
				const hit = lookupCache(cacheState, key, preHash);
				if (hit) {
					const marker = buildDedupMarker({
						path: absPath,
						offset,
						limit,
						priorToolCallId: hit.toolCallId,
						contentHash: preHash,
					});
					// Only use the dedup marker when it's actually net-shorter than the result it replaces;
					// otherwise the "optimization" would bloat a small read instead of shrinking it, so fall
					// through to a normal full read instead.
					if (isDedupWorthwhile(hit, marker.length)) {
						recordDedupedRead(cacheState, hit, marker.length);
						const details: ReadContextDetails = {
							dedup: true,
							path: absPath,
							offset,
							limit,
							contentHash: preHash,
							priorToolCallId: hit.toolCallId,
						};
						return { content: [{ type: "text" as const, text: marker }], details };
					}
				}
			}

			const outcome = await ctx.executeTool("read", { path: requestedPath, offset, limit }, execReadOptions);
			if (outcome.isError) {
				return {
					...outcome.result,
					isError: true,
					details: { dedup: false, path: absPath, offset, limit } as ReadContextDetails,
				};
			}

			// Verify the file is still exactly what we hashed before the nested read ran: the nested read
			// could have taken a noticeable amount of wall-clock time (large file, slow disk), during which
			// the file could have changed again. Only cache when the pre- and post-read hashes agree, so a
			// cache entry is never recorded against a hash that doesn't actually match what was returned.
			const postRead = readFileBounded(fs, absPath, undefined);
			const charCount = sumTextLength(outcome.result.content);
			if (postRead.ok) {
				const postHash = sha256Hex(postRead.buffer);
				if (postHash === preHash) {
					const resultDigest = digestContent(outcome.result.content);
					if (resultDigest !== null) {
						recordFullRead(cacheState, key, {
							toolCallId,
							contentHash: postHash,
							charCount,
							resultDigest,
							path: absPath,
							offset,
							limit,
						});
					}
				}
				// else: file changed mid-call -- return the successful read to the caller but never cache it
				// against a hash that no longer describes the file (avoids a false future dedup hit).
			}
			return {
				...outcome.result,
				details: { dedup: false, path: absPath, offset, limit, contentHash: preHash } as ReadContextDetails,
			};
		},
	});

	// -------------------------------------------------------------------------
	// scout_files: only ever registered inactive; activated by /jev-context on.
	// Dynamically imports the sibling scouting module at call time so this
	// extension loads and runs fully before that module exists or while the
	// user stays off/local (brief: "no call scout library at all while
	// off/local; dynamic import okay until sibling file merges").
	// -------------------------------------------------------------------------
	pi.registerTool({
		name: SCOUT_TOOL_NAME,
		label: "Jev file scout",
		description:
			"Sends an explicit goal and an explicit list of allowed tracked repo files (no globs, max 8 paths, " +
			"goal <=1000 chars) to TypeSafe for relevance triage. Returns a compact ranked list plus uncertain/skipped " +
			"files -- never full file contents or model-generated rationale. Only active after /jev-context on.",
		promptSnippet: "scout_files: explicit file-relevance triage via TypeSafe (only active after /jev-context on)",
		parameters: ScoutFilesParams,
		exposure: "direct",
		defaultActive: false,
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			if (mode !== "on") {
				return {
					content: [{ type: "text" as const, text: "scout_files is inactive; run /jev-context on first" }],
					details: undefined,
					isError: true,
				};
			}
			const canonicalCwd = canonicalizeCwd(fs, ctx.cwd);
			if (!consentValidForCwd(cacheState, canonicalCwd)) {
				return {
					content: [
						{
							type: "text" as const,
							text: "scout_files: scouting consent does not match the current project/cwd; run /jev-context on again here",
						},
					],
					details: undefined,
					isError: true,
				};
			}
			if (resolveJevApiMode({ env: process.env }) === "off") {
				return {
					content: [{ type: "text" as const, text: "scout_files: Jev API disabled via PI_JEV_MODE=off" }],
					details: undefined,
					isError: true,
				};
			}
			let scoutFiles: (args: unknown) => Promise<any>;
			try {
				const mod: any = await loadScoutModule();
				scoutFiles = mod.scoutFiles;
				if (typeof scoutFiles !== "function") throw new Error("scoutFiles export missing");
			} catch {
				return {
					content: [{ type: "text" as const, text: "scout_files: scouting module is not available yet" }],
					details: undefined,
					isError: true,
				};
			}
			const signals = [signal, scoutController?.signal].filter((s): s is AbortSignal => Boolean(s));
			const combinedSignal = signals.length > 0 ? AbortSignal.any(signals) : undefined;
			try {
				const result = await scoutFiles({
					cwd: ctx.cwd,
					goal: params.goal,
					paths: params.paths,
					enabled: true,
					signal: combinedSignal,
				});
				mergeScoutStats(cacheState, result?.stats);
				const byRelevance = (r: string) =>
					(result?.items ?? [])
						.filter((i: any) => i.relevance === r)
						.map((i: any) => `${i.path}${scoutConfidenceLabel(i.confidence)}`)
						.join(", ") || "(none)";
				const lines = [
					`relevant: ${byRelevance("relevant")}`,
					`uncertain: ${byRelevance("uncertain")}`,
					`unrelated: ${byRelevance("unrelated")}`,
					`skipped: ${(result?.skipped ?? []).map((s: any) => `${s.path} (${s.reason})`).join(", ") || "(none)"}`,
				];
				return {
					content: [{ type: "text" as const, text: lines.join("\n") }],
					details: { items: result?.items, skipped: result?.skipped },
					// Native Pi Usage aggregate from the sibling, passed through untouched -- never
					// remapped or reconstructed here. See operator notes: jev-context-extension-implementation.md (usage contract).
					usage: result?.usage,
				};
			} catch {
				// Never forward the raw caught error to the model: it could carry a provider error payload,
				// a stack trace, or other internal detail the sibling/this module doesn't control. Only a
				// short, fixed, non-secret message crosses this boundary -- consistent with the shared Jev
				// helper's "no raw provider error text" policy (config/pi/lib/jev.mjs).
				recordScoutError(cacheState);
				throw new Error("scout_files: scouting request failed");
			}
		},
	});

	// -------------------------------------------------------------------------
	// Lifecycle hooks: all registered unconditionally (cheap no-ops while off),
	// never gated behind mode so retention can never reference stale/invisible
	// history after a boundary we didn't anticipate.
	// -------------------------------------------------------------------------
	pi.on("context", (event) => {
		recomputeVisibility(cacheState, event.messages);
	});

	pi.on("session_before_compact", () => {
		clearRetention(cacheState);
	});
	pi.on("session_compact", () => {
		clearRetention(cacheState);
	});
	pi.on("session_before_switch", () => {
		resetConsentOnLifecycleBoundary();
	});
	pi.on("session_before_fork", () => {
		resetConsentOnLifecycleBoundary();
	});
	pi.on("session_shutdown", () => {
		abortScouting();
		clearRetention(cacheState);
	});
	pi.on("session_start", async (event, ctx) => {
		clearRetention(cacheState);
		if (event.reason !== "startup") {
			// resume/new/fork/reload: never silently carry a prior "on" consent into
			// a possibly different session/cwd. local mode is reset the same way;
			// the user/environment must opt back in explicitly in the new session.
			abortScouting();
			clearConsentCwd(cacheState);
			if (mode !== "off") {
				mode = "off";
				setToolActive(SCOUT_TOOL_NAME, false);
				setToolActive(READ_TOOL_NAME, false);
			}
		}
		const envOptIn = resolveEnvOptIn(process.env);
		if (envOptIn === "local") {
			activateLocal(ctx);
		} else if (envOptIn === "on") {
			// Awaited, not fire-and-forget: a dangling promise here could race the first turn's tool
			// declarations (scout_files activating after Pi has already decided what to declare for the
			// first model call), and an unhandled rejection from attemptEnableOn would otherwise be silent.
			await attemptEnableOn(ctx);
		}
	});

	pi.registerCommand("jev-context", {
		description: "Jev file scouting + duplicate-read suppression: status | local | on | off",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const sub = args.trim().split(/\s+/)[0] || "status";
			switch (sub) {
				case "status": {
					const lines = formatStatusLines({ mode, state: cacheState, jevApiNote: jevApiStatusNote() });
					ctx.ui.notify(lines.join("\n"), "info");
					return;
				}
				case "local": {
					activateLocal(ctx);
					ctx.ui.notify("jev-context: local duplicate-read suppression enabled (no external network)", "info");
					return;
				}
				case "on": {
					const enabled = await attemptEnableOn(ctx);
					if (enabled) {
						ctx.ui.notify("jev-context: scouting enabled (read_context + scout_files active)", "info");
					}
					return;
				}
				case "off": {
					deactivate();
					ctx.ui.notify("jev-context: disabled; tools deactivated and retained read-cache cleared", "info");
					return;
				}
				default: {
					ctx.ui.notify("Usage: /jev-context status|local|on|off", "info");
				}
			}
		},
	});
}
