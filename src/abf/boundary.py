"""The Autonomy Boundary orchestrator.

Runs the eight controls in lifecycle order against a signed intent. Any
deny, or any control exception, halts execution: the boundary fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from abf.controls.base import Control, ControlResult
from abf.intent import Intent
from abf.ledger import Ledger


@dataclass
class BoundaryDecision:
    allowed: bool
    results: list[ControlResult] = field(default_factory=list)

    @property
    def denials(self) -> list[ControlResult]:
        return [r for r in self.results if not r.allowed]


class AutonomyBoundary:
    def __init__(self, controls: list[Control], ledger: Ledger) -> None:
        self.controls = controls
        self.ledger = ledger

    def evaluate(self, intent: Intent, context: dict[str, Any] | None = None) -> BoundaryDecision:
        context = context or {}
        decision = BoundaryDecision(allowed=True)
        for control in self.controls:
            try:
                result = control.check(intent, context)
            except Exception as exc:  # fail closed
                result = ControlResult(control.name, False, f"control raised: {exc!r}")
            decision.results.append(result)
            if not result.allowed:
                decision.allowed = False
                break
        self.ledger.append(
            "boundary_decision",
            {
                "intent_hash": intent.hash,
                "allowed": decision.allowed,
                "results": [
                    {"control": r.control, "allowed": r.allowed, "reason": r.reason}
                    for r in decision.results
                ],
            },
        )
        return decision

    def execute(
        self,
        intent: Intent,
        action_fn: Callable[[Intent], Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        decision = self.evaluate(intent, context)
        if not decision.allowed:
            denied = decision.denials[0]
            raise PermissionError(f"boundary denied by {denied.control}: {denied.reason}")
        outcome = action_fn(intent)
        self.ledger.append("executed", {"intent_hash": intent.hash, "outcome": repr(outcome)})
        return outcome
