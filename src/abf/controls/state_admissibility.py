"""State Admissibility: the world behind an approval still deserves to govern.

Legibility proves the executed action is the approved action. This control
asks whether the decision-critical state that made that action eligible is
still the state that was bound at approval — and, for high-risk actions,
whether the validity window is still open. Window and state check are
separate conditions, not substitutes.

A matching hash proves the bound snapshot is unchanged. It does not prove
the original state was sound, complete, or trustworthy. That remains an
explicit non-goal of this control.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


def _parse_window(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class StateAdmissibilityControl(Control):
    name = "state_admissibility"

    def __init__(
        self,
        required_deps: Mapping[str, list[str]] | None = None,
        high_risk_actions: list[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.required_deps = {k: list(v) for k, v in (required_deps or {}).items()}
        self.high_risk = set(high_risk_actions or [])
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        required = set(self.required_deps.get(intent.action, []))
        bound = dict(intent.state_deps)
        omitted = sorted(required - set(bound))
        if omitted:
            return self.deny(
                "required dependency omitted",
                omitted=omitted,
            )

        if not bound:
            return self.allow("no decision-critical dependencies declared")

        current = dict(context.get("current_state") or {})
        high_risk = intent.action in self.high_risk

        if high_risk and not intent.validity_window:
            return self.deny("high-risk action requires a validity window")

        if intent.validity_window:
            now = self.clock()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if now >= _parse_window(intent.validity_window):
                return self.deny("validity window expired")

        if high_risk and not current:
            return self.deny(
                "high-risk action requires current state; a live window is not a substitute"
            )

        missing = sorted(set(bound) - set(current))
        if missing:
            return self.deny("current state missing for bound dependency", missing=missing)

        changed = sorted(name for name, digest in bound.items() if current.get(name) != digest)
        if changed:
            return self.deny("state changed since approval", changed=changed)

        return self.allow(
            "bound state unchanged since approval; original soundness not claimed"
        )
