"""End-to-end demo: an agent proposes a refund; the boundary enforces the
seven controls; the Legibility control catches a swapped action.

Run:  python examples/refund_agent.py
"""
from __future__ import annotations

import os
import tempfile

import yaml

from abf import AutonomyBoundary, Intent, Ledger
from abf.controls import (
    AuthorityControl, InputIntegrityControl, LegibilityControl,
    ObservabilityControl, ProvabilityControl, ReversibilityControl, ScopeControl,
)
from abf.controls.legibility import approve, render_for_human

KEY = os.urandom(32)


def build_boundary(policy_path: str, ledger: Ledger) -> AutonomyBoundary:
    with open(policy_path) as f:
        policy = yaml.safe_load(f)
    controls = [
        ScopeControl(policy["scope"]["allowed_resources"]),
        AuthorityControl(policy["authority"]["allowed_actions"], KEY),
        InputIntegrityControl(),
        ReversibilityControl(policy["reversibility"]["irreversible_actions"]),
        LegibilityControl(),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]
    return AutonomyBoundary(controls, ledger)


def main() -> None:
    ledger = Ledger(tempfile.mktemp(suffix=".jsonl"))
    boundary = build_boundary("policies/default.yaml", ledger)

    # 1. The agent proposes an action and signs the intent.
    intent = Intent("refund.issue", "acct/8841", {"amount": 250.00}).sign(KEY)
    print("approval dialog:", render_for_human(intent))

    # 2. A human approves what they were shown; the token binds the hash.
    approval = approve(intent, approver="hp")

    # 3. The executor runs it through the boundary.
    boundary.execute(intent, lambda i: f"refunded {i.params['amount']}", {"approval": approval})
    print("executed: approved == authorized held")

    # 4. The attack: the action is swapped after approval (SymJack class).
    swapped = Intent("refund.issue", "acct/8841", {"amount": 25000.00}).sign(KEY)
    try:
        boundary.execute(swapped, lambda i: "should never run", {"approval": approval})
    except PermissionError as e:
        print("blocked:", e)

    print("ledger chain verified:", ledger.verify_chain())


if __name__ == "__main__":
    main()
