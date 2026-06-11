"""Authority: the action must appear on an explicit allowlist, and the
intent's signature must verify. No allowlist entry, no authority."""
from __future__ import annotations

from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


class AuthorityControl(Control):
    name = "authority"

    def __init__(self, allowed_actions: list[str], signing_key: bytes) -> None:
        self.allowed_actions = set(allowed_actions)
        self.signing_key = signing_key

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        if not intent.verify_signature(self.signing_key):
            return self.deny("intent signature invalid or missing")
        if intent.action not in self.allowed_actions:
            return self.deny("action not on allowlist", action=intent.action)
        return self.allow("signed intent, allowlisted action")
