from abf.controls.legibility import LegibilityControl, approve
from abf.intent import Intent


def test_approved_equals_authorized_passes():
    intent = Intent("refund.issue", "acct/1", {"amount": 250.0})
    result = LegibilityControl().check(intent, {"approval": approve(intent, "hp")})
    assert result.allowed


def test_swapped_action_fails_closed():
    shown = Intent("refund.issue", "acct/1", {"amount": 250.0})
    executed = Intent("refund.issue", "acct/1", {"amount": 25000.0})
    result = LegibilityControl().check(executed, {"approval": approve(shown, "hp")})
    assert not result.allowed
    assert "does not match" in result.reason
