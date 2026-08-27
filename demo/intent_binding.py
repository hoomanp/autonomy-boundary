#!/usr/bin/env python3
"""
Intent binding — the Legibility control, runnable.

    Approved must equal authorized.

The approval binds a canonical hash of the post-resolution semantic effect
(resolved target, identity, capabilities, data boundary, expiry). At the
last enforcement point after resolution, immediately before effect, the
executor recomputes the hash and compares execution-time resolution to the
bound target. Either mismatch fails closed.

Run:
    python3 demo/intent_binding.py            # legitimate action: hashes match, executes
    python3 demo/intent_binding.py --attack   # runtime swaps the action: fails closed
    python3 demo/intent_binding.py --resolve  # path resolved somewhere else after approval: fails closed

No dependencies. Python 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import json


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def intent_hash(action: dict) -> str:
    return hashlib.sha256(canonical(action)).hexdigest()


def approve(action: dict, approver: str) -> dict:
    """The approval screen. The human sees the post-resolution effect —
    and the approval token binds to a hash of exactly that object."""
    h = intent_hash(action)
    print(f"[approval]  {approver} approves: {json.dumps(action)}")
    print(f"[approval]  bound intent hash: {h[:16]}…")
    return {"intent_hash": h, "approver": approver}


def execute(action: dict, approval: dict, runtime_resolved: str | None = None) -> bool:
    """Last enforcement point after resolution. Hash must match, and the
    path the runtime actually resolved must match the bound target."""
    h = intent_hash(action)
    print(f"[execute ]  runtime wants to perform: {json.dumps(action)}")
    print(f"[execute ]  recomputed hash: {h[:16]}…")
    if h != approval["intent_hash"]:
        print("[execute ]  MISMATCH — approved != authorized. FAILING CLOSED.")
        return False
    bound = action["resolved_target"]
    actual = runtime_resolved if runtime_resolved is not None else bound
    print(f"[execute ]  bound target: {bound}")
    print(f"[execute ]  resolved now: {actual}")
    if actual != bound:
        print("[execute ]  RESOLUTION DIVERGED — approval-time != execution-time. FAILING CLOSED.")
        return False
    print("[execute ]  match — executing.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attack", action="store_true",
                    help="runtime substitutes a broader action after approval")
    ap.add_argument("--resolve", action="store_true",
                    help="runtime resolves the path somewhere else after approval")
    args = ap.parse_args()

    shown = {
        "action": "read_files",
        "resource": "/home/user/project/docs",
        "resolved_target": "/home/user/project/docs",
        "effective_identity": "agent:docs-reader",
        "capabilities": ["read"],
        "data_boundary": "/home/user/project/docs",
        "expiry": "2026-08-26T23:00:00Z",
    }
    approval = approve(shown, approver="human:hp")
    print()

    runtime_resolved = None
    if args.attack:
        attempted = {
            "action": "execute_code",
            "resource": "/",
            "resolved_target": "/",
            "effective_identity": "agent:docs-reader",
            "capabilities": ["read", "write", "exec"],
            "data_boundary": "/",
            "expiry": "2026-08-26T23:00:00Z",
        }
    elif args.resolve:
        attempted = shown
        runtime_resolved = "/etc/passwd"
    else:
        attempted = shown

    ok = execute(attempted, approval, runtime_resolved)
    print(f"\nresult: {'EXECUTED' if ok else 'BLOCKED'}")
    if args.attack and not ok:
        print("\nThe approval was for one object; the runtime attempted another.")
        print("Without the binding, this executes and the audit log dutifully")
        print("records a lie. With it, the gap is uninhabitable.")
    if args.resolve and not ok:
        print("\nThe hash still matched. The folder the runtime resolved did not.")
        print("That is the TOCTOU / SymJack remainder: bind the effect, then")
        print("re-check resolution at the last point before it happens.")


if __name__ == "__main__":
    main()
