"""Scope: the agent may only act on resources inside its declared scope."""
from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


class ScopeControl(Control):
    name = "scope"

    def __init__(self, allowed_resources: list[str]) -> None:
        self.allowed_resources = allowed_resources

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        target = intent.effect_target
        for pattern in self.allowed_resources:
            if fnmatch(target, pattern):
                return self.allow(f"resource matches scope pattern '{pattern}'")
        return self.deny(
            "resource outside declared scope",
            resource=target,
            scope=self.allowed_resources,
        )
