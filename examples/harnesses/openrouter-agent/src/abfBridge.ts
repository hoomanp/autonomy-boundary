/** POST tool executions to the Python PEP. The eight controls stay one implementation. */

export type AbfRequest = {
  action: string;
  params: Record<string, unknown>;
  sessionId: string;
  resource?: string;
};

export type AbfResponse = {
  ok: boolean;
  result?: unknown;
  denied?: string;
  instance_id?: string;
};

const DEFAULT_URL = process.env.ABF_BRIDGE_URL ?? "http://127.0.0.1:8765";

export async function executeAbf(req: AbfRequest): Promise<string> {
  const res = await fetch(`${DEFAULT_URL}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: req.action,
      params: req.params,
      session_id: req.sessionId,
      resource: req.resource,
    }),
  });
  const body = (await res.json()) as AbfResponse;
  if (!body.ok) {
    throw new Error(body.denied ?? "boundary denied");
  }
  return String(body.result);
}

export async function waitForBridge(timeoutMs = 8000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${DEFAULT_URL}/health`);
      if (res.ok) return;
    } catch {
      await new Promise((r) => setTimeout(r, 150));
    }
  }
  throw new Error(
    `ABF bridge not reachable at ${DEFAULT_URL}. Start it with: python examples/harnesses/bridge.py`,
  );
}
