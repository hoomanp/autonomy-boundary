# Optional harness demos

A harness may **propose** actions. The Autonomy Boundary still **authorizes** them. These extras wrap LangChain, Anthropic, OpenAI, Gemini, and OpenRouter around the same customer-ops story: look up KV, write session memory, issue a $250 refund. Memory writes, KV lookups, and cache-session reuse are effects. They must pass Scope, Authority, Input Integrity, Legibility, State Admissibility, and land on the ledger with the issue #3 triple: approved intent, in-force grant, instance/session identity.

`demo/` stays zero-dependency. This directory is optional.

```bash
# fake model, no API keys, no extra packages
python examples/harnesses/langchain_refund.py
python examples/harnesses/anthropic_refund.py
python examples/harnesses/openai_refund.py
python examples/harnesses/gemini_refund.py
python examples/harnesses/openrouter_refund.py

# TypeScript Agent SDK, still fake/offline (Node 22+; no npm install)
cd examples/harnesses/openrouter-agent
node src/refund.ts
```

`--live` sends a real provider call. Install extras and set the matching key. Never required for pytest.

```bash
pip install -e ".[harness]"

python examples/harnesses/langchain_refund.py --live     # OPENAI_API_KEY
python examples/harnesses/anthropic_refund.py --live     # ANTHROPIC_API_KEY
python examples/harnesses/openai_refund.py --live        # OPENAI_API_KEY
python examples/harnesses/gemini_refund.py --live        # GEMINI_API_KEY or GOOGLE_API_KEY
python examples/harnesses/openrouter_refund.py --live    # OPENROUTER_API_KEY
```

| Harness | Native surface | ABF mapping |
|---|---|---|
| LangChain | LangGraph `MemorySaver` + Store; cache key in runnable config | Tools and `Store.put` go through `memory.write` / PEP |
| Anthropic | `cache_control` breakpoints on system/tools; TTL | Cache TTL is not Authority `expiry` |
| OpenAI | Responses API `prompt_cache_key` / breakpoint | Cache key bound as ledger instance |
| Gemini | Context cache; function calling | Cached corpus is `data_boundary`; Input Integrity on retrieved context |
| OpenRouter Python | `OpenAI(base_url=...)` + `extra_body.session_id` / `cache_control` | `session_id` is the instance claim; `cached_tokens` / `cache_discount` on the ledger; `maxCost` twin of `chain_budget` |
| OpenRouter Agent SDK (TS) | `callModel`, `sessionId`, `stopWhen: [stepCountIs(8), maxCost(1.0)]` | `tool().execute` POSTs to `bridge.py` |

OpenRouter-specific behavior the Python and TS demos show:

- `session_id` as sticky routing so the cache is warm from turn one
- Prefix discipline (system + tools + policy first) so agent loops do not bust implicit KV cache
- Explicit `cache_control` / `prompt_cache_key`; OpenRouter translates across Anthropic, OpenAI, and Gemini
- Record `cached_tokens` and `cache_discount` (Observability)
- `stopWhen` / `maxCost` fail closed alongside Authority `chain_budget`

Implicit provider KV cache is not application data retention (OpenRouter's ZDR stance). ABF still treats **application** memory and KV as governed state (issue #1).

The TypeScript demo does not reimplement the eight controls. Start the stdlib bridge, or let `--live` spawn it:

```bash
python examples/harnesses/bridge.py
cd examples/harnesses/openrouter-agent && npm install && npx tsx src/refund.ts --live
```

Policy: [`policies/harness.yaml`](../../policies/harness.yaml). Shared adapter: [`common/`](common/).
