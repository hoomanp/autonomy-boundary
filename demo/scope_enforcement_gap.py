#!/usr/bin/env python3
"""
Declared scope vs. enforced scope — the Scope control, runnable.

    A boundary you define is not a boundary the target agreed to.

A harness declares its own scope ("read-only") and classifies each request
against that declaration. The target system has its own permission model,
written by someone else, and it decides what a request actually does. When
the two disagree, the harness reports a clean read-only run while the
target records writes.

This is the failure class behind the September 2026 OpenAI DSEWiki
incident: an agent operating under a read-only scope produced roughly
18,000 discussion posts, because the endpoint it classified as a read
materialised a post on every visit. Nothing in the harness was violated.
The harness was measuring its own labels.

The fix is not a better label. It is to stop trusting the classification
and measure the target: probe first against a canary resource, compare the
target's state fingerprint before and after, and treat any change under a
read-only scope as a halt — not a warning.

Run:
    python3 demo/scope_enforcement_gap.py              # target enforces read-only → both harnesses agree
    python3 demo/scope_enforcement_gap.py --divergent  # target does not → naive writes 18,000, verified fails closed
    python3 demo/scope_enforcement_gap.py --divergent --batch 50

No dependencies. Python 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import json

READ_ENDPOINTS = ("view",)
CANARY = "Sandbox:AutonomyBoundaryCanary"


class WikiTarget:
    """The target system. Its permission model is its own — the harness does
    not get to define it, and does not get to assume it.

    In the divergent configuration the `view` endpoint has a side effect the
    harness never declared: visiting a page materialises a discussion stub.
    """

    def __init__(self, enforces_read_only: bool = True):
        self.enforces_read_only = enforces_read_only
        self.posts: dict[str, str] = {}
        self._seq = 0

    def fingerprint(self) -> str:
        payload = json.dumps(self.posts, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    def _post(self, resource: str, agent: str) -> None:
        self._seq += 1
        self.posts[f"{resource}#{self._seq}"] = agent

    def handle(self, request: dict) -> dict:
        endpoint = request["endpoint"]
        resource = request["resource"]
        agent = request.get("agent", "agent:unknown")
        if endpoint == "view":
            if not self.enforces_read_only:
                self._post(resource, agent)
            return {"body": f"contents of {resource}"}
        if endpoint == "edit":
            self._post(resource, agent)
            return {"body": f"saved {resource}"}
        raise ValueError(f"unknown endpoint: {endpoint}")


class Run:
    """What a harness believes happened, and what the target recorded."""

    def __init__(self, performed=None, refused=None, halted=False, reason=""):
        self.performed = performed or []
        self.refused = refused or []
        self.halted = halted
        self.reason = reason

    def __repr__(self) -> str:
        return (f"Run(performed={len(self.performed)}, refused={len(self.refused)}, "
                f"halted={self.halted}, reason={self.reason!r})")


class NaiveHarness:
    """Trusts its own request-type labels. This is the failure mode.

    Note what it gets right: it refuses every request it classifies as a
    write. Its enforcement of its own declared scope is correct and complete.
    It is simply enforcing a boundary the target never agreed to.
    """

    scope = "read-only"

    def __init__(self, target: WikiTarget, agent: str = "agent:wiki-reader"):
        self.target = target
        self.agent = agent

    def run(self, requests) -> Run:
        result = Run()
        for request in requests:
            if request["endpoint"] not in READ_ENDPOINTS:
                result.refused.append(request)
                continue
            self.target.handle({**request, "agent": self.agent})
            result.performed.append(request)
        return result


class VerifiedHarness:
    """Probes the target before acting, then checks real state change rather
    than declared intent. This is the fix.

    Two checks, both about the target and neither about the label:

    1. Probe. Before using an endpoint class for the first time, exercise it
       against a canary resource and compare state fingerprints. If the
       target mutates on what the harness calls a read, the declared scope is
       not enforced there and the harness refuses the class outright. The
       probe costs at most one write, against a named, disposable resource.
       Not probing cost 18,000, against real ones.

    2. Per-action verification. Fingerprint before and after every action. A
       change under a read-only scope halts the run — the probe verdict is
       evidence, not a standing permission.
    """

    scope = "read-only"

    def __init__(self, target: WikiTarget, agent: str = "agent:wiki-reader",
                 canary: str = CANARY):
        self.target = target
        self.agent = agent
        self.canary = canary
        self.probe_results: dict[str, bool] = {}

    def probe(self, endpoint: str) -> bool:
        """True if the target actually enforces read-only on this endpoint."""
        if endpoint in self.probe_results:
            return self.probe_results[endpoint]
        before = self.target.fingerprint()
        self.target.handle({"endpoint": endpoint, "resource": self.canary,
                            "agent": self.agent})
        enforced = self.target.fingerprint() == before
        self.probe_results[endpoint] = enforced
        return enforced

    def run(self, requests) -> Run:
        result = Run()
        for request in requests:
            endpoint = request["endpoint"]
            if endpoint not in READ_ENDPOINTS:
                result.refused.append(request)
                continue
            if not self.probe(endpoint):
                result.halted = True
                result.reason = (f"target does not enforce {self.scope!r} on "
                                 f"endpoint {endpoint!r}; declared scope and "
                                 f"enforced scope diverge")
                return result
            before = self.target.fingerprint()
            self.target.handle({**request, "agent": self.agent})
            if self.target.fingerprint() != before:
                result.halted = True
                result.reason = (f"target state changed during a {self.scope!r} "
                                 f"action on {request['resource']!r}")
                return result
            result.performed.append(request)
        return result


def _report(label: str, harness, requests, target: WikiTarget) -> Run:
    print(f"[{label:8}]  declared scope: {harness.scope}; {len(requests)} requests queued")
    result = harness.run(requests)
    print(f"[{label:8}]  harness believes: {len(result.performed)} reads, "
          f"{len(result.refused)} refused, halted={result.halted}")
    if result.reason:
        print(f"[{label:8}]  {result.reason}")
    print(f"[{label:8}]  target recorded: {len(target.posts)} posts written")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--divergent", action="store_true",
                    help="target does not enforce the harness's read-only scope")
    ap.add_argument("--batch", type=int, default=18000,
                    help="number of pages the agent visits (default: 18000)")
    args = ap.parse_args()

    enforces = not args.divergent
    requests = [{"endpoint": "view", "resource": f"Talk:Page_{i}"}
                for i in range(args.batch)]
    requests.append({"endpoint": "edit", "resource": "Talk:Page_0"})

    print(f"target enforces read-only on 'view': {enforces}")
    print()

    naive_target = WikiTarget(enforces_read_only=enforces)
    naive = _report("naive", NaiveHarness(naive_target), requests, naive_target)
    print()

    verified_target = WikiTarget(enforces_read_only=enforces)
    verified = _report("verified", VerifiedHarness(verified_target), requests,
                       verified_target)
    print()

    print(f"result: naive {'BLOCKED' if naive.halted else 'EXECUTED'}, "
          f"verified {'BLOCKED' if verified.halted else 'EXECUTED'}")
    if args.divergent:
        print("\nThe naive harness refused every request it labelled a write, and")
        print(f"still produced {len(naive_target.posts)} posts — because it audited its own labels")
        print("instead of the target, then reported a clean read-only run.")
        print("The verified harness paid one canary write to learn the same fact,")
        print("and stopped before it touched a single real page.")
    else:
        print("\nDeclared scope and enforced scope agree here. The verified")
        print("harness proves that rather than assuming it — which is the only")
        print("difference between this run and the other one.")


if __name__ == "__main__":
    main()
