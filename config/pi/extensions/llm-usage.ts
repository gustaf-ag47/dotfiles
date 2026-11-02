import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { TABS, fetchSnapshot, originFrom, poolEnabled, renderPanel, safe, statusLine } from "../lib/llm-inspector.mjs";

/** UI-only observer. Never sends account data to the model or changes routing. */
export default function (pi: ExtensionAPI) {
  const root = resolve(dirname(realpathSync(fileURLToPath(import.meta.url))), "../../..");
  let ctxRef: ExtensionContext | undefined;
  let timer: ReturnType<typeof setInterval> | undefined;
  let controller: AbortController | undefined;
  let generation = 0;
  let inFlight: Promise<void> | undefined;
  let fleetBusy = false;
  let requestRender: (() => void) | undefined;
  let unsubscribe: (() => void) | undefined;
  let unsubscribeTransitions: (() => void) | undefined;
  let view: any = { extensions: {}, events: [] };

  function session(ctx: ExtensionContext) {
    const id = ctx.sessionManager.getSessionId();
    return { id: id ? `pi-${id}` : "", provider: ctx.model?.provider, model: ctx.model?.id,
      pool: poolEnabled(), taskClass: process.env.PI_LLM_CLASS || "interactive",
      classSource: process.env.PI_LLM_CLASS ? "PI_LLM_CLASS" : "default" };
  }
  function draw() {
    if (ctxRef?.mode !== "tui") return;
    view.session = session(ctxRef);
    ctxRef.ui.setStatus("llm", safe(statusLine(view), 180));
    requestRender?.();
  }
  function event(kind: string, state: string) {
    const last = view.events.at(-1);
    if (last?.kind === kind && last?.state === state) return;
    view.events.push({ ts: Date.now() / 1000, kind, state: safe(state) });
    view.events = view.events.slice(-40);
  }
  function refresh(ctx: ExtensionContext): Promise<void> {
    ctxRef = ctx;
    pi.events.emit("llm:status-request", {});
    if (inFlight) return inFlight;
    const epoch = generation;
    controller = new AbortController();
    const signal = controller.signal;
    inFlight = (async () => {
      try {
        const snapshot = await fetchSnapshot(originFrom(), session(ctx), fetch, signal);
        if (epoch !== generation) return;
        if (view.error) event("proxy", "recovered");
        const previous = new Map((view.snapshot?.accounts || []).map((a: any) => [a.id, a.auth]));
        for (const account of snapshot.accounts) {
          if (account.auth === "rejected" && previous.has(account.id) && previous.get(account.id) !== "rejected") {
            event("auth", `${safe(account.label)} needs sign-in`);
            if (ctx.mode === "tui") ctx.ui.notify(`${safe(account.label)} needs sign-in. /llm accounts`, "warning");
          }
        }
        view.snapshot = snapshot;
        view.fetchedAt = Date.now() / 1000;
        view.error = undefined;
      } catch (error) {
        if (epoch !== generation || signal.aborted) return;
        const message = error instanceof Error ? error.message : "Proxy unavailable";
        if (!view.error) {
          event("proxy", "unreachable or unsupported");
          if (view.snapshot && ctx.mode === "tui" && ctx.model?.provider === "anthropic" && poolEnabled())
            ctx.ui.notify("Local proxy became unreachable. Last observations are marked stale. /llm", "warning");
        }
        view.error = safe(message);
      } finally {
        if (epoch === generation) { inFlight = undefined; draw(); }
      }
    })();
    return inFlight;
  }
  async function refreshFleet(ctx: ExtensionContext) {
    if (fleetBusy) return;
    fleetBusy = true;
    const epoch = generation;
    try {
      const result = await pi.exec(resolve(root, "bin/llm-usage"), ["--fleet", "--json"], { timeout: 15000 });
      if (epoch !== generation) return;
      if (result.code !== 0) throw new Error("Fleet unavailable. Configure ~/.config/llm-proxy/fleet.json; use llm-usage --fleet to diagnose.");
      const rows = JSON.parse(result.stdout);
      for (const [name, row] of Object.entries(rows) as [string, any][]) {
        if (row.error && !row.snapshot && view.fleet?.[name]?.snapshot) rows[name] = { ...view.fleet[name], error: row.error };
      }
      view.fleet = rows;
      view.fleetError = undefined;
    } catch (error) {
      if (epoch === generation) view.fleetError = safe(error instanceof Error ? error.message : "Fleet read failed");
    } finally {
      if (epoch === generation) { fleetBusy = false; draw(); }
    }
  }
  function shutdown() {
    generation++;
    if (timer) clearInterval(timer);
    timer = undefined;
    controller?.abort();
    inFlight = undefined;
    fleetBusy = false;
    unsubscribe?.(); unsubscribe = undefined;
    unsubscribeTransitions?.(); unsubscribeTransitions = undefined;
    requestRender = undefined;
    if (ctxRef?.mode === "tui") ctxRef.ui.setStatus("llm", undefined);
    ctxRef = undefined;
  }
  pi.on("session_start", (_event, ctx) => {
    shutdown();
    view = { extensions: { "llm-usage": { at: Date.now()/1000, state: { role: "read-only UI", pollSeconds: 15, fleet: "explicit opt-in" } } }, events: [] };
    ctxRef = ctx;
    unsubscribe = pi.events.on("llm:status", (data: any) => {
      if (!data || typeof data.id !== "string" || !data.state || typeof data.state !== "object") return;
      // Only known owners may contribute; never render arbitrary event objects.
      if (!["anthropic-pool", "llm-failover", "jev", "jev-context", "compaction-model"].includes(data.id)) return;
      view.extensions[data.id] = { state: data.state, at: data.at };
      draw();
    });
    unsubscribeTransitions = pi.events.on("llm:transition", (data: any) => {
      if (data?.source === "llm-failover") { event("failover", safe(data.line)); draw(); }
    });
    if (ctx.mode !== "tui") return;
    void refresh(ctx);
    timer = setInterval(() => { if (ctxRef) void refresh(ctxRef); }, 15000);
  });
  pi.on("session_shutdown", shutdown);
  pi.on("model_select", (_event, ctx) => {
    ctxRef = ctx;
    if (ctx.mode === "tui") {
      generation++; controller?.abort(); inFlight = undefined; fleetBusy = false;
      view.snapshot = undefined; view.fetchedAt = undefined;
      void refresh(ctx);
    }
  });
  pi.on("turn_end", (_event, ctx) => { if (ctx.mode === "tui") void refresh(ctx); });

  async function open(args: string, ctx: any) {
    const arg = (args || "overview").trim().toLowerCase();
    const aliases: Record<string, string> = { why: "routing", "--accounts": "accounts" };
    const key = aliases[arg] || arg;
    if (arg === "--debug" || arg === "--all" || arg === "--json") {
      const result = await pi.exec(resolve(root, "bin/llm-usage"), [arg], { timeout: 30000 });
      if (ctx.hasUI) ctx.ui.notify(result.code === 0 ? result.stdout.trim() : "llm-usage failed", result.code === 0 ? "info" : "error");
      else if (ctx.mode === "print") console.log(result.stdout.trim());
      return;
    }
    let index = TABS.findIndex((t: string) => t.toLowerCase() === key);
    if (index < 0) { ctx.ui.notify("Usage: /llm overview|accounts|why|config|events|extensions|fleet", "info"); return; }
    await refresh(ctx);
    if (ctx.mode !== "tui") {
      const text = renderPanel({ ...view, session: session(ctx) }, TABS[index]).join("\n");
      if (ctx.hasUI) ctx.ui.notify(text, "info");
      else if (ctx.mode === "print") console.log(text);
      return;
    }
    const { truncateToWidth, visibleWidth, wrapTextWithAnsi, matchesKey, Key } = await import("@earendil-works/pi-tui");
    let offset = 0;
    let accountIndex = Math.max(0, (view.snapshot?.accounts || []).findIndex((a: any) => a.id === view.snapshot?.routing?.account_preview?.would_pick));
    let expandedAccount: string | undefined;
    await ctx.ui.custom((tui: any, theme: any, keybindings: any, done: any) => {
      requestRender = () => tui.requestRender();
      return {
        render(width: number) {
          const height = Math.max(5, Math.floor((process.stdout.rows || 24) * .75));
          const body = renderPanel({ ...view, session: session(ctxRef || ctx), accountSelection: accountIndex, expandedAccount }, TABS[index])
            .flatMap((line: string) => wrapTextWithAnsi(safe(line, 600), Math.max(1, width - 2)));
          const page = Math.max(1, height - 4);
          offset = Math.max(0, Math.min(offset, Math.max(0, body.length - page)));
          const header = `LLM · ${view.snapshot?.host || "local"} · ${TABS[index]} · READ ONLY${view.error ? " · STALE" : ""}`;
          const tabs = TABS.map((name: string, i: number) => i === index ? `[${i+1} ${name}]` : `${i+1} ${name}`).join("  ");
          return [theme.fg("accent", truncateToWidth(safe(header), width)),
            theme.fg("muted", truncateToWidth(tabs, width)),
            ...body.slice(offset, offset + page).map((line: string) => truncateToWidth(line, width)),
            theme.fg("dim", truncateToWidth(`q/Esc close · ←→ tabs · ↑↓ ${TABS[index] === 'Accounts' ? 'select · Enter details · j/k scroll' : 'scroll'} · r refresh · f fleet (${offset+1}/${body.length})`, width))]
            .map(line => theme.bg("userMessageBg", line + " ".repeat(Math.max(0, width - visibleWidth(line)))));
        },
        handleInput(data: string) {
          if (keybindings.matches(data, "tui.select.cancel") || data === "q") { done(undefined); return; }
          if (matchesKey(data, Key.left)) { index = (index + TABS.length - 1) % TABS.length; offset = 0; }
          else if (matchesKey(data, Key.right) || data === "\t") { index = (index + 1) % TABS.length; offset = 0; }
          else if (TABS[index] === "Accounts" && keybindings.matches(data, "tui.select.confirm")) {
            const id = view.snapshot?.accounts?.[accountIndex]?.id;
            expandedAccount = expandedAccount === id ? undefined : id;
          }
          else if (TABS[index] === "Accounts" && (keybindings.matches(data, "tui.select.up") || keybindings.matches(data, "tui.select.down"))) {
            const n = view.snapshot?.accounts?.length || 1;
            accountIndex = (accountIndex + (keybindings.matches(data, "tui.select.up") ? n-1 : 1)) % n;
            expandedAccount = undefined; offset = 0;
          }
          else if (keybindings.matches(data, "tui.select.up") || data === "k") offset--;
          else if (keybindings.matches(data, "tui.select.down") || data === "j") offset++;
          else if (/^[1-7]$/.test(data)) { index = Number(data)-1; offset = 0; }
          else if (data === "r") { void refresh(ctx); if (TABS[index] === "Fleet" && view.fleet) void refreshFleet(ctx); }
          else if (data === "f") { index = 6; offset = 0; void refreshFleet(ctx); }
          tui.requestRender();
        },
        invalidate() {},
        dispose() { requestRender = undefined; },
      };
    }, { overlay: true, overlayOptions: { width: "95%", maxHeight: "85%" } });
    requestRender = undefined;
  }
  pi.registerCommand("llm", { description: "LLM inspector: overview | accounts | why | config | events | extensions | fleet", handler: open });
  pi.registerCommand("usage", { description: "LLM capacity inspector (UI-only); --debug preserves the full report", handler: (args, ctx) => open(args || "accounts", ctx) });
}
