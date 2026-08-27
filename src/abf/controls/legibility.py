"""Legibility: approved must equal authorized.

The approval surface renders from the canonical intent — including the
post-resolution semantic effect — and the approval token binds that hash.
At the last enforcement point after resolution, immediately before effect,
the control recomputes the hash and compares execution-time resolution to
the bound effect. Divergence fails closed (TOCTOU / SymJack).
"""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent

_EFFECT_FIELDS = (
    "resolved_target",
    "effective_identity",
    "capabilities",
    "data_boundary",
    "expiry",
)


def render_for_human(intent: Intent) -> str:
    """The approval dialog text, derived from the canonical intent only."""
    caps = ",".join(intent.capabilities) or "-"
    return (
        f"[{intent.intent_id}] {intent.action} on {intent.effect_target} "
        f"as {intent.effective_identity or '-'} caps={caps} "
        f"data={intent.data_boundary or '-'} until {intent.expiry or '-'} "
        f"with {dict(intent.params)} (hash {intent.hash[:12]})"
    )


def approve(intent: Intent, approver: str) -> dict[str, Any]:
    """A human approval token, bound to the intent hash it was shown."""
    return {"approver": approver, "approved_hash": intent.hash, "rendered": render_for_human(intent)}


class LegibilityControl(Control):
    name = "legibility"

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        approval = context.get("approval")
        if approval is None:
            return self.allow("no approval present; reversibility governs whether one is required")
        executing_hash = intent.hash  # recomputed from the action about to run
        if approval.get("approved_hash") != executing_hash:
            return self.deny(
                "approved hash does not match executing hash",
                approved=approval.get("approved_hash", "")[:12],
                executing=executing_hash[:12],
            )

        executing_effect = context.get("execution_effect")
        if executing_effect:
            bound = {
                "resolved_target": intent.effect_target,
                "effective_identity": intent.effective_identity,
                "capabilities": tuple(intent.capabilities),
                "data_boundary": intent.data_boundary,
                "expiry": intent.expiry,
            }
            for field in _EFFECT_FIELDS:
                actual = executing_effect.get(field)
                if actual is None:
                    continue
                expected = bound[field]
                if field == "capabilities":
                    actual = tuple(actual)
                if actual != expected:
                    return self.deny(
                        "approval-time and execution-time resolution diverged",
                        field=field,
                        bound=str(expected),
                        executing=str(actual),
                    )

        return self.allow("approved == authorized", hash=executing_hash[:12])
