"""Reversibility: irreversible actions require a human approval token in
context; reversible actions may proceed under the other controls alone."""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


class ReversibilityControl(Control):
    name = "reversibility"

    def __init__(
        self,
        irreversible_actions: list[str] | None = None,
        *,
        reversible_actions: list[str] | None = None,
    ) -> None:
        self.irreversible = set(irreversible_actions or [])
        self.reversible = set(reversible_actions) if reversible_actions is not None else None

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        is_irreversible = intent.action in self.irreversible or (
            self.reversible is not None and intent.action not in self.reversible
        )
        if not is_irreversible:
            return self.allow("action is reversible")
        if context.get("approval") is None:
            return self.deny(
                "irreversible action requires human approval",
                action=intent.action,
                requires_approval=True,
            )
        return self.allow("irreversible action carries an approval")
