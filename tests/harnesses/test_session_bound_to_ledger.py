"""session_id is the software instance claim on the decision record (issue #3)."""
from __future__ import annotations

from harnesses.common.boundary import HarnessRuntime
from harnesses.common.cache_session import CacheSession


def test_session_id_appears_on_decision_record():
    session = CacheSession.new("sess-demo-001")
    rt = HarnessRuntime.start(session=session)
    rt.tools.execute("kv.get", {"key": "account_status"})

    decisions = [
        rec for rec in rt.ledger.read() if rec["event"] == "boundary_decision"
    ]
    assert decisions
    payload = decisions[-1]["payload"]
    assert payload["instance_id"] == session.instance_id
    assert "sess-demo-001" in payload["instance_id"]
    assert payload["approved_hash"] is None  # reversible kv.get needs no approval
    assert payload["in_force_grant"]["chain_budget"] == 8
    assert payload["in_force_grant"]["remaining_budget"] == 8


def test_refund_binds_approval_grant_and_instance():
    session = CacheSession.new("sess-refund-9")
    rt = HarnessRuntime.start(session=session)
    rt.tools.execute("memory.write", {"note": "reviewed"})
    rt.tools.execute("refund.issue", {"amount": 250.0})

    refunds = []
    for rec in rt.ledger.read():
        if rec["event"] != "boundary_decision":
            continue
        observed = [
            o for o in rt.ledger.read()
            if o["event"] == "intent_observed" and o["payload"]["hash"] == rec["payload"]["intent_hash"]
        ]
        if observed and observed[-1]["payload"]["intent"]["action"] == "refund.issue":
            refunds.append(rec["payload"])
    assert refunds
    row = refunds[-1]
    assert row["allowed"] is True
    assert row["approved_hash"]
    assert row["instance_id"] == "agent:refund:sess-refund-9"
    assert row["in_force_grant"]["remaining_budget"] == 7  # one write already spent
    observed_intent = [
        o["payload"]["intent"]
        for o in rt.ledger.read()
        if o["event"] == "intent_observed" and o["payload"]["intent"]["action"] == "refund.issue"
    ][-1]
    assert observed_intent["effective_identity"] == row["instance_id"]
