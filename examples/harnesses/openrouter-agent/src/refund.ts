/**
 * OpenRouter Agent SDK refund demo.
 *
 * Default: offline fake (no API key, no @openrouter/agent import).
 * Live: callModel + sessionId + stopWhen [stepCountIs, maxCost]; tools POST to the Python PEP.
 *
 *   npx tsx src/refund.ts
 *   python ../../bridge.py   # in another shell, then:
 *   npx tsx src/refund.ts --live
 */

import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

import { executeAbf, waitForBridge } from "./abfBridge.ts";
import { pythonBin, runFake } from "./fake.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../../..");

async function runLive(): Promise<void> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY required for --live");
  }

  const { default: OpenRouter } = await import("@openrouter/sdk");
  const { callModel, tool, stepCountIs, maxCost } = await import("@openrouter/agent");
  const { z } = await import("zod");

  const sessionId = process.env.ABF_SESSION_ID ?? randomUUID().replace(/-/g, "");
  let bridge: ChildProcess | undefined;
  try {
    await waitForBridge(500);
  } catch {
    bridge = spawn(pythonBin(), [path.join(repoRoot, "examples/harnesses/bridge.py")], {
      cwd: repoRoot,
      stdio: "inherit",
    });
    await waitForBridge();
  }

  const kvGet = tool({
    name: "kv_get",
    description: "Read KV inside the account boundary. ABF authorizes kv.get.",
    inputSchema: z.object({ key: z.string() }),
    execute: async ({ key }: { key: string }) =>
      executeAbf({ action: "kv.get", params: { key }, sessionId }),
  });

  const memoryWrite = tool({
    name: "memory_write",
    description: "Write session memory. Store.put equivalent; goes through memory.write.",
    inputSchema: z.object({ note: z.string() }),
    execute: async ({ note }: { note: string }) =>
      executeAbf({ action: "memory.write", params: { note }, sessionId }),
  });

  const refundIssue = tool({
    name: "refund_issue",
    description: "Issue a refund. Irreversible; ABF requires approval and live state.",
    inputSchema: z.object({ amount: z.number() }),
    execute: async ({ amount }: { amount: number }) =>
      executeAbf({ action: "refund.issue", params: { amount }, sessionId }),
  });

  const client = new OpenRouter({ apiKey });
  const result = callModel(client, {
    model: process.env.ABF_OPENROUTER_MODEL ?? "anthropic/claude-sonnet-4",
    instructions:
      "You are a customer-operations agent. Propose refunds, memory writes, and KV lookups. You do not authorize them.",
    input: "Look up account_status, note the review, refund $250 on acct/8841.",
    tools: [kvGet, memoryWrite, refundIssue] as const,
    sessionId,
    promptCacheKey: `abf:${sessionId}`,
    stopWhen: [stepCountIs(8), maxCost(1.0)],
  });

  const text = await result.getText();
  const usage = await result.getUsage();
  console.log(text);
  console.log("usage", usage);
  if (bridge) bridge.kill();
}

const live = process.argv.includes("--live");
if (live) {
  runLive().catch((err) => {
    console.error(err);
    process.exit(1);
  });
} else {
  process.exit(runFake());
}
