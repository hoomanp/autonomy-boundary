# Autonomy Boundary Framework

Reference implementation of the Autonomy Boundary Framework (ABF): seven composable controls that make agent autonomy auditable. The repository exists to demonstrate one claim in working code:

> **Approved must equal authorized.** The action a human approves and the action an executor runs must be one signed representation, verified by hash equality at execution time, failing closed on mismatch.

![Autonomy Boundary](docs/assets/autonomy_boundary.png)

## Why

In May–June 2026, Adversa AI disclosed TrustFall and SymJack: across six major coding agents, the approval dialog could show a developer one action while the system executed another. The gap is architectural, not behavioral. When the approval surface and the executor each hold their own representation of an action, the two are free to drift, and prompt-level fixes cannot close the distance.

This implementation closes it structurally. The agent emits a single signed intent. The approval dialog renders from that intent's canonical form. The executor recomputes the hash of the action it is about to run and refuses to proceed unless it matches the hash the human approved.

## The seven controls

| Phase | Control | Enforces |
|---|---|---|
| Before acting | **Scope** | the agent acts only on resources inside its declared scope |
| Before acting | **Authority** | signed intent, allowlisted action; no allowlist entry, no authority |
| Before acting | **Input Integrity** | parameters from untrusted context are screened before shaping an action |
| At the boundary | **Reversibility** | irreversible actions require a human approval token |
| At the boundary | **Legibility** | approved hash == executing hash, asserted in code, failing closed |
| Continuous | **Observability** | every decision is recorded as it happens, not reconstructed |
| Continuous | **Provability** | a hash-chained ledger that must verify before new actions land |

Each control is a small module under `src/abf/controls/`. The orchestrator (`src/abf/boundary.py`) runs them in lifecycle order; any denial or any exception halts execution.

## Quickstart

```bash
pip install -e ".[dev]"
pytest -q                              # 13 tests
python examples/refund_agent.py        # end-to-end demo incl. a blocked swap
python evals/owasp_asi_coverage.py     # adversarial scenarios -> control matrix
```

The demo approves a $250 refund, executes it, then attempts to execute a $25,000 intent against the same approval token. The Legibility control denies it: the approved hash and the executing hash differ.

## Design notes

- **One representation, two readers.** `Intent` serializes canonically (sorted keys, no whitespace drift) so its hash is stable across the approval surface and the executor.
- **Fail closed.** A control that raises is a denial. A ledger that fails chain verification halts the boundary.
- **Signatures.** The reference uses HMAC-SHA256 to keep dependencies minimal; the binding logic is identical under Ed25519, which is what a production deployment should use.
- **Tamper-evident, not tamper-proof.** The ledger detects modification by hash-chain verification; protecting the file itself is a deployment concern.

## Scope

ABF governs the action boundary of deployed agents. It deliberately does not address model alignment, training-data governance, or supply-chain assurance; those are separate problems with separate controls.

## License

MIT © 2026 Hooman Parta
