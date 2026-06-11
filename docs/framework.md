# The Autonomy Boundary Framework

**Seven controls that make agent autonomy auditable.**

## The problem

Every AI adoption roadmap moves through the same four layers. First the model assists: chat, Q&A, search. Then it augments: a copilot drafts and a human acts. Then it acts: an agent executes and a human approves. Eventually it runs autonomously within defined bounds.

One threshold on that path changes the engineering problem entirely: the point where the model stops suggesting and starts acting. Below that threshold, a bad output costs an edit. Above it, a bad action touches records, money, and infrastructure. That threshold is the **autonomy boundary**, and most organizations cross it relying on controls they have never verified.

The framework treats the boundary as an engineering surface with three phases: what must hold **before** an agent acts, what must hold **at the moment** of acting, and what must hold **after and continuously**.

## The seven controls

### Before acting

**1. Scope.** The agent may act only on resources inside its declared scope. Scope is declared in policy, not inferred from behavior, and is checked against the resource the intent names — not against what the agent says it is doing.

**2. Authority.** Every action must appear on an explicit allowlist, and the intent describing it must carry a valid signature. No allowlist entry means no authority; an unsigned or tampered intent is denied regardless of content. Authority answers "is this agent permitted to do this kind of thing at all," before any question of this particular instance.

**3. Input Integrity.** Parameters that originated in untrusted context — user messages, retrieved documents, tool outputs, repository files — are screened before they can shape an action. Injection patterns, traversal sequences, and control characters are denials. This control does not make untrusted input trusted; it prevents the most direct paths by which untrusted input becomes an executed action.

### At the boundary

**4. Reversibility.** Actions are classified by whether they can be undone. Reversible actions may proceed under the other controls alone; irreversible actions — payments, deletions, external communications, configuration changes — require a human approval token. The classification is policy, reviewed like policy, not left to the agent's judgment.

**5. Legibility.** *Approved must equal authorized.* The action a human approves and the action an executor runs must be one signed representation. The approval surface renders directly from the canonical intent; the approval token binds that intent's hash; the executor recomputes the hash of the action it is about to take and refuses to proceed unless the hashes match. A mismatch fails closed.

This is the control that existing frameworks leave unnamed, and it is the control the TrustFall and SymJack disclosures (Adversa AI, May–June 2026) exploited: across six major coding agents, the approval dialog could show one action while the system executed another. The failure is architectural — two separately maintained representations of the same action will eventually drift — and the remedy is structural, not behavioral: one representation, two readers, equality asserted in code.

### After acting, and continuously

**6. Observability.** Every decision the boundary makes is recorded as it happens — intent, control results, outcome — not reconstructed afterward from application logs. An auditor should be able to answer "what did the agent do and why was it allowed" from the boundary's own records.

**7. Provability.** The record itself must be trustworthy. The ledger is append-only and hash-chained: each record embeds the hash of its predecessor, so modification anywhere breaks verification everywhere after it. The boundary verifies the chain before new actions land on top of it; a broken chain halts execution.

## Accountability

The boundary's placement is a leadership decision, not a model property. Which actions are irreversible, what falls in scope, what appears on the allowlist — these are choices a named owner makes and reviews, and the framework's records exist so that owner can defend them in an audit. An agent operating without a defined boundary is not autonomous; it is unowned.

## What this framework does not cover

ABF governs the action boundary of deployed agents. It deliberately excludes model alignment, training-data governance, and full supply-chain assurance. Those are real problems with their own controls; claiming them here would dilute the controls this framework can actually enforce.

## Reference implementation

This repository implements all seven controls as composable guards with a working demonstration of the Legibility binding, a hash-chained ledger, and an adversarial coverage suite. See the [README](../README.md) for the quickstart.
