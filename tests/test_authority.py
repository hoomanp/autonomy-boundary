import os

from abf.controls.authority import AuthorityControl
from abf.intent import Intent

KEY = b"k" * 32


def _control(**kwargs):
    return AuthorityControl(
        ["refund.issue", "ticket.close"],
        KEY,
        capability_envelope=["read", "refund"],
        chain_budget=2,
        **kwargs,
    )


def test_capabilities_outside_envelope_denied():
    intent = Intent(
        "refund.issue", "acct/1", {"amount": 1.0}, capabilities=("refund", "exec")
    ).sign(KEY)
    result = _control().check(intent, {})
    assert not result.allowed
    assert "envelope" in result.reason


def test_subprocess_cannot_exceed_parent_envelope():
    intent = Intent(
        "ticket.close", "ticket/1", {}, capabilities=("read", "refund")
    ).sign(KEY)
    result = _control().check(intent, {"parent_envelope": ["read"]})
    assert not result.allowed
    assert "parent envelope" in result.reason


def test_chain_budget_denies_when_spend_is_exhausted():
    intent = Intent(
        "refund.issue", "acct/1", {"amount": 1.0}, capabilities=("refund",)
    ).sign(KEY)
    result = _control().check(intent, {"task_spend": 2})
    assert not result.allowed
    assert "budget" in result.reason


def test_chain_budget_applies_to_parallel_spend_the_caller_accumulates():
    intent = Intent(
        "refund.issue", "acct/1", {"amount": 1.0}, capabilities=("refund",)
    ).sign(KEY)
    # Parallel chains share one counter: two prior siblings already spent the budget.
    result = _control().check(intent, {"task_spend": 2, "parallel": True})
    assert not result.allowed
    assert "budget" in result.reason


def test_within_envelope_and_budget_allows():
    intent = Intent(
        "refund.issue", "acct/1", {"amount": 1.0}, capabilities=("refund",)
    ).sign(KEY)
    result = _control().check(intent, {"task_spend": 1})
    assert result.allowed
