#!/usr/bin/env python3
"""
Tamper-evident decision ledger — the Provability control, runnable.

Every entry commits to the hash of the previous entry plus a canonical
serialization of the full decision context. Altering any past entry breaks
every hash downstream: tampering is mathematically visible.

Run:
    python3 demo/ledger.py            # happy path: append, verify
    python3 demo/ledger.py --tamper   # edit a past entry, watch the chain break

No dependencies. Python 3.9+.
"""
import argparse
import hashlib
import json
import time

GENESIS = "0" * 64


def canonical(obj: dict) -> bytes:
    """Deterministic serialization — same dict, same bytes, always."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def entry_hash(prev_hash: str, record: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode())
    h.update(canonical(record))
    return h.hexdigest()


class Ledger:
    """Append-only, hash-chained. In production: WORM storage + external
    anchoring (RFC 3161 timestamps / transparency log) so the operator
    can't rewrite history either. See docs/THREAT_MODEL.md."""

    def __init__(self):
        self.entries: list[dict] = []

    def append(self, record: dict) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        entry = {
            "seq": len(self.entries),
            "ts": record.get("ts", time.time()),
            "record": record,
            "prev": prev,
        }
        entry["hash"] = entry_hash(prev, entry["record"])
        self.entries.append(entry)
        return entry

    def verify(self) -> tuple[bool, int]:
        """Returns (ok, first_bad_seq). Recomputes every link."""
        prev = GENESIS
        for e in self.entries:
            if e["prev"] != prev:
                return False, e["seq"]
            if entry_hash(prev, e["record"]) != e["hash"]:
                return False, e["seq"]
            prev = e["hash"]
        return True, -1


def demo_actions(ledger: Ledger):
    """Append a realistic sequence of agent decisions."""
    actions = [
        {"agent": "billing-agent", "action": "read_invoice", "target": "inv-1042",
         "approved_by": "policy:auto", "outcome": "ok"},
        {"agent": "billing-agent", "action": "issue_refund", "target": "inv-1042",
         "amount": 129.00, "approved_by": "human:kperez", "outcome": "ok"},
        {"agent": "billing-agent", "action": "update_limit", "target": "acct-77",
         "approved_by": "human:kperez", "outcome": "denied:over-authority"},
    ]
    for a in actions:
        e = ledger.append(a)
        print(f"  appended seq={e['seq']}  {a['action']:>13}  hash={e['hash'][:16]}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tamper", action="store_true",
                    help="alter a past entry after the fact, then re-verify")
    args = ap.parse_args()

    ledger = Ledger()
    print("Appending decision records:")
    demo_actions(ledger)

    ok, bad = ledger.verify()
    print(f"\nVerify chain: {'INTACT' if ok else f'BROKEN at seq {bad}'}")

    if args.tamper:
        print("\nTampering: changing the refund amount in seq 1 from 129.00 to 29.00 …")
        ledger.entries[1]["record"]["amount"] = 29.00
        ok, bad = ledger.verify()
        print(f"Verify chain: {'INTACT' if ok else f'BROKEN at seq {bad}'}")
        print("\nThe edit is visible. The log isn't trustworthy because it's stored")
        print("safely — it's trustworthy because tampering breaks the chain.")


if __name__ == "__main__":
    main()
