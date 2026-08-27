"""The signed, canonical intent object.

One representation of an action, read by both the approval surface and the
executor. The hash binds the post-resolution semantic effect — resolved
target, effective identity, capability set, data boundary, expiry — plus
the decision-critical state snapshot State Admissibility will re-check.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import posixpath
import re
import uuid
from dataclasses import dataclass, field, replace
from string import Template
from typing import Any, Mapping

_UNEXPANDED = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Deterministic serialization: sorted keys, no whitespace drift."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical serialization."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def snapshot_state(values: Mapping[str, Any]) -> dict[str, str]:
    """Hash each named dependency. Key order does not affect the mapping."""
    return {name: canonical_hash({name: values[name]}) for name in values}


def canonicalize_target(
    target: str,
    *,
    env: Mapping[str, str] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> str:
    """Resolve a target to the post-resolution form bound into an intent.

    Order: environment expansion → alias substitution → POSIX normalize →
    follow symlinks if the path exists. Unexpanded ``$VAR`` references fail
    closed. Network-layer redirects and container path mapping are out of
    coverage for this reference (see issue #2).
    """
    expanded = Template(target).safe_substitute(dict(env or {}))
    if _UNEXPANDED.search(expanded):
        raise ValueError(f"unexpanded environment reference in target: {expanded}")
    resolved = dict(aliases or {}).get(expanded, expanded)
    if "/" in resolved or resolved.startswith("."):
        resolved = posixpath.normpath(resolved)
        if os.path.lexists(resolved):
            resolved = os.path.realpath(resolved)
    return resolved


@dataclass(frozen=True)
class Intent:
    """An immutable, signed description of one action an agent proposes.

    `action`             dotted verb, e.g. "refund.issue"
    `resource`           the target as named at proposal time
    `params`             action parameters
    `resolved_target`    post-resolution canonical target (issue #2)
    `effective_identity` identity the effect will run as
    `capabilities`       capability set the effect is empowered to use
    `data_boundary`      data the effect may touch
    `expiry`             when this grant dies
    `state_deps`         name → snapshot hash of decision-critical state (issue #1)
    `validity_window`    when the bound state snapshot expires
    `signature`          HMAC-SHA256 over the canonical body (swap for Ed25519
                         in production; the binding logic is identical)
    """

    action: str
    resource: str
    params: Mapping[str, Any]
    intent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    signature: str = ""
    resolved_target: str = ""
    effective_identity: str = ""
    capabilities: tuple[str, ...] = ()
    data_boundary: str = ""
    expiry: str = ""
    state_deps: Mapping[str, str] = field(default_factory=dict)
    validity_window: str = ""

    @property
    def effect_target(self) -> str:
        """The target Scope and Legibility must check: resolved, else named."""
        return self.resolved_target or self.resource

    def body(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action": self.action,
            "resource": self.resource,
            "params": dict(self.params),
            "resolved_target": self.effect_target,
            "effective_identity": self.effective_identity,
            "capabilities": sorted(self.capabilities),
            "data_boundary": self.data_boundary,
            "expiry": self.expiry,
            "state_deps": dict(self.state_deps),
            "validity_window": self.validity_window,
        }

    @property
    def hash(self) -> str:
        return canonical_hash(self.body())

    def sign(self, key: bytes) -> "Intent":
        sig = hmac.new(key, canonical_json(self.body()).encode(), hashlib.sha256).hexdigest()
        return replace(self, signature=sig)

    def verify_signature(self, key: bytes) -> bool:
        expected = hmac.new(key, canonical_json(self.body()).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)
