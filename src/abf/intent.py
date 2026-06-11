"""The signed, canonical intent object.

One representation of an action, read by both the approval surface and the
executor. The Legibility control asserts that the hash a human approved is
the hash the executor runs: approved must equal authorized.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Deterministic serialization: sorted keys, no whitespace drift."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical serialization."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Intent:
    """An immutable, signed description of one action an agent proposes.

    `action`    dotted verb, e.g. "refund.issue"
    `resource`  the target, e.g. "acct/8841"
    `params`    action parameters
    `signature` HMAC-SHA256 over the canonical body (swap for Ed25519 in
                production; the binding logic is identical)
    """

    action: str
    resource: str
    params: Mapping[str, Any]
    intent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    signature: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action": self.action,
            "resource": self.resource,
            "params": dict(self.params),
        }

    @property
    def hash(self) -> str:
        return canonical_hash(self.body())

    def sign(self, key: bytes) -> "Intent":
        sig = hmac.new(key, canonical_json(self.body()).encode(), hashlib.sha256).hexdigest()
        return Intent(self.action, self.resource, self.params, self.intent_id, sig)

    def verify_signature(self, key: bytes) -> bool:
        expected = hmac.new(key, canonical_json(self.body()).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)
