"""Shared PEP factory for optional harness demos.

A harness may propose actions. This module is the only place those actions
are authorized. Extracted from the refund example so every SDK demo shares
one signing key, one policy, and one ledger.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from abf import AutonomyBoundary, Ledger
from abf.controls import (
    AuthorityControl,
    InputIntegrityControl,
    LegibilityControl,
    ObservabilityControl,
    ProvabilityControl,
    ReversibilityControl,
    ScopeControl,
    StateAdmissibilityControl,
)

from harnesses.common.cache_session import CacheSession
from harnesses.common.memory import Store
from harnesses.common.tools import ToolRuntime

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = ROOT / "policies" / "harness.yaml"
WINDOW = "2099-01-01T00:00:00+00:00"


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_POLICY) as f:
        return yaml.safe_load(f)


def build_boundary(
    policy_path: str | Path | None,
    ledger: Ledger,
    *,
    signing_key: bytes,
) -> AutonomyBoundary:
    policy = load_policy(policy_path)
    authority = policy["authority"]
    state = policy["state_admissibility"]
    controls = [
        ScopeControl(policy["scope"]["allowed_resources"]),
        AuthorityControl(
            authority["allowed_actions"],
            signing_key,
            capability_envelope=authority.get("capability_envelope"),
            chain_budget=authority.get("chain_budget"),
        ),
        InputIntegrityControl(),
        ReversibilityControl(policy["reversibility"]["irreversible_actions"]),
        LegibilityControl(),
        StateAdmissibilityControl(
            required_deps=state.get("required_deps"),
            high_risk_actions=state.get("high_risk_actions"),
        ),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]
    return AutonomyBoundary(controls, ledger)


@dataclass
class HarnessRuntime:
    """One customer-ops session: store, cache session, PEP, gated tools."""

    key: bytes
    ledger: Ledger
    boundary: AutonomyBoundary
    store: Store
    session: CacheSession
    tools: ToolRuntime
    policy: dict[str, Any]
    chain_budget: int = 8
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        *,
        policy_path: str | Path | None = None,
        ledger_path: str | Path | None = None,
        session: CacheSession | None = None,
        signing_key: bytes | None = None,
        store: Store | None = None,
    ) -> "HarnessRuntime":
        key = signing_key or os.urandom(32)
        ledger = Ledger(ledger_path or tempfile.mktemp(suffix=".jsonl"))
        policy = load_policy(policy_path)
        boundary = build_boundary(policy_path, ledger, signing_key=key)
        cache = session or CacheSession.new()
        mem = store or Store()
        tools = ToolRuntime(
            boundary=boundary,
            key=key,
            session=cache,
            store=mem,
            chain_budget=int(policy["authority"].get("chain_budget") or 8),
        )
        return cls(
            key=key,
            ledger=ledger,
            boundary=boundary,
            store=mem,
            session=cache,
            tools=tools,
            policy=policy,
            chain_budget=int(policy["authority"].get("chain_budget") or 8),
        )

    def record_cache(self, cached_tokens: int = 0, cache_discount: float = 0.0) -> None:
        """Observability: prompt-cache hits are effects, not a ninth control."""
        self.ledger.append(
            "cache_observed",
            {
                "session_id": self.session.session_id,
                "prompt_cache_key": self.session.prompt_cache_key,
                "cached_tokens": cached_tokens,
                "cache_discount": cache_discount,
            },
        )
