"""Reversibility: irreversible actions require a human approval token in
context; reversible actions may proceed under the other controls alone."""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


class ReversibilityControl(Control):
    name = "reversibility"

    def __init__(self, irreversible_actions: list[str]) -> None:
        self.irreversible = set(irreversible_actions)

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        if intent.action not in self.irreversible:
            return self.allow("action is reversible")
        if context.get("approval") is None:
            return self.deny("irreversible action requires human approval", action=intent.action)
        return self.allow("irreversible action carries an approval")
