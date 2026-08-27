"""OpenRouter Python client refund demo.

OpenAI-compatible client with extra_body session_id and cache_control.
session_id is sticky routing (cache warm from turn one) and the ledger
instance claim. maxCost-class spend maps to Authority chain_budget — fail
closed on either. cached_tokens / cache_discount land on the ledger.

Implicit provider KV cache is not application data retention (OpenRouter
ZDR). This demo still treats memory.write / kv.* as governed state.

  python examples/harnesses/openrouter_refund.py
  python examples/harnesses/openrouter_refund.py --live
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "src"), str(_ROOT / "examples")]

from harnesses.common.cache_session import POLICY_PREFIX, SYSTEM_PROMPT, CacheSession, stable_prefix
from harnesses.common.scenario import run_offline, tool_schemas


def openrouter_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "kv_get",
                "description": "Read KV via kv.get.",
                "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_write",
                "description": "Write session memory via memory.write.",
                "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "refund_issue",
                "description": "Issue a refund.",
                "parameters": {"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]},
            },
        },
    ]


def native_surface(session: CacheSession) -> dict:
    return {
        "harness": "openrouter-python",
        "base_url": "https://openrouter.ai/api/v1",
        "request": {
            "model": "anthropic/claude-sonnet-4",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
                {"role": "system", "content": POLICY_PREFIX, "cache_control": {"type": "ephemeral"}},
                {"role": "user", "content": "Look up status, note the review, refund $250 on acct/8841."},
            ],
            "tools": openrouter_tools(),
            "extra_body": {
                "session_id": session.session_id,
                "cache_control": {"type": "ephemeral"},
            },
        },
        "stop_twin": {"chain_budget": 8, "maxCost": 1.0},
        "zdr_note": "implicit KV cache is not app retention; memory/KV writes still pass State Admissibility",
        "prefix": stable_prefix(tools=tool_schemas()),
        "instance_id": session.instance_id,
    }


def run_live(session: CacheSession) -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY required for --live")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(f"pip install -e '.[harness]' ({exc})") from exc

    from harnesses.common.boundary import HarnessRuntime

    rt = HarnessRuntime.start(session=session)
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    surface = native_surface(session)
    name_map = {"kv_get": "kv.get", "memory_write": "memory.write", "refund_issue": "refund.issue"}
    messages = list(surface["request"]["messages"])
    spent = 0.0
    max_cost = float(os.environ.get("ABF_MAX_COST", "1.0"))
    for _ in range(rt.chain_budget):
        if spent >= max_cost:
            raise PermissionError("boundary denied by authority: maxCost exhausted (harness twin of chain_budget)")
        resp = client.chat.completions.create(
            model=surface["request"]["model"],
            messages=messages,
            tools=surface["request"]["tools"],
            extra_body=surface["request"]["extra_body"],
        )
        usage = resp.usage
        cached = 0
        discount = 0.0
        if usage is not None:
            cached = int(getattr(usage, "prompt_tokens_details", None) and getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0)
            extra = getattr(usage, "model_extra", None) or {}
            if not cached:
                cached = int((extra.get("cached_tokens") if isinstance(extra, dict) else 0) or 0)
            raw = getattr(resp, "model_extra", None) or {}
            usage_extra = raw.get("usage") if isinstance(raw, dict) else None
            if isinstance(usage_extra, dict):
                cached = int(usage_extra.get("cached_tokens") or cached)
                discount = float(usage_extra.get("cache_discount") or 0)
            spent += float(getattr(usage, "total_tokens", 0) or 0) * 1e-6
        rt.record_cache(cached_tokens=cached, cache_discount=discount)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            print(msg.content)
            break
        messages.append(msg)
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            out = rt.tools.dispatch(name_map[call.function.name], args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": str(out)})
    print("ledger chain verified:", rt.ledger.verify_chain())


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenRouter Python refund harness")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    session = CacheSession.new()
    print(json.dumps(native_surface(session), indent=2))
    if args.live:
        run_live(session)
    else:
        run_offline(session)


if __name__ == "__main__":
    main()
