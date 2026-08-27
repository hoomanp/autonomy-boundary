/** Offline path: no OpenRouter network. Reuses the Python fake-model scenario. */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../../..");

export function pythonBin(): string {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venv = path.join(repoRoot, ".venv", "bin", "python");
  if (existsSync(venv)) return venv;
  return "python3";
}

export const nativeCallModelShape = {
  harness: "openrouter-agent",
  callModel: {
    model: "anthropic/claude-sonnet-4",
    sessionId: "<CacheSession.session_id>",
    promptCacheKey: "abf:<session_id>",
    stopWhen: ["stepCountIs(8)", "maxCost(1.0)"],
    tools: ["kv_get", "memory_write", "refund_issue"],
    note: "stopWhen is the harness twin of Authority chain_budget; fail closed on either",
  },
  pep: "tool().execute POSTs to examples/harnesses/bridge.py — TypeScript does not reimplement the eight controls",
};

export function runFake(): number {
  console.log(JSON.stringify(nativeCallModelShape, null, 2));
  const demo = path.join(repoRoot, "examples/harnesses/openrouter_refund.py");
  const result = spawnSync(pythonBin(), [demo], { cwd: repoRoot, stdio: "inherit" });
  if (result.error) {
    console.error(result.error);
    return 1;
  }
  return result.status ?? 1;
}
