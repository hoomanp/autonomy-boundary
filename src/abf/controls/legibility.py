"""Legibility: approved must equal authorized.

The approval surface renders from the canonical intent and the approval
token binds its hash. At execution time the control recomputes the hash of
the action actually about to run and asserts equality with the approved
hash. A mismatch is the TrustFall/SymJack class of failure, and it fails
closed here.
"""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


def render_for_human(intent: Intent) -> str:
    """The approval dialog text, derived from the canonical intent only."""
    return (
        f"[{intent.intent_id}] {intent.action} on {intent.resource} "
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
        return self.allow("approved == authorized", hash=executing_hash[:12])
