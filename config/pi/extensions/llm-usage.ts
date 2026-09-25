import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";

export default function (pi: ExtensionAPI) {
  pi.registerCommand("usage", {
    description: "Account usage: Claude pool, ChatGPT subscription, DeepSeek balance",
    handler: async (_args, ctx) => {
      const root = resolve(dirname(realpathSync(__filename)), "../../..");
      const result = await pi.exec(resolve(root, "bin/llm-usage"), [], { timeout: 30000 });
      // UI-only: don't send private account usage to the next selected LLM.
      if (ctx.hasUI) ctx.ui.notify(result.code === 0 ? result.stdout.trim() : "llm-usage failed", result.code === 0 ? "info" : "error");
      else if (ctx.mode === "print") console.log(result.stdout.trim());
    },
  });
}
