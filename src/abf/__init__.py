"""Autonomy Boundary Framework (ABF) reference implementation.

Seven controls that make agent autonomy auditable:

Before acting:   Scope, Authority, Input Integrity
At the boundary: Reversibility, Legibility
After acting:    Observability, Provability
"""
from abf.intent import Intent, canonical_hash
from abf.boundary import AutonomyBoundary, BoundaryDecision
from abf.ledger import Ledger

__all__ = [
    "Intent",
    "canonical_hash",
    "AutonomyBoundary",
    "BoundaryDecision",
    "Ledger",
]
__version__ = "0.1.0"
