"""Provability: the ledger chain must verify before any new action lands on
top of it. A broken chain halts the boundary."""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent
from abf.ledger import Ledger


class ProvabilityControl(Control):
    name = "provability"

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        if not self.ledger.path.exists():
            return self.allow("fresh ledger")
        if not self.ledger.verify_chain():
            return self.deny("ledger chain failed verification; halting")
        return self.allow("ledger chain verified")
