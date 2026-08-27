"""State Admissibility (control #8): the world behind an approval still governs."""
from datetime import datetime, timezone

from abf.controls.state_admissibility import StateAdmissibilityControl
from abf.intent import Intent, snapshot_state

FROZEN = datetime(2026, 8, 26, 21, 0, tzinfo=timezone.utc)
WINDOW = "2026-08-26T23:00:00+00:00"


def _control(**kwargs):
    return StateAdmissibilityControl(
        required_deps={"refund.issue": ["account_status", "refund_policy"]},
        high_risk_actions=["refund.issue"],
        clock=lambda: FROZEN,
        **kwargs,
    )


def _intent(deps, window=WINDOW):
    return Intent(
        "refund.issue",
        "acct/1",
        {"amount": 250.0},
        state_deps=deps,
        validity_window=window,
    )


def test_matching_state_and_live_window_allows():
    deps = snapshot_state({"account_status": "active", "refund_policy": "v3"})
    result = _control().check(_intent(deps), {"current_state": deps})
    assert result.allowed


def test_stale_state_fails_closed():
    bound = snapshot_state({"account_status": "active", "refund_policy": "v3"})
    current = snapshot_state({"account_status": "frozen", "refund_policy": "v3"})
    result = _control().check(_intent(bound), {"current_state": current})
    assert not result.allowed
    assert "state changed" in result.reason


def test_agent_cannot_omit_policy_required_deps():
    deps = snapshot_state({"account_status": "active"})  # refund_policy missing
    result = _control().check(_intent(deps), {"current_state": deps})
    assert not result.allowed
    assert "omitted" in result.reason


def test_agent_may_add_extra_deps():
    deps = snapshot_state(
        {"account_status": "active", "refund_policy": "v3", "channel": "web"}
    )
    result = _control().check(_intent(deps), {"current_state": deps})
    assert result.allowed


def test_high_risk_window_is_not_a_substitute_for_state_check():
    deps = snapshot_state({"account_status": "active", "refund_policy": "v3"})
    result = _control().check(_intent(deps), {})  # window still live, no current_state
    assert not result.allowed
    assert "current state" in result.reason


def test_high_risk_expired_window_fails_even_when_state_matches():
    deps = snapshot_state({"account_status": "active", "refund_policy": "v3"})
    result = _control().check(
        _intent(deps, window="2026-08-26T20:00:00+00:00"),
        {"current_state": deps},
    )
    assert not result.allowed
    assert "validity window" in result.reason


def test_matching_hash_does_not_claim_original_state_was_sound():
    # Honesty constraint: contamination already present at approval rides
    # through a matching hash. The control records that limit in the reason.
    poisoned = snapshot_state({"account_status": "injected", "refund_policy": "v3"})
    result = _control().check(_intent(poisoned), {"current_state": poisoned})
    assert result.allowed
    assert "unchanged" in result.reason
