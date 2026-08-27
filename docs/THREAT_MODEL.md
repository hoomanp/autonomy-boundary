# Threat Model — The Autonomy Boundary Framework

This document states what the framework defends against, the assumptions it
rests on, and — just as deliberately — what it does not solve. A control
framework that won't name its own limits shouldn't be trusted to name anyone
else's.

The reference implementation is a teaching kernel. Mechanisms described here
are **invariants the code asserts**; where the reference is narrower than a
production deployment, that is named in §5.

## 1. System under consideration

An **agentic system**: a model plus a harness (orchestration, tools, retrieval,
memory) that can take **actions with real-world effect** — reading and writing
records, moving money, sending messages, executing code — inside an enterprise
that answers to regulators, customers, or courts.

Components:

- **Approval surface** — where a human sees and approves a proposed action.
- **Enforcement point** — the broker in the request path that permits or blocks
  each tool call (the PEP, in NIST 800-207 terms).
- **Policy engine** — decides permit/deny against explicit policy (the PDP).
- **Executor / tools** — the code that performs the effect.
- **Decision ledger** — append-only, hash-chained record of every decision.

## 2. Adversaries and failure sources

| # | Source | Example |
|---|--------|---------|
| A1 | **External content attacker** | Prompt injection riding in on a document, repo, email, or web page the agent reads. |
| A2 | **Approval-gap attacker** | The TrustFall/SymJack class: engineering divergence between what the approval surface displays and what the runtime is empowered to do. |
| A3 | **Resolution-time attacker** | Symlinks, path expansion, redirects, or races that make the executed target differ from the approved target (TOCTOU). |
| A4 | **Compromised or buggy agent runtime** | The agent itself attempts actions outside its grant — malice is not required; a confused model suffices. |
| A5 | **Post-hoc record tampering** | An insider or attacker (including a compromised operator) edits history to change what "happened." |
| A6 | **Composition attacker** | Individually-approved actions chained into an aggregate effect nobody approved (confused deputy). |
| A7 | **Stale or omitted eligibility state** | The approval is valid; the world that made the action eligible has moved, or a required dependency was never bound. |

## 3. Control ↔ threat mapping

| Control | Primarily counters | Mechanism |
|---|---|---|
| Scope | A1, A4, A3 | Blast radius bounded before anything runs; checked against the **resolved** target. |
| Authority | A4, A6 | Task-scoped signed grants; capability envelope; inherited subprocess envelope; cumulative chain budget across sequential and parallel spend. |
| Input Integrity | A1 | Validation, provenance checks, injection defense on everything the agent reads. |
| Reversibility | A4 | Irreversible actions classified and gated on human sign-off; everything else undoable. |
| **Legibility** | **A2, A3** | Approval binds to a canonical hash of the **post-resolution semantic effect** (resolved target, effective identity, capability set, data boundary, expiry). Enforcement recomputes at the last point after resolution, immediately before effect. Execution-time divergence fails closed. |
| **State Admissibility** | **A7** | Policy-declared decision-critical dependencies hashed into the intent plus a validity window. High-risk actions require both a live window and a matching re-hash; neither substitutes for the other. Agent may add deps, must not omit the minimum set. |
| Observability | A4, A6 | Full decision traces: inputs, versions, choices, outcomes — enough to reconstruct, not just to count. |
| Provability | A5 | Hash-chained, append-only ledger; each entry commits to its predecessor; altering any entry breaks every link downstream. |

## 4. Trust assumptions — stated, not hidden

1. **Enforcement-point integrity at the moment of action.** If the enforcement
   point itself is fully compromised *and* can also reach the ledger with
   update/delete rights, the model collapses. Mitigation: the enforcement point
   produces evidence but does not hold it — append-only credentials into a
   ledger in a **different trust domain**. Custody is split by design.
2. **External anchoring for operator-proof history.** A ledger the operator
   runs is still the operator's report about itself. The chain root must anchor
   outside the operator's trust domain — trusted timestamp authority (RFC 3161),
   a transparency log, or a counterparty. Tamper-evidence is only meaningful to
   someone other than the operator when the anchor is.
3. **Canonicalization is correct.** Intent binding is only as strong as the
   canonical serialization and the resolution step. Bugs here are control
   bypasses; this code path deserves adversarial review above all others.
4. **Instance identity is an assertion in pure software.** "Which instance of
   the agent acted" ultimately rests on the runtime's own claim unless rooted
   in hardware attestation (e.g., TEE-based). The framework records the claim;
   hardening it is an open collaboration area.
5. **The caller reports chain spend honestly.** Authority budgets compose
   across parallel chains only if the orchestrator accumulates `task_spend`
   on a shared counter. The control cannot see siblings it was not told about.

## 5. Explicit non-goals and remaining edges

- **Model alignment, training-data governance, supply-chain assurance** — out
  of scope. Different control surface. Use the frameworks that own those.
- **Original-state soundness (issue #1, accepted as control #8).** State
  Admissibility detects post-approval drift of the bound dependency set. A
  matching hash cannot prove the snapshot was complete or uncontaminated
  *at approval time*. That is Input Integrity's job at read time, and it
  remains an honest gap when contamination predates the snapshot.
- **Resolution classes still uncovered (issue #2).** The reference
  canonicalizer covers env expansion, aliasing, POSIX normalize, and symlink
  follow. Network-layer redirects and container path mapping are not covered.
- **Availability.** Fail-closed is a safety choice with an availability cost.
  This framework chooses safety; your SLOs may require compensating design.

## 6. Design principles

1. **Fail closed.** Ambiguity at the boundary resolves to "no."
2. **Bind semantics, not strings.** Authorize what it resolved to, not what was typed.
3. **Split custody.** Whoever enforces must not also hold the proof.
4. **Anchor outside yourself.** Evidence must be checkable by someone who isn't you.
5. **Prefer boring.** Every mechanism here is deliberately auditable-by-hand.
   The boring controls are the ones that ship.
