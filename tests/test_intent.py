import os

from abf.intent import Intent, canonical_hash


def test_canonical_hash_is_order_independent():
    a = canonical_hash({"x": 1, "y": 2})
    b = canonical_hash({"y": 2, "x": 1})
    assert a == b


def test_signature_roundtrip():
    key = os.urandom(32)
    intent = Intent("ticket.close", "ticket/77", {}).sign(key)
    assert intent.verify_signature(key)
    assert not intent.verify_signature(os.urandom(32))


def test_param_change_changes_hash():
    a = Intent("refund.issue", "acct/1", {"amount": 250.0}, intent_id="fixed")
    b = Intent("refund.issue", "acct/1", {"amount": 25000.0}, intent_id="fixed")
    assert a.hash != b.hash
