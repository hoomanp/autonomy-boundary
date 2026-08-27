"""LangChain / LangGraph refund demo.

Checkpointer + Store are session memory. Store writes go through memory.write.
Prefix-stable messages keep the prompt-cache key warm. ABF still authorizes
every tool.

Default: fake model, no extras required.
Live: pip install -e '.[harness]' and OPENAI_API_KEY.

  python examples/harnesses/langchain_refund.py
  python examples/harnesses/langchain_refund.py --live
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "src"), str(_ROOT / "examples")]

from harnesses.common.cache_session import CacheSession, stable_prefix
from harnesses.common.scenario import run_offline, tool_schemas


def native_surface(session: CacheSession) -> dict:
    return {
        "harness": "langchain",
        "checkpointer": "langgraph.checkpoint.memory.MemorySaver",
        "store": "langgraph.store.memory.InMemoryStore",
        "runnable_config": {
            "configurable": {
                "thread_id": session.session_id,
                "prompt_cache_key": session.prompt_cache_key,
            }
        },
        "messages": stable_prefix(tools=tool_schemas()),
        "binding": "Store.put and tool functions call ToolRuntime.execute; they do not write memory themselves",
    }


def run_live(session: CacheSession) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY required for --live")
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise SystemExit(f"pip install -e '.[harness]' ({exc})") from exc

    from harnesses.common.boundary import HarnessRuntime

    rt = HarnessRuntime.start(session=session)

    @tool
    def kv_get(key: str) -> str:
        """Read a KV value inside the account data boundary."""
        return str(rt.tools.dispatch("kv.get", {"key": key}))

    @tool
    def memory_write(note: str) -> str:
        """Persist a session note. Goes through memory.write."""
        return str(rt.tools.dispatch("memory.write", {"note": note}))

    @tool
    def refund_issue(amount: float) -> str:
        """Issue a refund. Irreversible; ABF requires approval + live state."""
        return str(rt.tools.dispatch("refund.issue", {"amount": amount}))

    model = ChatOpenAI(model=os.environ.get("ABF_OPENAI_MODEL", "gpt-4.1-mini"))
    agent = create_react_agent(
        model,
        [kv_get, memory_write, refund_issue],
        checkpointer=MemorySaver(),
    )
    prefix = stable_prefix(tools=tool_schemas())
    messages = [SystemMessage(content=m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])) for m in prefix]
    messages.append(HumanMessage(content="Look up account_status, note the review, refund $250 on acct/8841."))
    result = agent.invoke(
        {"messages": messages},
        {"configurable": {"thread_id": session.session_id}},
    )
    print(result["messages"][-1].content)
    rt.record_cache()
    print("ledger chain verified:", rt.ledger.verify_chain())


def main() -> None:
    parser = argparse.ArgumentParser(description="LangChain refund harness")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    session = CacheSession.new()
    print(json.dumps(native_surface(session), indent=2, default=str))
    if args.live:
        run_live(session)
    else:
        run_offline(session)


if __name__ == "__main__":
    main()
