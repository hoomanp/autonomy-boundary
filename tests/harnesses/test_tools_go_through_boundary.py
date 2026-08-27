"""Harness tools cannot bypass Legibility, State Admissibility, or Scope."""
from __future__ import annotations

import pytest

from abf.controls.legibility import approve
from harnesses.common.boundary import HarnessRuntime
from harnesses.common.tools import ToolRuntime


def test_swapped_amount_denied_by_legibility():
    rt = HarnessRuntime.start()
    shown = rt.tools.make_intent("refund.issue", {"amount": 250.0})
    approval = approve(shown, "hp")
    with pytest.raises(PermissionError, match="legibility"):
        rt.tools.execute("refund.issue", {"amount": 25000.0}, approval=approval)


def test_stale_memory_fingerprint_denied_by_state_admissibility():
    rt = HarnessRuntime.start()
    rt.tools.execute("memory.write", {"note": "first review"})
    stale = rt.store.eligibility_snapshot()
    rt.tools.execute("memory.write", {"note": "later note changes fingerprint"})
    with pytest.raises(PermissionError, match="state_admissibility"):
        rt.tools.execute("refund.issue", {"amount": 250.0}, state_deps=stale)


def test_kv_put_outside_scope_denied():
    rt = HarnessRuntime.start()
    with pytest.raises(PermissionError, match="scope"):
        rt.tools.execute(
            "kv.put",
            {"key": "secret", "value": "payroll"},
            resource="kv/payroll/secret",
        )


def test_happy_path_refund_after_memory_and_kv():
    rt = HarnessRuntime.start()
    assert rt.tools.execute("kv.get", {"key": "account_status"}) == "active"
    assert "note" in rt.tools.execute("memory.write", {"note": "ok to refund"})
    out = rt.tools.execute("refund.issue", {"amount": 250.0})
    assert "250" in out
    assert rt.ledger.verify_chain()
    assert rt.tools.task_spend == 3


def test_tools_never_mutate_before_pep(monkeypatch):
    rt = HarnessRuntime.start()
    seen: list[str] = []
    original = ToolRuntime._apply

    def wrapped(self, intent):
        seen.append(intent.action)
        return original(self, intent)

    monkeypatch.setattr(ToolRuntime, "_apply", wrapped)
    with pytest.raises(PermissionError, match="scope"):
        rt.tools.execute("kv.put", {"value": "x"}, resource="kv/payroll/secret")
    assert seen == []
    assert "kv/payroll/secret" not in rt.store.kv
