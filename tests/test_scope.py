from abf.controls.scope import ScopeControl
from abf.intent import Intent, canonicalize_target


def test_scope_uses_resolved_target_not_display_path():
    control = ScopeControl(["acct/*"])
    display = "acct/../payroll/secret"
    intent = Intent(
        "refund.issue",
        display,
        {},
        resolved_target=canonicalize_target(display),
    )
    result = control.check(intent, {})
    assert not result.allowed
    assert result.detail["resource"] == "payroll/secret"
