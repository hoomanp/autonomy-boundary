"""AI Agent Chatbot Skill Example for the Autonomy Boundary Framework.

Demonstrates how an AI Agent or Chatbot imports `AutonomyBoundarySkill` to
govern its own tool proposals, render human approval prompts, assert live
state admissibility, and maintain a mathematically tamper-evident audit trail.

Run:
    python examples/skill_agent.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

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
from abf.skill import AutonomyBoundarySkill

AGENT_KEY = os.urandom(32)
APPROVER_KEY = os.urandom(32)


def main() -> None:
    print("=================================================================")
    print("  Autonomy Boundary Framework (ABF) — AI Agent Chatbot Skill")
    print("=================================================================\n")

    ledger = Ledger(tempfile.mktemp(suffix=".jsonl"))

    # Configure the 8 controls
    controls = [
        ScopeControl(["acct/*", "docs/*"]),
        AuthorityControl(
            allowed_actions=["docs.read", "payment.send"],
            signing_key=AGENT_KEY,
            capability_envelope=["read", "send"],
        ),
        InputIntegrityControl(),
        ReversibilityControl(irreversible_actions=["payment.send"]),
        LegibilityControl(approver_key=APPROVER_KEY),
        StateAdmissibilityControl(required_deps={"payment.send": ["compliance_status"]}),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]

    boundary = AutonomyBoundary(controls, ledger)

    # Initialize the importable skill
    skill = AutonomyBoundarySkill(
        boundary=boundary,
        signing_key=AGENT_KEY,
        approver_key=APPROVER_KEY,
        agent_identity="agent:enterprise-copilot",
    )

    # Register action implementations
    skill.register_action("docs.read", lambda p: f"Contents of {p['path']}: [Policy Document v4.1]")
    skill.register_action("payment.send", lambda p: f"Sent ${p['amount']} to {p['account_id']}")

    # --- Scenario 1: Reversible Action (Runs Autonomously) ---
    print("[1] Agent proposes reversible action: docs.read...")
    proposal_read = skill.propose_action("docs.read", "docs/policy", {"path": "docs/policy"})
    print(f"    Status: {proposal_read.status} (Requires approval: {proposal_read.requires_approval})")
    read_result = skill.execute_action(proposal_read.intent.hash)
    print(f"    Executed autonomously: '{read_result}'\n")

    # --- Scenario 2: Irreversible Action (Requires Human Approval) ---
    print("[2] Agent proposes irreversible action: payment.send $500.00...")
    compliance_state = {"compliance_status": "cleared"}
    proposal_pay = skill.propose_action(
        "payment.send",
        "acct/4921",
        {"account_id": "acct/4921", "amount": 500.0},
        state_deps=compliance_state,
    )
    print(f"    Status: {proposal_pay.status} (Requires approval: {proposal_pay.requires_approval})")
    print(f"    Rendered Approval Prompt Shown to Human:")
    print(f"    >>> {proposal_pay.approval_prompt}")

    # Human supervisor signs the approval token
    print("\n[3] Human supervisor verifies dialog and signs approval token...")
    token = skill.approve_proposal(proposal_pay.intent.hash, approver="ciso:alice")
    print(f"    Signed Token: approver={token['approver']} hash={token['approved_hash'][:12]}...")

    # Execute with live compliance state check
    print("\n[4] Executing payment with live state assertion...")
    pay_result = skill.execute_action(
        proposal_pay.intent.hash,
        approval=token,
        current_state=compliance_state,
    )
    print(f"    Execution Result: '{pay_result}'\n")

    # --- Scenario 3: Inspect Audit Ledger ---
    audit = skill.inspect_ledger()
    print("[5] Verifying Audit Trail:")
    print(f"    Chain Intact: {audit['chain_intact']}")
    print(f"    Total Events Logged: {audit['record_count']}")
    print(f"    Tamper-Evidence Invariant: PASSED")

    # --- Scenario 4: Export Tool Declarations for LLM Function Calling ---
    print("\n[6] LLM Function Calling Declarations (OpenAI/Anthropic compatible):")
    tools = skill.get_tool_declarations()
    for t in tools:
        fn = t["function"]
        print(f"    - {fn['name']}: {fn['description']}")

    print("\nAll Skill demonstration steps completed successfully.")


if __name__ == "__main__":
    main()
