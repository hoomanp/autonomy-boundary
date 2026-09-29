"""Autonomy Boundary Framework (ABF) reference implementation.

Eight controls that make agent autonomy auditable:

Before acting:   Scope, Authority, Input Integrity
At the boundary: Reversibility, Legibility, State Admissibility
After acting:    Observability, Provability
"""
from abf.intent import Intent, canonical_hash, canonicalize_target, snapshot_state
from abf.boundary import AutonomyBoundary, BoundaryDecision
from abf.ledger import Ledger
from abf.mcp import ABFMCPGateway, MCPTool
from abf.skill import AutonomyBoundarySkill, ProposedAction

__all__ = [
    "Intent",
    "canonical_hash",
    "canonicalize_target",
    "snapshot_state",
    "AutonomyBoundary",
    "BoundaryDecision",
    "Ledger",
    "ABFMCPGateway",
    "MCPTool",
    "AutonomyBoundarySkill",
    "ProposedAction",
]
__version__ = "0.3.0"
