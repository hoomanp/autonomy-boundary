# OpenRouter Agent SDK (TypeScript)

Small demo of `callModel` with `sessionId` and `stopWhen: [stepCountIs(8), maxCost(1.0)]`. Tool `execute` functions POST to the Python PEP (`examples/harnesses/bridge.py`) so TypeScript does not reimplement the eight controls.

```bash
# offline — fake model, no API key, no npm install (Node 22+)
node src/refund.ts

# or: npx tsx src/refund.ts

# live
python ../../bridge.py          # or let --live spawn it
export OPENROUTER_API_KEY=...
npx tsx src/refund.ts --live
```

`stopWhen` is the harness twin of Authority `chain_budget`: fail closed on either. `sessionId` is the issue #3 software instance claim bound into the ledger by the Python bridge.
