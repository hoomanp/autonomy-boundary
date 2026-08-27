#!/usr/bin/env python3
"""
State Admissibility — control #8, runnable.

    The world behind the approval still has to deserve to govern.

Approval binds a hash of each policy-declared decision-critical dependency.
At execution the enforcement point re-hashes current state. For high-risk
actions the validity window and the state check are separate conditions:
an unexpired window is not proof the state is still true.

A matching hash proves the snapshot is unchanged. It does not prove the
original state was sound.

Run:
    python3 demo/state_admissibility.py           # bound state still current → executes
    python3 demo/state_admissibility.py --stale   # account frozen after approval → fails closed
    python3 demo/state_admissibility.py --omit    # agent drops a required dep → fails closed

No dependencies. Python 3.9+.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone

REQUIRED = ("account_status", "refund_policy")
HIGH_RISK = True
NOW = datetime(2026, 8, 26, 21, 0, tzinfo=timezone.utc)


def digest(name, value):
    payload = json.dumps({name: value}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def snapshot(values):
    return {name: digest(name, values[name]) for name in values}


def check(bound, current, window, now):
    omitted = [name for name in REQUIRED if name not in bound]
    if omitted:
        print(f"[state   ]  required dependency omitted: {omitted}. FAILING CLOSED.")
        return False
    if HIGH_RISK and now >= datetime.fromisoformat(window):
        print("[state   ]  validity window expired. FAILING CLOSED.")
        return False
    if HIGH_RISK and current is None:
        print("[state   ]  high-risk action requires current state; a live window is not a substitute.")
        return False
    changed = [name for name, h in bound.items() if current.get(name) != h]
    if changed:
        print(f"[state   ]  state changed since approval: {changed}. FAILING CLOSED.")
        return False
    print("[state   ]  bound state unchanged since approval; original soundness not claimed.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale", action="store_true",
                    help="account is frozen after approval")
    ap.add_argument("--omit", action="store_true",
                    help="agent omits a policy-required dependency")
    args = ap.parse_args()

    live = {"account_status": "active", "refund_policy": "v3"}
    bound = snapshot(live)
    if args.omit:
        bound = snapshot({"account_status": "active"})
    window = "2026-08-26T23:00:00+00:00"
    print(f"[approval]  bound deps: {json.dumps(bound, sort_keys=True)[:80]}…")
    print(f"[approval]  validity window: {window}")
    print()

    if args.stale:
        current = snapshot({"account_status": "frozen", "refund_policy": "v3"})
        print("[execute ]  account_status is now frozen")
    elif args.omit:
        current = bound
        print("[execute ]  agent presented an incomplete dependency set")
    else:
        current = bound
        print("[execute ]  current state matches the bound snapshot")

    ok = check(bound, current, window, NOW)
    print(f"\nresult: {'EXECUTED' if ok else 'BLOCKED'}")
    if args.stale and not ok:
        print("\nThe approval was still valid. The grant was still live.")
        print("The world that made the refund eligible was not.")
    if args.omit and not ok:
        print("\nPolicy names the minimum dependencies for this action class.")
        print("The agent may add to that set. It may not silently omit from it.")


if __name__ == "__main__":
    main()
