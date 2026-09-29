import os
import tempfile

import pytest

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

KEY = os.urandom(32)
APPROVER_KEY = os.urandom(32)


def make_skill(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    controls = [
        ScopeControl(["acct/*"]),
        AuthorityControl(["refund.issue", "account.lookup"], KEY),
        InputIntegrityControl(),
        ReversibilityControl(["refund.issue"]),
        LegibilityControl(approver_key=APPROVER_KEY),
        StateAdmissibilityControl(required_deps={"refund.issue": ["status"]}),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]
    boundary = AutonomyBoundary(controls, ledger)
    skill = AutonomyBoundarySkill(boundary, KEY, approver_key=APPROVER_KEY)
    skill.register_action("refund.issue", lambda p: f"refunded {p['amount']}")
    skill.register_action("account.lookup", lambda p: f"account active: {p['account_id']}")
    return skill, ledger


def test_skill_propose_reversible_action(tmp_path):
    skill, _ = make_skill(tmp_path)
    proposal = skill.propose_action("account.lookup", "acct/123", {"account_id": "acct/123"})
    assert not proposal.requires_approval
    assert proposal.status == "ready_autonomous"
    # Autonomous execution
    result = skill.execute_action(proposal.intent.hash)
    assert "account active: acct/123" in result


def test_skill_propose_irreversible_action(tmp_path):
    skill, ledger = make_skill(tmp_path)
    deps = {"status": "active"}
    proposal = skill.propose_action(
        "refund.issue",
        "acct/123",
        {"amount": 250},
        state_deps=deps,
    )
    assert proposal.requires_approval
    assert proposal.status == "requires_human_approval"
    assert "refund.issue on acct/123" in proposal.approval_prompt

    # Execute without approval fails
    with pytest.raises(PermissionError, match="reversibility"):
        skill.execute_action(proposal.intent.hash, current_state=deps)

    # Approve and execute succeeds
    token = skill.approve_proposal(proposal.intent.hash, approver="alice")
    result = skill.execute_action(proposal.intent.hash, approval=token, current_state=deps)
    assert result == "refunded 250"

    audit = skill.inspect_ledger()
    assert audit["chain_intact"] is True
    assert audit["record_count"] >= 2


def test_skill_tool_declarations():
    boundary = AutonomyBoundary([], Ledger(tempfile.mktemp()))
    skill = AutonomyBoundarySkill(boundary, KEY)
    tools = skill.get_tool_declarations()
    assert len(tools) == 3
    names = [t["function"]["name"] for t in tools]
    assert "boundary_propose_action" in names
    assert "boundary_execute_action" in names
    assert "boundary_inspect_ledger" in names
