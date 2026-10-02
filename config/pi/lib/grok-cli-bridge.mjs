// Pure helper for grok-build.ts's read-only Grok CLI session bridge. Kept
// dependency-free (no @earendil-works/pi-ai import) so it can be unit-tested
// without requiring that package's node_modules to be present.
//
// Native `Provider.auth.apiKey.resolve()` return values are used verbatim as
// the bearer token by @earendil-works/pi-ai's resolveApiKey()
// (auth/resolve.ts) -- it never interprets a leading "!". That string
// convention is only auto-applied to legacy ProviderConfig (models.json)
// values (pi-coding-agent's core/provider-composer.ts), and
// AuthStorage.read() explicitly leaves command-type stored keys unresolved
// for the caller to handle (core/auth-storage.ts). So grok-build executes
// the bridge script itself, directly, with no shell involved (execFileSync
// with an argv array, not a shell string) and a bounded timeout. This also
// means no token is ever stored or cached here: every call re-runs the
// read-only script against the Grok CLI's live session.
import { execFileSync } from "node:child_process";

export function resolveGrokCliBridgeToken(bridgeScript) {
  let stdout;
  try {
    stdout = execFileSync(bridgeScript, [], {
      encoding: "utf8",
      timeout: 10_000,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    const stderr = error?.stderr;
    const detail = stderr ? String(stderr).trim().split("\n").filter(Boolean).pop() : undefined;
    throw new Error(detail || "Grok CLI session unavailable; run `grok login --device-auth`.");
  }
  const token = stdout.trim();
  if (!token) throw new Error("Grok CLI session bridge returned no token.");
  return token;
}
