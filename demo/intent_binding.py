#!/usr/bin/env python3
"""
Intent binding — the Legibility control, runnable.

    Approved must equal authorized.

At approval time, the exact intended action is serialized canonically and
hashed; the human's approval binds to that hash. At execution time, the
enforcement point recomputes the hash of the action it is about to take
and refuses on mismatch. This is the control that closes the
TrustFall/SymJack class of failure: the screen says "trust this folder,"
the runtime tries "execute arbitrary code" — and the executor says no.

Run:
    python3 demo/intent_binding.py           # legitimate action: hashes match, executes
    python3 demo/intent_binding.py --attack  # runtime swaps the action: fails closed

No dependencies. Python 3.9+.
"""
import argparse
import hashlib
import json


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def intent_hash(action: dict) -> str:
    return hashlib.sha256(canonical(action)).hexdigest()


def approve(action: dict, approver: str) -> dict:
    """The approval screen. The human sees `action` — and the approval token
    binds to a hash of exactly that object, nothing broader."""
    h = intent_hash(action)
    print(f"[approval]  {approver} approves: {json.dumps(action)}")
    print(f"[approval]  bound intent hash: {h[:16]}…")
    return {"intent_hash": h, "approver": approver}


def execute(action: dict, approval: dict) -> bool:
    """The enforcement point. Recomputes the hash of what it is actually
    about to do. No match, no move — fails closed."""
    h = intent_hash(action)
    print(f"[execute ]  runtime wants to perform: {json.dumps(action)}")
    print(f"[execute ]  recomputed hash: {h[:16]}…")
    if h != approval["intent_hash"]:
        print("[execute ]  MISMATCH — approved != authorized. FAILING CLOSED.")
        return False
    print("[execute ]  match — executing.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attack", action="store_true",
                    help="runtime substitutes a broader action after approval")
    args = ap.parse_args()

    shown = {"action": "read_files", "scope": "/home/user/project/docs",
             "capabilities": ["read"], "expiry": "2026-07-17T12:00:00Z"}
    approval = approve(shown, approver="human:hp")
    print()

    if args.attack:
        # The TrustFall/SymJack pattern: what the screen showed and what the
        # runtime attempts have quietly diverged.
        attempted = {"action": "execute_code", "scope": "/",
                     "capabilities": ["read", "write", "exec"],
                     "expiry": "2026-07-17T12:00:00Z"}
    else:
        attempted = shown

    ok = execute(attempted, approval)
    print(f"\nresult: {'EXECUTED' if ok else 'BLOCKED'}")
    if args.attack and not ok:
        print("\nThe approval was for one object; the runtime attempted another.")
        print("Without the binding, this executes and the audit log dutifully")
        print("records a lie. With it, the gap is uninhabitable.")


if __name__ == "__main__":
    main()
