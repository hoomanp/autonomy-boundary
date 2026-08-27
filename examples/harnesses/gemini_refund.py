"""Gemini function-calling refund demo.

A cached corpus is a data_boundary. Retrieved context still passes Input
Integrity. Context-cache breakpoints are provider features; ABF governs
the effect those bytes are about to cause.

  python examples/harnesses/gemini_refund.py
  python examples/harnesses/gemini_refund.py --live
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


def gemini_tools() -> dict:
    return {
        "function_declarations": [
            {
                "name": "kv_get",
                "description": "Read KV via kv.get.",
                "parameters": {"type": "OBJECT", "properties": {"key": {"type": "STRING"}}, "required": ["key"]},
            },
            {
                "name": "memory_write",
                "description": "Write session memory via memory.write.",
                "parameters": {"type": "OBJECT", "properties": {"note": {"type": "STRING"}}, "required": ["note"]},
            },
            {
                "name": "refund_issue",
                "description": "Issue a refund.",
                "parameters": {"type": "OBJECT", "properties": {"amount": {"type": "NUMBER"}}, "required": ["amount"]},
            },
        ]
    }


def native_surface(session: CacheSession) -> dict:
    return {
        "harness": "gemini",
        "cached_content": {
            "display_name": f"abf-policy-{session.session_id}",
            "system_instruction": SYSTEM_PROMPT,
            "contents": [{"role": "user", "parts": [{"text": POLICY_PREFIX}]}],
            "ttl": "300s",
        },
        "data_boundary": f"cache:{session.prompt_cache_key}",
        "generate_content": {
            "model": "gemini-2.5-flash",
            "config": {
                "cached_content": "CACHE_NAME",
                "tools": [gemini_tools()],
            },
            "contents": "Look up status, note the review, refund $250 on acct/8841.",
        },
        "prefix": stable_prefix(tools=tool_schemas()),
        "instance_id": session.instance_id,
    }


def run_live(session: CacheSession) -> None:
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY required for --live")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise SystemExit(f"pip install -e '.[harness]' ({exc})") from exc

    from harnesses.common.boundary import HarnessRuntime

    rt = HarnessRuntime.start(session=session)
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    cache = client.caches.create(
        model="gemini-2.5-flash",
        config=types.CreateCachedContentConfig(
            display_name=f"abf-policy-{session.session_id}",
            system_instruction=SYSTEM_PROMPT,
            contents=[POLICY_PREFIX],
            ttl="300s",
        ),
    )
    name_map = {"kv_get": "kv.get", "memory_write": "memory.write", "refund_issue": "refund.issue"}
    contents: list = ["Look up status, note the review, refund $250 on acct/8841."]
    for _ in range(rt.chain_budget):
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                cached_content=cache.name,
                tools=[types.Tool(function_declarations=gemini_tools()["function_declarations"])],
            ),
        )
        cached = 0
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            cached = int(getattr(usage, "cached_content_token_count", 0) or 0)
        rt.record_cache(cached_tokens=cached)
        calls = []
        for cand in resp.candidates or []:
            for part in cand.content.parts or []:
                if part.function_call:
                    calls.append(part.function_call)
        if not calls:
            print(resp.text)
            break
        contents.append(resp.candidates[0].content)
        fn_responses = []
        for call in calls:
            out = rt.tools.dispatch(name_map[call.name], dict(call.args or {}))
            fn_responses.append(types.Part.from_function_response(name=call.name, response={"result": str(out)}))
        contents.append(types.Content(role="user", parts=fn_responses))
    print("ledger chain verified:", rt.ledger.verify_chain())


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini refund harness")
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
