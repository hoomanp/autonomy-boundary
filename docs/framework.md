# The Autonomy Boundary Framework

**Eight controls that make agent autonomy auditable.**

## The problem

Every AI adoption roadmap moves through the same four layers. First the model assists: chat, Q&A, search. Then it augments: a copilot drafts and a human acts. Then it acts: an agent executes and a human approves. Eventually it runs autonomously within defined bounds.

One threshold on that path changes the engineering problem entirely: the point where the model stops suggesting and starts acting. Below that threshold, a bad output costs an edit. Above it, a bad action touches records, money, and infrastructure. That threshold is the **autonomy boundary**, and most organizations cross it relying on controls they have never verified.

The framework treats the boundary as an engineering surface with three phases: what must hold **before** an agent acts, what must hold **at the moment** of acting, and what must hold **after and continuously**.

## The eight controls

### Before acting

**1. Scope.** The agent may act only on resources inside its declared scope. Scope is declared in policy, not inferred from behavior, and is checked against the **post-resolution** target the intent binds — not against the display path, and not against what the agent says it is doing. `acct/../payroll/secret` is `payroll/secret`.

**2. Authority.** Every action must appear on an explicit allowlist, and the intent describing it must carry a valid signature. The intent's capability set must sit inside the policy envelope; subprocesses inherit a parent envelope they cannot grow. A task carries a cumulative authority budget shared across sequential and parallel chains — the caller accumulates spend, the control refuses when the budget is exhausted. No allowlist entry means no authority; an unsigned or tampered intent is denied regardless of content.

**3. Input Integrity.** Parameters that originated in untrusted context — user messages, retrieved documents, tool outputs, repository files — are screened before they can shape an action. Injection patterns, traversal sequences, and control characters are denials. This control does not make untrusted input trusted; it prevents the most direct paths by which untrusted input becomes an executed action.

### At the boundary

**4. Reversibility.** Actions are classified by whether they can be undone. Reversible actions may proceed under the other controls alone; irreversible actions — payments, deletions, external communications, configuration changes — require a human approval token. The classification is policy, reviewed like policy, not left to the agent's judgment.

**5. Legibility.** *Approved must equal authorized.* The action a human approves and the action an executor runs must be one signed representation of the **post-resolution semantic effect**: canonical resolved target (symlinks followed, paths normalized, env and aliases expanded), effective identity, capability set, data boundary, and expiry. The approval surface renders directly from that object; the approval token binds its hash. The check runs at the **last enforcement point after resolution**, immediately before effect. The executor recomputes the hash and compares execution-time resolution to the bound effect. Either mismatch fails closed.

This is the control that existing frameworks leave unnamed, and it is the control the TrustFall and SymJack disclosures (Adversa AI, May–June 2026) exploited: across six major coding agents, the approval dialog could show one action while the system executed another. The failure is architectural — two separately maintained representations of the same action will eventually drift — and the remedy is structural, not behavioral: one representation, two readers, equality asserted in code.

**6. State Admissibility.** The approval can be valid, the grant live, and the hashes matched, and the action can still be wrong because the state that made it eligible has gone stale — or because a required dependency was never bound. The intent carries a hash of each **policy-declared** decision-critical dependency, plus a validity window. The agent may add dependencies; it may not silently omit the minimum set. At execution the enforcement point re-hashes current state. For high-risk actions, an unexpired window and a matching state check are **separate** conditions, not substitutes. A matching hash proves the snapshot is unchanged; it does **not** prove the original state was sound.

### After acting, and continuously

**7. Observability.** Every decision the boundary makes is recorded as it happens — intent, control results, outcome — not reconstructed afterward from application logs. An auditor should be able to answer "what did the agent do and why was it allowed" from the boundary's own records. A check at the moment of action that produces no record did not happen.

**8. Provability.** The record itself must be trustworthy. The ledger is append-only and hash-chained: each record embeds the hash of its predecessor, so modification anywhere breaks verification everywhere after it. The boundary verifies the chain before new actions land on top of it; a broken chain halts execution.

A record only counts if three facts are bound together **at the moment of action**, somewhere the agent cannot rewrite: **what was approved** (the intent hash the human bound), **what was actually in force** (the live grant — envelope, remaining budget, expiry), and **which instance of the agent acted**. Skip any of the three, and the proof is a report written by the thing under investigation.

Observability produces that record; Provability holds it in a **different trust domain** from both the agent runtime and the enforcement point. The enforcement point is the only component that sees the full binding at the moment of action, so it must emit the evidence — and must not be the custodian. In the reference, instance identity is a signed software assertion. A hardware root of trust (TEE, silicon identity) is the production upgrade that makes the instance claim unforgeable; it is not a property of this kernel.

### Context, memory, and KV cache

These are not a ninth control. Provider prompt caches, conversation checkpointers, and application memory stores are **inputs and effects** the eight controls already govern.

A retrieved chunk, a session note, or a warm cache prefix is an input: Input Integrity screens it before it can shape an action, and State Admissibility re-hashes decision-critical memory (including a `memory_fingerprint`) before a high-risk effect. A memory write, a KV put, or reuse of a `session_id` is an effect: Scope names what it may touch, Authority allowlists the verb and spends `chain_budget`, Reversibility classifies it, Legibility binds the signed intent, Observability records cache hits (`cached_tokens`, `cache_discount`), and Provability binds the session as the software instance claim.

Implicit provider KV cache is not application data retention. OpenRouter's zero-data-retention stance applies to that cache; ABF still treats **application** memory and KV as governed state. A harness such as LangChain or `callModel` may propose the write. The boundary still authorizes it. Optional wrappers live under [`examples/harnesses/`](../examples/harnesses/).

## Accountability

The boundary's placement is a leadership decision, not a model property. Which actions are irreversible, what falls in scope, what appears on the allowlist, which dependencies an action class must bind — these are choices a named owner makes and reviews, and the framework's records exist so that owner can defend them in an audit. An agent operating without a defined boundary is not autonomous; it is unowned.

## What this framework does not cover

ABF governs the action boundary of deployed agents. It deliberately excludes model alignment, training-data governance, and full supply-chain assurance. Those are real problems with their own controls; claiming them here would dilute the controls this framework can actually enforce.

Honest remaining limits, accepted from issues [#1](https://github.com/hoomanp/autonomy-boundary/issues/1), [#2](https://github.com/hoomanp/autonomy-boundary/issues/2), and [#3](https://github.com/hoomanp/autonomy-boundary/issues/3):

- **Original-state soundness.** State Admissibility detects post-approval drift of the bound dependency set. A matching hash cannot prove the snapshot was complete or uncontaminated at approval time.
- **Resolution coverage.** The reference canonicalizer covers env expansion, aliases, POSIX normalize, and symlink follow. Network-layer redirects and container path mapping are out of coverage.
- **Instance identity and ledger custody.** The teaching kernel records instance identity as a signed software claim and still co-locates the ledger with the enforcement point. Hardware attestation, and a ledger in a different trust domain, are the production bar — not a claim this repository currently satisfies.

## Reference implementation

This repository implements all eight controls as composable guards with working demonstrations of Legibility binding, State Admissibility, a hash-chained ledger, and an adversarial coverage suite. See the [README](../README.md) for the quickstart.
