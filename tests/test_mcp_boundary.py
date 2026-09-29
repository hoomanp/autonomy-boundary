import os
import tempfile

from abf import AutonomyBoundary, Intent, Ledger
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
from abf.controls.legibility import approve
from mcp_boundary import MCPBoundaryProxy

PEP_KEY = os.urandom(32)
APPROVER_KEY = os.urandom(32)


def test_mcp_proxy_allows_valid_and_blocks_tampered():
    ledger = Ledger(tempfile.mktemp(suffix=".jsonl"))
    controls = [
        ScopeControl(["acct/*"]),
        AuthorityControl(["mcp.refund"], PEP_KEY),
        InputIntegrityControl(),
        ReversibilityControl(["mcp.refund"]),
        LegibilityControl(approver_key=APPROVER_KEY),
        StateAdmissibilityControl(),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]
    boundary = AutonomyBoundary(controls, ledger)
    proxy = MCPBoundaryProxy(boundary, signing_key=PEP_KEY)
    proxy.register_tool("refund", lambda args: f"refunded {args['amount']}")

    ctx: dict = {"instance_id": "mcp:test"}
    intent = proxy.create_intent("refund", {"account_id": "acct/1", "amount": 100}, ctx)
    token = approve(intent, approver="alice", key=APPROVER_KEY)
    ctx["approval"] = token

    # Valid call
    call = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {"name": "refund", "arguments": {"account_id": "acct/1", "amount": 100}},
    }
    resp = proxy.handle_mcp_request(call, ctx)
    assert "result" in resp
    assert "refunded 100" in resp["result"]["content"][0]["text"]

    # Tampered call (swapped amount)
    tampered_call = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "tools/call",
        "params": {"name": "refund", "arguments": {"account_id": "acct/1", "amount": 9999}},
    }
    resp_tampered = proxy.handle_mcp_request(tampered_call, ctx)
    assert "error" in resp_tampered
    assert "legibility" in resp_tampered["error"]["message"]
