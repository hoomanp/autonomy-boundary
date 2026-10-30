"""Autonomy Boundary Framework (ABF) reference implementation.

Eight controls that make agent autonomy auditable:

Before acting:   Scope, Authority, Input Integrity
At the boundary: Reversibility, Legibility, State Admissibility
After acting:    Observability, Provability
"""
from abf.intent import Intent, canonical_hash, canonicalize_target, snapshot_state
from abf.boundary import AutonomyBoundary, BoundaryDecision
from abf.crypto import Ed25519Keypair, ed25519_sign, ed25519_verify
from abf.frontier import (
    BatchEvaluationResult,
    FrontierModelHarness,
    ReasoningAlignmentControl,
    ReasoningEnvelope,
    extract_reasoning_trace,
)
from abf.graph import (
    BoundaryGraph,
    BoundaryInterrupt,
    BudgetCoordinator,
    CausalDAGTracker,
    CycleDetectedError,
    CycleDetector,
)
from abf.ledger import Ledger
from abf.mcp import ABFMCPGateway, MCPTool
from abf.memory import EpisodicRecord, GovernedMemoryStore, MerkleProof, TaintLevel
from abf.skill import AutonomyBoundarySkill, ProposedAction

__all__ = [
    "Intent",
    "canonical_hash",
    "canonicalize_target",
    "snapshot_state",
    "AutonomyBoundary",
    "BoundaryDecision",
    "Ed25519Keypair",
    "ed25519_sign",
    "ed25519_verify",
    "FrontierModelHarness",
    "ReasoningAlignmentControl",
    "ReasoningEnvelope",
    "BatchEvaluationResult",
    "extract_reasoning_trace",
    "BoundaryGraph",
    "BoundaryInterrupt",
    "BudgetCoordinator",
    "CausalDAGTracker",
    "CycleDetector",
    "CycleDetectedError",
    "Ledger",
    "ABFMCPGateway",
    "MCPTool",
    "GovernedMemoryStore",
    "MerkleProof",
    "TaintLevel",
    "EpisodicRecord",
    "AutonomyBoundarySkill",
    "ProposedAction",
]
__version__ = "0.4.0"

