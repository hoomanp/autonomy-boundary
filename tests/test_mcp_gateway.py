import json
import os
import tempfile

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
from abf.controls.legibility import approve
from abf.mcp import ABFMCPGateway

KEY = os.urandom(32)
APPROVER_KEY = os.urandom(32)


def make_gateway(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    controls = [
        ScopeControl(["acct/*"]),
        AuthorityControl(["mcp.refund", "mcp.status"], KEY),
        InputIntegrityControl(),
        ReversibilityControl(["mcp.refund"]),
        LegibilityControl(approver_key=APPROVER_KEY),
        StateAdmissibilityControl(),
        ObservabilityControl(ledger),
        ProvabilityControl(ledger),
    ]
    boundary = AutonomyBoundary(controls, ledger)
    gateway = ABFMCPGateway(boundary, KEY, approver_key=APPROVER_KEY)

    @gateway.tool(name="refund", description="Issue customer refund", irreversible=True)
    def refund(params):
        return f"refunded {params['amount']} to {params['account_id']}"

    @gateway.tool(name="status", description="Get account status")
    def status(params):
        return f"active account {params['account_id']}"

    return gateway, ledger


def test_mcp_gateway_tools_list(tmp_path):
    gateway, _ = make_gateway(tmp_path)
    res = gateway.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert "result" in res
    tools = res["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "refund" in names
    assert "status" in names


def test_mcp_gateway_autonomous_reversible_call(tmp_path):
    gateway, ledger = make_gateway(tmp_path)
    msg = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "status", "arguments": {"account_id": "acct/123"}},
    }
    res = gateway.handle_jsonrpc(msg)
    assert "result" in res
    assert "active account acct/123" in res["result"]["content"][0]["text"]
    assert ledger.verify_chain()


def test_mcp_gateway_irreversible_requires_approval(tmp_path):
    gateway, _ = make_gateway(tmp_path)
    # Call without approval token
    msg = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "refund", "arguments": {"account_id": "acct/123", "amount": 50}},
    }
    res = gateway.handle_jsonrpc(msg)
    assert "error" in res
    assert "reversibility" in res["error"]["message"]


def test_mcp_gateway_with_valid_approval_token(tmp_path):
    gateway, ledger = make_gateway(tmp_path)
    args = {"account_id": "acct/123", "amount": 50}
    intent = gateway.create_intent("refund", args)
    token = approve(intent, approver="supervisor_bob", key=APPROVER_KEY)

    msg = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "refund", "arguments": args},
    }
    res = gateway.handle_jsonrpc(msg, context={"approval": token})
    assert "result" in res
    assert "refunded 50 to acct/123" in res["result"]["content"][0]["text"]
    assert ledger.verify_chain()
