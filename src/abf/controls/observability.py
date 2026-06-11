"""Observability: every decision is recorded to the ledger as it happens,
not reconstructed afterward."""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent
from abf.ledger import Ledger


class ObservabilityControl(Control):
    name = "observability"

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        self.ledger.append("intent_observed", {"intent": intent.body(), "hash": intent.hash})
        return self.allow("intent recorded to ledger")
