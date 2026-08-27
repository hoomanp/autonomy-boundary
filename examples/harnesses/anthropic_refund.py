"""Anthropic Messages API refund demo.

Explicit cache_control breakpoints on system and tools. Cache TTL is a
provider cost knob; Authority expiry is the grant lifetime. They are not
the same clock — a warm cache after expiry is still unauthorized.

  python examples/harnesses/anthropic_refund.py
  python examples/harnesses/anthropic_refund.py --live
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
from harnesses.common.tools import WINDOW


def anthropic_tools() -> list[dict]:
    return [
        {
            "name": "kv_get",
            "description": "Read KV inside the account boundary. ABF authorizes kv.get.",
            "input_schema": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
        {
            "name": "memory_write",
            "description": "Write session memory via memory.write.",
            "input_schema": {
                "type": "object",
                "properties": {"note": {"type": "string"}},
                "required": ["note"],
            },
        },
        {
            "name": "refund_issue",
            "description": "Issue a refund. Irreversible.",
            "input_schema": {
                "type": "object",
                "properties": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        },
    ]


def native_surface(session: CacheSession) -> dict:
    tools = anthropic_tools()
    tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral", "ttl": session.cache_ttl}}
    return {
        "harness": "anthropic",
        "session_id": session.session_id,
        "authority_expiry": WINDOW,
        "cache_ttl_is_not_grant_expiry": True,
        "request": {
            "model": "claude-sonnet-4-20250514",
            "system": [
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral", "ttl": session.cache_ttl}},
                {"type": "text", "text": POLICY_PREFIX, "cache_control": {"type": "ephemeral", "ttl": session.cache_ttl}},
            ],
            "tools": tools,
            "messages": [{"role": "user", "content": "Look up status, note the review, refund $250."}],
        },
        "prefix": stable_prefix(tools=tool_schemas()),
    }


def run_live(session: CacheSession) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY required for --live")
    try:
        import anthropic
    except ImportError as exc:
        raise SystemExit(f"pip install -e '.[harness]' ({exc})") from exc

    from harnesses.common.boundary import HarnessRuntime

    rt = HarnessRuntime.start(session=session)
    surface = native_surface(session)
    client = anthropic.Anthropic()
    name_map = {"kv_get": "kv.get", "memory_write": "memory.write", "refund_issue": "refund.issue"}
    messages = list(surface["request"]["messages"])
    for _ in range(rt.chain_budget):
        resp = client.messages.create(
            model=surface["request"]["model"],
            max_tokens=1024,
            system=surface["request"]["system"],
            tools=surface["request"]["tools"],
            messages=messages,
        )
        usage = getattr(resp, "usage", None)
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0 if usage else 0
        rt.record_cache(cached_tokens=int(cached))
        blocks = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not blocks:
            print(resp.content)
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in blocks:
            action = name_map[block.name]
            out = rt.tools.dispatch(action, dict(block.input))
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(out)})
        messages.append({"role": "user", "content": results})
    print("ledger chain verified:", rt.ledger.verify_chain())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anthropic refund harness")
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
