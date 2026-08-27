"""Scripted tool-call turns. Demos and tests run with no API keys."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


def scripted_turns() -> list[ToolCall]:
    """Same customer-ops story every harness tells."""
    return [
        ToolCall("kv.get", {"key": "account_status"}),
        ToolCall("memory.write", {"note": "reviewed acct/8841 for a $250 refund"}),
        ToolCall("refund.issue", {"amount": 250.0}),
    ]
