"""ABF-gated tools. execute builds a signed Intent, runs the PEP, then mutates.

Memory and KV never bypass the boundary. A swapped amount is a different
intent hash (Legibility). A stale memory fingerprint is a different world
(State Admissibility). A KV write outside acct/* is Scope.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from abf import AutonomyBoundary, Intent
from abf.controls.legibility import approve

from harnesses.common.cache_session import CacheSession
from harnesses.common.memory import ACCOUNT, Store

WINDOW = "2099-01-01T00:00:00+00:00"

CAPABILITIES: dict[str, tuple[str, ...]] = {
    "refund.issue": ("refund",),
    "memory.write": ("write",),
    "kv.get": ("read",),
    "kv.put": ("write",),
}

DEFAULT_RESOURCE: dict[str, str] = {
    "refund.issue": ACCOUNT,
    "memory.write": f"memory/{ACCOUNT}",
}


def default_resource(action: str, params: Mapping[str, Any]) -> str:
    if action in ("kv.get", "kv.put"):
        key = str(params.get("key") or params.get("resource") or "unknown")
        if key.startswith("kv/"):
            return key
        return f"kv/{ACCOUNT}/{key}"
    return str(params.get("resource") or DEFAULT_RESOURCE[action])


class ToolRuntime:
    def __init__(
        self,
        *,
        boundary: AutonomyBoundary,
        key: bytes,
        session: CacheSession,
        store: Store,
        chain_budget: int = 8,
        approver: str = "harness:operator",
    ) -> None:
        self.boundary = boundary
        self.key = key
        self.session = session
        self.store = store
        self.chain_budget = chain_budget
        self.approver = approver
        self.task_spend = 0

    def make_intent(
        self,
        action: str,
        params: Mapping[str, Any],
        *,
        resource: str | None = None,
        state_deps: Mapping[str, str] | None = None,
    ) -> Intent:
        target = resource or default_resource(action, params)
        clean = {k: v for k, v in params.items() if k != "resource"}
        return Intent(
            action,
            target,
            clean,
            resolved_target=target,
            effective_identity=self.session.instance_id,
            capabilities=CAPABILITIES[action],
            data_boundary=target,
            expiry=WINDOW,
            state_deps=dict(state_deps if state_deps is not None else self.store.eligibility_snapshot()),
            validity_window=WINDOW,
        ).sign(self.key)

    def context_for(
        self,
        intent: Intent,
        *,
        approval: dict[str, Any] | None = None,
        current_state: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        remaining = max(self.chain_budget - self.task_spend, 0)
        token = approval
        if token is None and intent.action == "refund.issue":
            token = approve(intent, self.approver)
        return {
            "approval": token,
            "current_state": dict(current_state if current_state is not None else self.store.eligibility_snapshot()),
            "task_spend": self.task_spend,
            "instance_id": self.session.instance_id,
            "in_force_grant": {
                "capability_envelope": ["read", "write", "refund"],
                "remaining_budget": remaining,
                "expiry": WINDOW,
                "chain_budget": self.chain_budget,
            },
        }

    def execute(
        self,
        action: str,
        params: Mapping[str, Any],
        *,
        resource: str | None = None,
        approval: dict[str, Any] | None = None,
        state_deps: Mapping[str, str] | None = None,
        current_state: Mapping[str, str] | None = None,
    ) -> Any:
        intent = self.make_intent(action, params, resource=resource, state_deps=state_deps)
        ctx = self.context_for(intent, approval=approval, current_state=current_state)
        outcome = self.boundary.execute(intent, self._apply, ctx)
        self.task_spend += 1
        return outcome

    def dispatch(self, name: str, args: Mapping[str, Any], **kwargs: Any) -> Any:
        action = name if "." in name else {
            "refund_issue": "refund.issue",
            "refund.issue": "refund.issue",
            "memory_write": "memory.write",
            "memory.write": "memory.write",
            "kv_get": "kv.get",
            "kv.get": "kv.get",
            "kv_put": "kv.put",
            "kv.put": "kv.put",
        }.get(name, name)
        resource = args.get("resource")
        return self.execute(action, args, resource=resource, **kwargs)

    def _apply(self, intent: Intent) -> Any:
        apply: dict[str, Callable[[Intent], Any]] = {
            "refund.issue": lambda i: f"refunded {i.params['amount']} on {i.effect_target}",
            "memory.write": self._write_memory,
            "kv.get": lambda i: self.store.read_kv(i.effect_target),
            "kv.put": self._put_kv,
        }
        if intent.action not in apply:
            raise ValueError(f"unknown action {intent.action}")
        return apply[intent.action](intent)

    def _write_memory(self, intent: Intent) -> str:
        note = str(intent.params.get("note") or "")
        self.store.write_note(note)
        return f"remembered {len(self.store.notes)} note(s)"

    def _put_kv(self, intent: Intent) -> str:
        self.store.write_kv(intent.effect_target, intent.params.get("value"))
        return f"stored {intent.effect_target}"
