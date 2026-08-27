"""Shared refund + memory + cache story used by every harness demo."""
from __future__ import annotations

from typing import Any

from harnesses.common.boundary import HarnessRuntime
from harnesses.common.cache_session import CacheSession, stable_prefix
from harnesses.common.fake_model import ToolCall, scripted_turns
from harnesses.common.tools import CAPABILITIES


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "capabilities": list(caps),
            "description": f"Propose {name}. ABF authorizes it.",
        }
        for name, caps in CAPABILITIES.items()
    ]


def run_offline(
    session: CacheSession | None = None,
    *,
    turns: list[ToolCall] | None = None,
    runtime: HarnessRuntime | None = None,
) -> HarnessRuntime:
    rt = runtime or HarnessRuntime.start(session=session)
    prefix = stable_prefix(tools=tool_schemas())
    print(f"cache session {rt.session.session_id}")
    print(f"instance claim {rt.session.instance_id}")
    print(f"stable prefix turns: {len(prefix)} (system/tools/policy first)")
    for call in turns or scripted_turns():
        result = rt.tools.dispatch(call.name, call.args)
        print(f"  {call.name} {call.args} -> {result}")
    rt.record_cache(cached_tokens=0, cache_discount=0.0)
    print("ledger chain verified:", rt.ledger.verify_chain())
    return rt
