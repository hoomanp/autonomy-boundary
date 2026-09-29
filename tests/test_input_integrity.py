from abf.controls.input_integrity import InputIntegrityControl
from abf.intent import Intent


def test_input_integrity_detects_traversal_in_resource():
    control = InputIntegrityControl()
    intent = Intent("file.read", "../../../etc/passwd", {})
    result = control.check(intent, {})
    assert not result.allowed
    assert "suspect pattern in parameters or target" in result.reason


def test_input_integrity_with_custom_validator():
    def positive_amount_validator(intent, ctx):
        amount = intent.params.get("amount", 0)
        if amount <= 0 or amount > 1000:
            return False, "amount must be between 0 and 1000"
        return True, "valid amount"

    control = InputIntegrityControl(validators=[positive_amount_validator])
    valid_intent = Intent("refund.issue", "acct/1", {"amount": 250})
    invalid_intent = Intent("refund.issue", "acct/1", {"amount": 25000})

    assert control.check(valid_intent, {}).allowed
    result = control.check(invalid_intent, {})
    assert not result.allowed
    assert "amount must be between 0 and 1000" in result.reason


def test_input_integrity_validator_fails_closed_on_exception():
    def exploding_validator(intent, ctx):
        raise RuntimeError("schema engine failure")

    control = InputIntegrityControl(validators=[exploding_validator])
    intent = Intent("refund.issue", "acct/1", {"amount": 50})
    result = control.check(intent, {})
    assert not result.allowed
    assert "validator raised exception" in result.reason
