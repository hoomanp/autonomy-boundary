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


def test_approval_dialog_shows_resolved_effect_not_display_path():
    intent = Intent(
        "read_files",
        "/home/user/project/docs",
        {},
        resolved_target="/var/lib/project/docs",
        capabilities=("read",),
        data_boundary="/var/lib/project/docs",
        expiry="2026-08-26T23:00:00+00:00",
        effective_identity="agent:docs-reader",
    )
    from abf.controls.legibility import render_for_human
    rendered = render_for_human(intent)
    assert "/var/lib/project/docs" in rendered
    assert "read" in rendered


def test_execution_time_resolution_divergence_fails_closed():
    intent = Intent(
        "read_files",
        "/home/user/project/docs",
        {},
        resolved_target="/home/user/project/docs",
        capabilities=("read",),
        data_boundary="/home/user/project/docs",
        effective_identity="agent:docs-reader",
        expiry="2026-08-26T23:00:00+00:00",
    )
    result = LegibilityControl().check(
        intent,
        {
            "approval": approve(intent, "hp"),
            "execution_effect": {
                "resolved_target": "/etc/passwd",
                "effective_identity": "agent:docs-reader",
                "capabilities": ("read",),
                "data_boundary": "/home/user/project/docs",
                "expiry": "2026-08-26T23:00:00+00:00",
            },
        },
    )
    assert not result.allowed
    assert "resolution diverged" in result.reason
