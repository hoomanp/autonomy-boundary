"""In-process session memory and KV. Reads feed State Admissibility; writes
are effects that must already have passed the PEP.
"""
from __future__ import annotations

from typing import Any

from abf import snapshot_state

ACCOUNT = "acct/8841"


class Store:
    """Application memory, not a provider KV cache.

    Implicit prompt cache is not data retention. This store is: notes and
    KV entries are decision-critical state (issue #1) and must be re-hashed
    before a high-risk refund lands.
    """

    def __init__(self) -> None:
        self.account_status = "active"
        self.refund_policy = "v3"
        self.notes: list[str] = []
        self.kv: dict[str, Any] = {
            f"kv/{ACCOUNT}/account_status": "active",
            f"kv/{ACCOUNT}/refund_policy": "v3",
        }

    def memory_fingerprint(self) -> str:
        return snapshot_state({"notes": list(self.notes)})["notes"]

    def eligibility(self) -> dict[str, Any]:
        return {
            "account_status": self.account_status,
            "refund_policy": self.refund_policy,
            "memory_fingerprint": self.memory_fingerprint(),
        }

    def eligibility_snapshot(self) -> dict[str, str]:
        return snapshot_state(self.eligibility())

    def read_kv(self, resource: str) -> Any:
        if resource not in self.kv:
            raise KeyError(resource)
        return self.kv[resource]

    def write_kv(self, resource: str, value: Any) -> None:
        self.kv[resource] = value
        if resource.endswith("/account_status"):
            self.account_status = str(value)
        if resource.endswith("/refund_policy"):
            self.refund_policy = str(value)

    def write_note(self, note: str) -> None:
        self.notes.append(note)
