"""End-to-end demonstration of the 5 v0.4.0 architectural upgrades:

  1. JEPA World-State Energy Control (`JEPAWorldStateControl`)
  2. Cyclic Agent Graph with `BoundaryInterrupt` suspend/resume & Causal DAG
  3. Tiered Merkle LLM Memory (`GovernedMemoryStore`) & Provenance Taint Tracking
  4. Frontier Reasoning Model Harness (`FrontierModelHarness` + `ReasoningAlignmentControl`)
  5. Asymmetric Ed25519 Custody (`Ed25519Keypair`) & Concurrent Hash-Chained Ledger

Run with:
    PYTHONPATH=src python3 examples/jepa_graph_frontier_demo.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from abf import (
    AutonomyBoundary,
    BoundaryGraph,
    BoundaryInterrupt,
    Ed25519Keypair,
    FrontierModelHarness,
    GovernedMemoryStore,
    Intent,
    Ledger,
    ReasoningAlignmentControl,
    TaintLevel,
)
from abf.controls import (
    AuthorityControl,
    InputIntegrityControl,
    JEPAWorldStateControl,
    LegibilityControl,
    ObservabilityControl,
    ProvabilityControl,
    ReversibilityControl,
    ScopeControl,
    StateAdmissibilityControl,
)
from abf.controls.legibility import approve


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger_path = Path(tmp) / "v040_demo_ledger.jsonl"

        # 1. Generate separate Ed25519 keypairs for the Agent and Human Approver
        agent_keys = Ed25519Keypair.from_seed(b"agent-ed25519-private-seed-00001")
        human_keys = Ed25519Keypair.from_seed(b"human-ed25519-private-seed-00002")

        # 2. Initialize 3-Tier Governed Memory Store (Procedural, Semantic Merkle, Episodic Taint)
        memory = GovernedMemoryStore()
        memory.set_procedural("refund_policy", "Max $500 per account; require human sign-off.")
        memory.put_semantic("customer:acct_42:tier", "gold")
        memory.put_semantic("customer:acct_42:eligible", True)

        merkle_root = memory.merkle_root()
        inclusion_proof = memory.prove_key("customer:acct_42:eligible")
        assert inclusion_proof.verify(merkle_root)
        print(f"[1] Semantic KV Merkle Root: {merkle_root[:16]}... (O(log N) proof verified)")

        # 3. Assemble the Autonomy Boundary with JEPA, Ed25519, Taint, and Reasoning controls
        ledger = Ledger(ledger_path)
        jepa = JEPAWorldStateControl(energy_threshold=0.55)
        boundary = AutonomyBoundary(
            controls=[
                ScopeControl(["customer:*", "db:*"]),
                AuthorityControl(
                    ["ticket.read", "refund.issue", "db.delete"],
                    public_key=agent_keys.public_key,
                ),
                InputIntegrityControl(custom_validators=[memory.make_taint_validator()]),
                ReversibilityControl(reversible_actions=["ticket.read"]),
                LegibilityControl(approver_public_key=human_keys.public_key),
                StateAdmissibilityControl(),
                JEPAWorldStateControl(energy_threshold=0.55),
                ReasoningAlignmentControl(require_reasoning_hash=True),
                ObservabilityControl(ledger),
                ProvabilityControl(ledger),
            ],
            ledger=ledger,
        )

        # 4. Wrap in FrontierModelHarness + BoundaryGraph
        harness = FrontierModelHarness(boundary, private_key=agent_keys.private_key)
        graph = BoundaryGraph(
            boundary,
            private_key=agent_keys.private_key,
            chain_budget=6,
            max_steps=15,
        )

        state_snap = memory.snapshot_keys(["customer:acct_42:tier", "customer:acct_42:eligible"])
        world_state = {"cumulative_spend": 50.0, "budget_limit": 1000.0, "affected_resources": 1}

        # 5. Step 1: Reversible read bound to Claude Extended Thinking trace
        claude_thinking = {
            "provider": "anthropic_claude_4",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Read ticket #88 for customer:acct_42 to verify eligibility.",
                    "signature": "anth_sig_01",
                }
            ],
        }
        read_intent = harness.bind_reasoning(
            Intent("ticket.read", "customer:acct_42", {"ticket_id": 88}, state_deps=state_snap),
            claude_thinking,
        )
        d1, out1 = graph.step(
            read_intent,
            {"current_state": state_snap, "world_state": world_state},
            node_name="inspect_ticket",
            executor_fn=lambda i: {"status": "open", "requested_refund": 150.0},
        )
        print(f"[2] Step 1 (ticket.read) Allowed={d1.allowed} -> {out1}")

        # 6. Step 2: Irreversible refund triggers BoundaryInterrupt (no rubber-stamping!)
        refund_intent = harness.bind_reasoning(
            Intent("refund.issue", "customer:acct_42", {"amount": 150.0}, state_deps=state_snap),
            claude_thinking,
        )
        try:
            graph.step(
                refund_intent,
                {"current_state": state_snap, "world_state": world_state},
                node_name="issue_refund",
                executor_fn=lambda i: f"Refunded ${i.params['amount']} to {i.effect_target}",
            )
        except BoundaryInterrupt as interrupt:
            print(f"[3] Caught BoundaryInterrupt ({interrupt.checkpoint_id}):")
            print(f"    Prompt shown to human: {interrupt.rendered_prompt}")
            # External human signs approval with their Ed25519 private key
            human_token = approve(
                interrupt.intent,
                "alice@security",
                private_key=human_keys.private_key,
                timestamp="2026-10-18T21:00:00Z",
            )
            d2, out2 = graph.resume(interrupt.checkpoint_id, approval=human_token)
            print(f"[4] Resumed Checkpoint with Ed25519 Human Approval -> Allowed={d2.allowed}: {out2}")

        # 7. Step 3: JEPA World-State Energy Gate blocks catastrophic wildcard deletion
        bad_intent = harness.bind_reasoning(
            Intent(
                "db.delete",
                "db:prod/*",
                {"recursive": True, "count": 500},
                state_deps=state_snap,
            ),
            claude_thinking,
        )
        pred = jepa.predict(bad_intent, world_state)
        print(
            f"[5] JEPA Prediction for 'db.delete db:prod/*': "
            f"Energy={pred.total_energy:.3f} (Threshold={pred.threshold}) "
            f"Violated={list(pred.violated_dimensions)} -> Admissible={pred.admissible}"
        )
        assert not pred.admissible
        assert boundary.ledger.verify_chain()
        print(f"[6] Ledger chain verified ({len(list(boundary.ledger.read()))} cryptographically linked events).")


if __name__ == "__main__":
    main()
