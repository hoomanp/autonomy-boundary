"""OpenAI Responses API refund demo.

prompt_cache_key (and optional prompt_cache_breakpoint) is bound into the
ledger instance claim so a reused conversation cannot shed its session.

  python examples/harnesses/openai_refund.py
  python examples/harnesses/openai_refund.py --live
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


def openai_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "name": "kv_get",
            "description": "Read KV via kv.get.",
            "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
        },
        {
            "type": "function",
            "name": "memory_write",
            "description": "Write session memory via memory.write.",
            "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
        },
        {
            "type": "function",
            "name": "refund_issue",
            "description": "Issue a refund.",
            "parameters": {"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]},
        },
    ]


def native_surface(session: CacheSession) -> dict:
    return {
        "harness": "openai",
        "request": {
            "model": "gpt-4.1-mini",
            "prompt_cache_key": session.prompt_cache_key,
            "prompt_cache_retention": "24h",
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT, "prompt_cache_breakpoint": True},
                {"role": "system", "content": POLICY_PREFIX},
                {"role": "user", "content": "Look up status, note the review, refund $250 on acct/8841."},
            ],
            "tools": openai_tools(),
        },
        "instance_id": session.instance_id,
        "prefix": stable_prefix(tools=tool_schemas()),
    }


def run_live(session: CacheSession) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY required for --live")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(f"pip install -e '.[harness]' ({exc})") from exc

    from harnesses.common.boundary import HarnessRuntime

    rt = HarnessRuntime.start(session=session)
    client = OpenAI()
    surface = native_surface(session)
    name_map = {"kv_get": "kv.get", "memory_write": "memory.write", "refund_issue": "refund.issue"}
    items = list(surface["request"]["input"])
    for _ in range(rt.chain_budget):
        resp = client.responses.create(
            model=surface["request"]["model"],
            prompt_cache_key=session.prompt_cache_key,
            input=items,
            tools=surface["request"]["tools"],
        )
        cached = 0
        usage = getattr(resp, "usage", None)
        if usage is not None:
            details = getattr(usage, "input_tokens_details", None)
            cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        rt.record_cache(cached_tokens=cached)
        calls = [item for item in resp.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            print(getattr(resp, "output_text", resp))
            break
        items.extend(resp.output)
        for call in calls:
            args = json.loads(call.arguments or "{}")
            out = rt.tools.dispatch(name_map[call.name], args)
            items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": str(out),
            })
    print("ledger chain verified:", rt.ledger.verify_chain())


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI refund harness")
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
