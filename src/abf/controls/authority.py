"""Authority: the action must appear on an explicit allowlist, and the
intent's signature must verify. Capability envelopes and cumulative
chain budgets bound what a task — including subprocesses and parallel
siblings — may spend. No allowlist entry, no authority.
"""
from __future__ import annotations

from typing import Any, Iterable

from abf.controls.base import Control, ControlResult
from abf.intent import Intent


class AuthorityControl(Control):
    name = "authority"

    def __init__(
        self,
        allowed_actions: list[str],
        signing_key: bytes,
        *,
        capability_envelope: Iterable[str] | None = None,
        chain_budget: int | None = None,
    ) -> None:
        self.allowed_actions = set(allowed_actions)
        self.signing_key = signing_key
        self.capability_envelope = set(capability_envelope) if capability_envelope is not None else None
        self.chain_budget = chain_budget

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        if not intent.verify_signature(self.signing_key):
            return self.deny("intent signature invalid or missing")
        if intent.action not in self.allowed_actions:
            return self.deny("action not on allowlist", action=intent.action)

        requested = set(intent.capabilities)
        envelope = self.capability_envelope
        if envelope is not None and not requested <= envelope:
            return self.deny(
                "capabilities exceed envelope",
                requested=sorted(requested),
                envelope=sorted(envelope),
            )

        parent = context.get("parent_envelope")
        if parent is not None and not requested <= set(parent):
            return self.deny(
                "capabilities exceed parent envelope",
                requested=sorted(requested),
                parent_envelope=list(parent),
            )

        if self.chain_budget is not None:
            spent = int(context.get("task_spend") or 0)
            if spent >= self.chain_budget:
                return self.deny(
                    "task authority budget exhausted",
                    spent=spent,
                    budget=self.chain_budget,
                )

        return self.allow("signed intent, allowlisted action, within envelope and budget")
