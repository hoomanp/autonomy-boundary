"""End-to-end demo: an agent proposes a refund; the boundary enforces the
eight controls; Legibility catches a swapped action; State Admissibility
catches a frozen account after approval.

Run:  python examples/refund_agent.py
"""
from __future__ import annotations

import os
import tempfile

import yaml

from abf import AutonomyBoundary, Intent, Ledger, snapshot_state
from abf.controls import (
    AuthorityControl, InputIntegrityControl, LegibilityControl,
    ObservabilityControl, ProvabilityControl, ReversibilityControl,
    ScopeControl, StateAdmissibilityControl,
)
from abf.controls.legibility import approve, render_for_human

KEY = os.urandom(32)
WINDOW = "2099-01-01T00:00:00+00:00"


def build_boundary(policy_path: str, ledger: Ledger) -> AutonomyBoundary:
    with open(policy_path) as f:
        policy = yaml.safe_load(f)
    authority = policy["authority"]
    state = policy["state_admissibility"]
    controls = [
        ScopeControl(policy["scope"]["allowed_resources"]),
        AuthorityControl(
            authority["allowed_actions"],
            KEY,
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


def refund_intent(amount: float, deps: dict[str, str]) -> Intent:
    return Intent(
        "refund.issue",
        "acct/8841",
        {"amount": amount},
        resolved_target="acct/8841",
        effective_identity="agent:refund",
        capabilities=("refund",),
        data_boundary="acct/8841",
        expiry=WINDOW,
        state_deps=deps,
        validity_window=WINDOW,
    ).sign(KEY)


def main() -> None:
    ledger = Ledger(tempfile.mktemp(suffix=".jsonl"))
    boundary = build_boundary("policies/default.yaml", ledger)

    live = {"account_status": "active", "refund_policy": "v3"}
    deps = snapshot_state(live)
    intent = refund_intent(250.00, deps)
    print("approval dialog:", render_for_human(intent))

    approval = approve(intent, approver="hp")
    ctx = {"approval": approval, "current_state": deps, "task_spend": 0}
    boundary.execute(intent, lambda i: f"refunded {i.params['amount']}", ctx)
    print("executed: approved == authorized held; state still admissible")

    swapped = refund_intent(25000.00, deps)
    try:
        boundary.execute(swapped, lambda i: "should never run", ctx)
    except PermissionError as e:
        print("blocked:", e)

    frozen = snapshot_state({"account_status": "frozen", "refund_policy": "v3"})
    try:
        boundary.execute(intent, lambda i: "should never run", {**ctx, "current_state": frozen})
    except PermissionError as e:
        print("blocked:", e)

    print("ledger chain verified:", ledger.verify_chain())


if __name__ == "__main__":
    main()
