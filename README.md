# The Autonomy Boundary Framework

**Seven controls for auditable agent autonomy.**
The line where a system stops assisting and starts acting — and the proof that it stayed inside it.

> Approved must equal authorized.

AI agents don't fail like models fail. A wrong answer is an annoyance; a wrong **action** is an incident, a breach notice, or a finding. The recent TrustFall and SymJack disclosures showed the sharpest version of the problem across major coding agents: the action a human approves on screen and the action the runtime is actually empowered to take can quietly diverge. The user approves "trust this folder." The system hears "run arbitrary code." The dialog looked completely normal.

This framework defines the seven runtime controls that make agent autonomy **provable** — to an examiner, an auditor, a clinician, a court, or your own incident review.

![Autonomy Boundary](docs/assets/autonomy_boundary.png)

## Run the demos (no dependencies, Python 3.9+)

**Legibility — approved must equal authorized:**

```
python3 demo/intent_binding.py           # hashes match → executes
python3 demo/intent_binding.py --attack  # runtime swaps the action → fails closed
```

**Provability — the tamper-evident ledger:**

```
python3 demo/ledger.py            # append decisions, verify the chain
python3 demo/ledger.py --tamper   # edit a past entry → chain breaks, visibly
```

Together they demonstrate the core claim: the approval binds to a canonical hash of the exact intended action, the enforcement point re-checks it at the moment of execution, and every decision lands in a chain where tampering is mathematically visible.

## The seven controls

Organized by *when* in an action's life they apply.

**Before the agent acts**

| Control | Question it answers |
|---|---|
| **Scope** | What is it allowed to touch at all? The blast radius, defined up front. |
| **Authority** | What may it *do* within that scope? Granted per task, revoked after. Borrowed power, not a standing key. |
| **Input Integrity** | Can the thing it's acting on be trusted? The poisoned file, the hostile repo, the injected instruction — caught before it becomes an action. |

**At the boundary — the moment of crossing**

| Control | Question it answers |
|---|---|
| **Reversibility** | Can this be undone? If not, it waits for a human. Irreversible actions are a different class. |
| **Legibility** | Is what the human approved *provably identical* to what the agent is empowered to do? Checked at the moment of action; fails closed on mismatch. |

**After, and continuously**

| Control | Question it answers |
|---|---|
| **Observability** | Can you see what it did — what it saw, what it chose, and why? |
| **Provability** | Can you prove that record wasn't altered afterward? Hash-chained, append-only, anchored outside the operator's trust domain. |

Observability and Provability are deliberately **separate controls with separate custodians**: the enforcement point must *produce* the evidence (it's the only component that sees the full binding at the moment of action) but must not *hold* it — otherwise enforcement and evidence share a failure domain, and the proof is a report written by the thing under investigation.

## Reference implementation

The `demo/` scripts above are standalone and dependency-free. The full framework — all seven controls, wired into a lifecycle orchestrator that runs them in order and halts on any denial or exception — lives under `src/abf/`.

```bash
pip install -e ".[dev]"
pytest -q                              # test suite
python examples/refund_agent.py        # end-to-end demo incl. a blocked swap
python evals/owasp_asi_coverage.py     # adversarial scenarios -> control matrix
```

The refund demo approves a $250 refund, executes it, then attempts a $25,000 intent against the same approval token. The Legibility control denies it: the approved hash and the executing hash differ.

- Each control is a small module under `src/abf/controls/`.
- The orchestrator (`src/abf/boundary.py`) runs them in lifecycle order.
- `Intent` (`src/abf/intent.py`) serializes canonically so its hash is stable across the approval surface and the executor. The reference uses HMAC-SHA256 to keep dependencies minimal; the binding logic is identical under Ed25519, which is what a production deployment should use.

## What this is — and is not

This framework governs the **runtime boundary**: what an agent does when it acts, and whether you can prove it. It does **not** address model alignment, training-data governance, or full supply-chain assurance. Those matter; they are a different control surface.

Existing frameworks (OWASP Top 10 for Agentic Applications, NIST's AI agent work, CSA MAESTRO, ISO 42001, vendor security stacks) enumerate the threats and cover *authorization*. What none of them isolates as a first-class control is **consent integrity** — the guarantee that what a human approved is provably what the agent was authorized to do. That is the Legibility control, and it is the central contribution here.

## Open questions (help wanted)

The framework improved measurably in its first week public, because practitioners found the seams. The current open edges, each tracked as an issue:

1. **State admissibility** — the approval is valid, but the state that made the action *eligible* has gone stale or was contaminated upstream. Is this control #8, or an extension of Legibility's binding? (→ issue #1)
2. **Semantic binding under resolution and chaining** — defining "same action" across shell expansion, symlinks, redirects, subprocesses, and tool chains, where individually-approved actions can compose into an effect nobody approved. (→ issue #2)

If you deploy agents into regulated environments and have scars, open an issue. Disagreement with evidence is the most useful contribution.

## Documents

- [`docs/framework.md`](docs/framework.md) — the full framework write-up: lifecycle phasing, each control in depth, and what ABF deliberately excludes.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — what this defends against, what it assumes, and what it explicitly does not solve.
- `demo/` — the runnable controls.
- `src/abf/` — the full reference implementation.

## Author

**Hooman Parta** — [linkedin.com/in/hooman-parta](https://www.linkedin.com/in/hooman-parta)
25+ years securing cloud platforms at Fortune-100 scale; this framework distills that discipline for the agentic era. Companion essays: *The Autonomy Boundary* series and *The Last Mile* (deployments into finance, healthcare, retail, and government), on LinkedIn.

## License

MIT — see [`LICENSE`](LICENSE).
