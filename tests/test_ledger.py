import json

from abf.ledger import Ledger


def test_chain_verifies(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    ledger.append("a", {"n": 1})
    ledger.append("b", {"n": 2})
    assert ledger.verify_chain()


def test_tamper_breaks_chain(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger = Ledger(path)
    ledger.append("a", {"n": 1})
    ledger.append("b", {"n": 2})
    lines = path.read_text().splitlines()
    record = json.loads(lines[0])
    record["payload"]["n"] = 999
    lines[0] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")
    assert not Ledger(path).verify_chain() or not ledger.verify_chain()
