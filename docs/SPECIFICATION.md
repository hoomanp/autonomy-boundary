# The Autonomy Boundary Specification (ABF-RFC-01)

**A Formal Specification for Auditable AI Agent Autonomy Boundaries**

---

## 1. Overview

The **Autonomy Boundary Framework (ABF)** defines the protocol and data structures for a deterministic **Policy Enforcement Point (PEP)** that mediates between autonomous agent runtimes (LLMs, harnesses, orchestrators) and real-world execution systems (APIs, databases, tools, cloud infrastructure).

The framework enforces eight controls structured across three lifecycle phases:
1. **Pre-Execution**: Scope, Authority, Input Integrity.
2. **At the Boundary**: Reversibility, Legibility (Semantic Binding), State Admissibility.
3. **Continuous Non-Repudiation**: Observability, Provability (Tamper-Evident Ledger).

---

## 2. Canonical Data Formats

### 2.1 The Intent Object

An `Intent` represents an immutable proposal for an agent action. To guarantee that hashes match across distributed systems, all hashing operates on the **canonical JSON serialization**:
* Deterministic sorting of dictionary keys (`sort_keys=True`).
* Compact separators with no extraneous whitespace (`,` and `:`).
* UTF-8 byte encoding.
* Hash algorithm: SHA-256 (`canonical_hash`).

```json
{
  "action": "refund.issue",
  "resource": "acct/8841",
  "params": {
    "amount": 250.00
  },
  "intent_id": "054633aa344a",
  "resolved_target": "acct/8841",
  "effective_identity": "agent:refund",
  "capabilities": [
    "refund"
  ],
  "data_boundary": "acct/8841",
  "expiry": "2099-01-01T00:00:00+00:00",
  "state_deps": {
    "account_status": "4daa3ed4d3b92b7883f3d7a31eb68edba9cdbebbbdbdc4d8ff74a68028d1051b"
  },
  "validity_window": "2099-01-01T00:00:00+00:00"
}
```

#### Fields:
* `action` (string): Dotted action verb (e.g. `file.read`, `payment.transfer`).
* `resource` (string): Resource target as named at proposal time.
* `params` (object): Key-value parameters passed to the action.
* `intent_id` (string): Unique identifier for this action proposal.
* `resolved_target` (string): Post-resolution target (environment variables expanded, symlinks followed, POSIX path-normalized).
* `effective_identity` (string): Identity / role under which the effect executes.
* `capabilities` (list of strings): Capability tokens required to execute the action.
* `data_boundary` (string): Scope envelope of data the action is permitted to read or mutate.
* `expiry` (string): ISO 8601 timestamp after which the intent proposal is void.
* `state_deps` (map of string -> SHA256 hex string): State snapshot of decision-critical system dependencies.
* `validity_window` (string): ISO 8601 timestamp limiting the admissible lifespan of `state_deps`.

---

### 2.2 The Human Approval Token

When an action is classified as **irreversible**, execution requires an explicit human approval token bound directly to the canonical intent hash:

```json
{
  "approver": "user:hp",
  "approved_hash": "4426a086f7a7...",
  "intent_id": "054633aa344a",
  "timestamp": "2026-09-28T12:00:00Z",
  "signature": "hmac_or_asymmetric_signature_over_payload",
  "rendered": "[054633aa344a] refund.issue on acct/8841 as agent:refund caps=refund data=acct/8841 until 2099-01-01T00:00:00+00:00 with {'amount': 250.0}"
}
```

* **Legibility Rule**: At the moment of action, the enforcement point recomputes `canonical_hash(executing_intent)`. If `approved_hash != executing_hash`, the boundary **fails closed**.
* **Signature Rule**: If `key` is configured, `signature` asserts that the approver identity and approved hash have not been forged in-process.

---

### 2.3 The Proof Triple

Every boundary decision binds three non-negotiable facts at the moment of action:
$$\text{Proof Triple} = (\text{Approved Intent Hash} \times \text{In-Force Grant} \times \text{Instance Identity})$$

1. **Approved Intent Hash**: What the human authorized on screen.
2. **In-Force Grant**: What capability envelope, remaining budget, and expiry were active when the PEP evaluated the request.
3. **Instance Identity**: Which software instance, session ID, or attested hardware enclave requested the effect.

---

### 2.4 The Decision Ledger Record

Decisions are stored in an append-only, cryptographic hash-chained ledger. Any modification to a previous entry invalidates all downstream verification hashes.

```json
{
  "ts": 1790647890.12,
  "event": "boundary_decision",
  "payload": {
    "intent_hash": "4426a086f7a7...",
    "allowed": true,
    "approved_hash": "4426a086f7a7...",
    "in_force_grant": "grant_cfg_v1",
    "instance_id": "agent:refund",
    "results": [
      {"control": "scope", "allowed": true, "reason": "matches scope pattern 'acct/*'"},
      {"control": "authority", "allowed": true, "reason": "signed intent, allowlisted action"},
      {"control": "input_integrity", "allowed": true, "reason": "parameters passed integrity screen"},
      {"control": "reversibility", "allowed": true, "reason": "action carries approval"},
      {"control": "legibility", "allowed": true, "reason": "approved == authorized"},
      {"control": "state_admissibility", "allowed": true, "reason": "bound state unchanged"},
      {"control": "provability", "allowed": true, "reason": "ledger chain verified"}
    ]
  },
  "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "record_hash": "7a3f89b1c20e..."
}
```

---

## 3. Invariants & Lifecycle Guarantees

1. **Fail Closed**: Any unhandled exception, syntax error, missing key, unexpanded environment variable, or missing dependency yields an immediate denial (`allowed: false`).
2. **Deterministic & Zero-LLM**: The Policy Enforcement Point executes in under 1 millisecond using deterministic cryptographic hashing and set operations. It does not invoke non-deterministic LLM-as-a-judge evaluators in the critical path.
3. **Ledger Integrity Pre-Check**: Before evaluating any intent or appending a decision, the enforcement point verifies the complete integrity of the prior ledger chain from genesis. If corrupted, it halts immediately.
4. **Split Custody**: The enforcement point produces evidence but must not be the sole custodian of the ledger. Long-term storage must be anchored in a separate trust domain (e.g., append-only S3 bucket with Object Lock, RFC 3161 timestamping authority, or external audit log).
5. **Post-Resolution Parity**: Scope and Legibility evaluate the **canonical resolved target** (symlinks dereferenced, path traversal resolved, environment expanded), never the raw userland display string.
