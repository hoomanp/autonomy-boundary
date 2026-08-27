import os

from abf.intent import Intent, canonical_hash, canonicalize_target, snapshot_state


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


def test_resolved_target_is_bound_into_the_hash():
    a = Intent("read_files", "docs", {}, intent_id="fixed", resolved_target="/tmp/a")
    b = Intent("read_files", "docs", {}, intent_id="fixed", resolved_target="/tmp/b")
    assert a.hash != b.hash


def test_state_deps_are_bound_into_the_hash():
    a = Intent("refund.issue", "acct/1", {}, intent_id="fixed", state_deps={"k": "1"})
    b = Intent("refund.issue", "acct/1", {}, intent_id="fixed", state_deps={"k": "2"})
    assert a.hash != b.hash


def test_effect_target_defaults_to_resource():
    intent = Intent("refund.issue", "acct/1", {})
    assert intent.effect_target == "acct/1"


def test_snapshot_state_is_stable():
    assert snapshot_state({"a": 1, "b": "x"}) == snapshot_state({"b": "x", "a": 1})


def test_canonicalize_target_exported():
    assert canonicalize_target("acct/./1") == "acct/1"
