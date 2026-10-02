#!/usr/bin/env node
/**
 * Bounded, credential-free live test of TypeSafe's Jev classifier, using Pi's
 * own installed classify() implementation (not a reimplementation).
 *
 * Reads the API key ONLY from process.env.TYPESAFE_API_KEY; never reads a
 * file path itself, never logs the key, never logs request headers. Caller
 * must supply the key via environment, e.g.:
 *
 *   Set the TYPESAFE_API_KEY environment variable from your private key file
 *   (e.g. via shell command substitution reading the file) before running:
 *   node docs/research/jev-test.mjs
 *
 * Hard-capped at 5 billed classifier (POST /v1/systemone) calls. One extra,
 * unbilled GET /v1/models call runs first to confirm the key works before
 * any spend. All prompts here are synthetic placeholders, not real
 * code/conversations/task history. Output is sanitized: no Authorization
 * header, no key material, full response bodies only for non-auth fields.
 */
// Imported directly from the installed Pi package so this exercises the exact
// implementation Pi itself runs (see docs/research/jev-pi-routing.md §2) rather
// than a reimplementation. Override with JEV_CLASSIFY_MODULE for other installs.
const CLASSIFY_MODULE =
	process.env.JEV_CLASSIFY_MODULE ||
	"/home/gustaf/.local/share/npm/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/api/typesafe-system-one.js";
const { classify } = await import(CLASSIFY_MODULE);

const API_KEY = process.env.TYPESAFE_API_KEY;
if (!API_KEY) {
	console.error("TYPESAFE_API_KEY not set in environment; aborting without any request.");
	process.exit(1);
}

// Exact catalog entry Pi ships for this model (TYPESAFE_CLASSIFIER_MODELS["jev-latest"]
// from @earendil-works/pi-ai/providers/typesafe.models.js), reproduced here as a literal
// so this script has no dependency on that subpath export working in every environment.
const JEV_MODEL = {
	type: "classifier",
	id: "jev-latest",
	name: "Jev",
	api: "typesafe-system-one",
	provider: "typesafe",
	baseUrl: "https://api.typesafe.ai/v1/",
	input: ["text"],
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	contextWindow: 64000,
};

const MAX_BILLED_CALLS = 5;
let billedCalls = 0;

async function listModels() {
	const res = await fetch(new URL("models", JEV_MODEL.baseUrl), {
		headers: { authorization: `Bearer ${API_KEY}` },
	});
	const body = await res.json().catch(() => null);
	return { status: res.status, body };
}

async function runClassify(label, state, questions) {
	if (billedCalls >= MAX_BILLED_CALLS) throw new Error("MAX_BILLED_CALLS exceeded — refusing to send");
	billedCalls += 1;
	const start = Date.now();
	const result = await classify(JEV_MODEL, { state, questions }, { apiKey: API_KEY, maxRetries: 0 });
	const latencyMs = Date.now() - start;
	return { label, latencyMs, result };
}

function sanitize(result) {
	// Strip nothing from answers/usage (synthetic, non-sensitive); just ensure
	// no accidental header/key leakage from errorMessage.
	const safe = { ...result };
	if (typeof safe.errorMessage === "string") {
		safe.errorMessage = safe.errorMessage.replace(/Bearer\s+\S+/gi, "Bearer <redacted>");
	}
	return safe;
}

async function main() {
	console.log("=== Step 0: GET /v1/models (unbilled, verifies auth) ===");
	try {
		const probe = await listModels();
		console.log(JSON.stringify(probe, null, 2));
		if (probe.status === 401) {
			console.error("401 from /v1/models — key invalid; aborting before any billed call.");
			process.exit(1);
		}
	} catch (err) {
		console.error("GET /v1/models failed:", err instanceof Error ? err.message : err);
		process.exit(1);
	}

	const cases = [
		{
			label: "noul_clear_approval",
			state: "The change works, thanks.",
			questions: {
				approved: {
					type: "bool",
					instructions: "Does the user approve of the result?",
					criteria: { true: "Approval", false: "No approval" },
				},
			},
		},
		{
			label: "noul_ambiguous",
			state: "It's fine I guess, not sure yet.",
			questions: {
				approved: {
					type: "bool",
					instructions: "Does the user approve of the result?",
					criteria: { true: "Approval", false: "No approval" },
				},
			},
		},
		{
			label: "choice_task_class_clear",
			state: "Rename this variable from `x` to `count` across the file.",
			questions: {
				task_class: {
					type: "choice",
					instructions: "Classify the software engineering work requested in `state`.",
					criteria: {
						mechanical: "Pure syntax/rename/format, no judgment",
						research: "Investigation or reading, no code change",
						build: "Ordinary feature or fix work",
						interactive: "Needs back-and-forth with a human",
					},
				},
			},
		},
		{
			label: "choice_task_class_ambiguous",
			state: "Look into why it's slow sometimes and maybe fix it if it's easy.",
			questions: {
				task_class: {
					type: "choice",
					instructions: "Classify the software engineering work requested in `state`.",
					criteria: {
						mechanical: "Pure syntax/rename/format, no judgment",
						research: "Investigation or reading, no code change",
						build: "Ordinary feature or fix work",
						interactive: "Needs back-and-forth with a human",
					},
				},
			},
		},
		{
			label: "score_complexity",
			state: "Add a retry with exponential backoff around one HTTP call.",
			questions: {
				complexity: {
					type: "score",
					instructions: "How demanding is the software engineering work requested in `state`?",
					criteria: ["Trivial", "Standard", "Complex"],
				},
			},
		},
	];

	const results = [];
	for (const c of cases) {
		console.log(`\n=== ${c.label} ===`);
		const out = await runClassify(c.label, c.state, c.questions);
		const safe = sanitize(out.result);
		console.log(JSON.stringify({ label: c.label, latencyMs: out.latencyMs, ...safe }, null, 2));
		results.push({ label: c.label, latencyMs: out.latencyMs, ...safe });
	}

	console.log(`\n=== Summary: ${billedCalls} billed classify() call(s) ===`);
	console.log(JSON.stringify(results.map((r) => ({
		label: r.label,
		stopReason: r.stopReason,
		usage: r.usage,
		latencyMs: r.latencyMs,
	})), null, 2));
}

main().catch((err) => {
	console.error("Fatal:", err instanceof Error ? err.message : err);
	process.exit(1);
});
