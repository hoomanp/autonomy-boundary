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


def test_scope_probe_passes_when_target_enforces():
    def probe_fn(intent, ctx):
        return True, "target enforces read-only"

    control = ScopeControl(["wiki/*"], probe=probe_fn)
    intent = Intent("page.view", "wiki/home", {})
    result = control.check(intent, {})
    assert result.allowed


def test_scope_probe_fails_closed_when_target_diverges():
    # Simulates the OpenAI DSEWiki failure class:
    # Harness declares read-only, but target's endpoint mutates state.
    def probe_fn(intent, ctx):
        return False, "target mutated 1 record under declared read-only scope"

    control = ScopeControl(["wiki/*"], probe=probe_fn)
    intent = Intent("page.view", "wiki/home", {})
    result = control.check(intent, {})
    assert not result.allowed
    assert "target enforcement divergence" in result.reason
    assert "target mutated 1 record" in result.reason
