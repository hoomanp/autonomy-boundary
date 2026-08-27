"""Bridge execute_payload uses the same PEP as the Python tools."""
from __future__ import annotations

from harnesses.bridge import execute_payload


def test_bridge_kv_then_refund():
    sid = "bridge-test-1"
    lookup = execute_payload({"action": "kv.get", "params": {"key": "account_status"}, "session_id": sid})
    assert lookup["ok"] is True
    assert lookup["result"] == "active"
    assert "bridge-test-1" in lookup["instance_id"]

    note = execute_payload({"action": "memory.write", "params": {"note": "reviewed"}, "session_id": sid})
    assert note["ok"] is True

    refund = execute_payload({"action": "refund.issue", "params": {"amount": 250.0}, "session_id": sid})
    assert refund["ok"] is True
    assert "250" in str(refund["result"])


def test_bridge_denies_out_of_scope():
    out = execute_payload({
        "action": "kv.put",
        "params": {"key": "secret", "value": "x"},
        "resource": "kv/payroll/secret",
        "session_id": "bridge-deny",
    })
    assert out["ok"] is False
    assert "scope" in (out.get("denied") or "")
