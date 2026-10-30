"""Tiered Merkle LLM Memory & Provenance Taint-Tracked KV Subsystem.

Addresses two failure modes in stateful LLM agents (MemGPT / Letta / LangMem):
1. Whole-store hashing bottleneck: Replaces O(N) full-store re-hashing on every
   tool call with selective key snapshots and O(log N) Merkle inclusion proofs.
2. Second-order memory poisoning (delayed prompt injection): Separates agent
   memory into three governed tiers:
     - Procedural (system rules, skill definitions; write-locked without admin approval)
     - Semantic   (Merkle-committed structured KV facts for State Admissibility)
     - Episodic   (retrieved/RAG/conversation chunks with provenance TaintLevel)
   When an episodic entry tainted with UNTRUSTED_EXTERNAL is read into the
   working context, any high-impact action proposed in that turn is denied
   unless accompanied by an explicit human approval token.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Iterable, Mapping

from abf.intent import Intent, canonical_hash, canonical_json


class TaintLevel(IntEnum):
    """Information-flow provenance taint labels ordered by risk."""

    TRUSTED = 0
    USER = 1
    UNTRUSTED_EXTERNAL = 2


@dataclass(frozen=True)
class MerkleSibling:
    """Single step in a binary Merkle inclusion proof."""

    hash: str
    position: str  # "left" or "right"


@dataclass(frozen=True)
class MerkleProof:
    """O(log N) cryptographic inclusion proof for a single Semantic KV key."""

    key: str
    leaf_hash: str
    root_hash: str
    siblings: tuple[MerkleSibling, ...]

    def verify(self, expected_root: str | None = None) -> bool:
        target_root = expected_root if expected_root is not None else self.root_hash
        current = self.leaf_hash
        for step in self.siblings:
            if step.position == "left":
                combined = f"node:{step.hash}:{current}"
            else:
                combined = f"node:{current}:{step.hash}"
            current = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return current == target_root


@dataclass(frozen=True)
class EpisodicRecord:
    """An episodic memory entry carrying provenance taint metadata."""

    entry_id: str
    text: str
    taint: TaintLevel
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    content_hash: str = ""


def _leaf_hash(key: str, value: Any) -> str:
    payload = canonical_json({"key": key, "value": value})
    return hashlib.sha256(f"leaf:{payload}".encode("utf-8")).hexdigest()


def _pair_hash(left: str, right: str) -> str:
    return hashlib.sha256(f"node:{left}:{right}".encode("utf-8")).hexdigest()


class GovernedMemoryStore:
    """Three-tier governed memory subsystem for stateful LLM agents."""

    def __init__(self) -> None:
        self._procedural: dict[str, Any] = {}
        self._semantic: dict[str, Any] = {}
        self._episodic: list[EpisodicRecord] = []
        self._active_taint: TaintLevel = TaintLevel.TRUSTED
        self._active_sources: list[str] = []

    # ── Tier 1: Procedural Memory (Write-Locked System Rules / Skills) ────

    def set_procedural(
        self,
        key: str,
        value: Any,
        *,
        admin_approval: Mapping[str, Any] | None = None,
    ) -> None:
        """Write to procedural memory. Requires explicit admin approval after bootstrap."""
        if key in self._procedural and not admin_approval:
            raise PermissionError(
                f"procedural memory key '{key}' is write-locked; admin_approval required"
            )
        self._procedural[key] = value

    def get_procedural(self, key: str, default: Any = None) -> Any:
        return self._procedural.get(key, default)

    # ── Tier 2: Semantic KV Memory (Merkle Tree & Selective State Deps) ───

    def put_semantic(self, key: str, value: Any) -> str:
        """Store a structured fact and return its leaf hash."""
        self._semantic[key] = value
        return _leaf_hash(key, value)

    def get_semantic(self, key: str, default: Any = None) -> Any:
        return self._semantic.get(key, default)

    def semantic_state(self) -> dict[str, Any]:
        """Return a shallow copy of the semantic KV dictionary."""
        return dict(self._semantic)

    def snapshot_keys(self, keys: Iterable[str]) -> dict[str, str]:
        """Snapshot only the specified decision-critical keys for Intent.state_deps."""
        return {
            k: canonical_hash({k: self._semantic.get(k)})
            for k in keys
        }

    def merkle_root(self) -> str:
        """Compute the binary Merkle root over sorted Semantic KV entries."""
        if not self._semantic:
            return hashlib.sha256(b"empty_merkle_tree").hexdigest()
        sorted_keys = sorted(self._semantic.keys())
        level = [_leaf_hash(k, self._semantic[k]) for k in sorted_keys]
        while len(level) > 1:
            next_level: list[str] = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(_pair_hash(left, right))
            level = next_level
        return level[0]

    def prove_key(self, key: str) -> MerkleProof:
        """Construct an O(log N) Merkle inclusion proof for `key`."""
        if key not in self._semantic:
            raise KeyError(f"semantic key not found: {key}")
        sorted_keys = sorted(self._semantic.keys())
        idx = sorted_keys.index(key)
        leaves = [_leaf_hash(k, self._semantic[k]) for k in sorted_keys]
        leaf = leaves[idx]

        siblings: list[MerkleSibling] = []
        level = leaves
        cur_idx = idx
        while len(level) > 1:
            if cur_idx % 2 == 0:
                sib_idx = cur_idx + 1 if cur_idx + 1 < len(level) else cur_idx
                siblings.append(MerkleSibling(hash=level[sib_idx], position="right"))
            else:
                sib_idx = cur_idx - 1
                siblings.append(MerkleSibling(hash=level[sib_idx], position="left"))

            next_level: list[str] = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(_pair_hash(left, right))
            level = next_level
            cur_idx //= 2

        return MerkleProof(
            key=key,
            leaf_hash=leaf,
            root_hash=level[0],
            siblings=tuple(siblings),
        )

    # ── Tier 3: Episodic Memory (Provenance Taint Tracking) ──────────────

    def add_episodic(
        self,
        text: str,
        *,
        taint: TaintLevel = TaintLevel.USER,
        source: str = "user_turn",
        entry_id: str | None = None,
    ) -> EpisodicRecord:
        """Append an episodic memory chunk with explicit provenance taint."""
        eid = entry_id or f"ep_{len(self._episodic) + 1:04d}"
        chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rec = EpisodicRecord(
            entry_id=eid,
            text=text,
            taint=TaintLevel(taint),
            source=source,
            content_hash=chash,
        )
        self._episodic.append(rec)
        return rec

    def recall_episodic(self, limit: int = 10) -> list[EpisodicRecord]:
        """Recall recent episodic records and propagate their taint into active context."""
        records = self._episodic[-limit:]
        for rec in records:
            if rec.taint > self._active_taint:
                self._active_taint = rec.taint
            if rec.taint == TaintLevel.UNTRUSTED_EXTERNAL and rec.source not in self._active_sources:
                self._active_sources.append(rec.source)
        return records

    @property
    def active_taint(self) -> TaintLevel:
        """Highest provenance taint level read into the current agent turn."""
        return self._active_taint

    @property
    def tainted_sources(self) -> tuple[str, ...]:
        return tuple(self._active_sources)

    def clear_active_taint(self) -> None:
        """Reset turn-level active taint after a human-verified checkpoint."""
        self._active_taint = TaintLevel.TRUSTED
        self._active_sources.clear()

    def make_taint_validator(
        self,
        *,
        high_impact_actions: Iterable[str] = (
            "refund.issue",
            "email.send",
            "db.delete",
            "funds.transfer",
            "file.write",
        ),
    ) -> Callable[[Intent, dict[str, Any]], tuple[bool, str]]:
        """Return a validator for InputIntegrityControl that blocks untrusted taint flow.

        If the agent has recalled `UNTRUSTED_EXTERNAL` episodic memory in this turn
        and proposes a high-impact action without an explicit human `approval` token,
        the validator fails closed.
        """
        protected = set(high_impact_actions)

        def _validate(intent: Intent, context: dict[str, Any]) -> tuple[bool, str]:
            taint = context.get("memory_taint", self._active_taint)
            if int(taint) >= int(TaintLevel.UNTRUSTED_EXTERNAL):
                if intent.action in protected and not context.get("approval"):
                    sources = ", ".join(self._active_sources) or "external_rag"
                    return (
                        False,
                        f"tainted episodic memory ({sources}) cannot drive "
                        f"high-impact action '{intent.action}' without human approval",
                    )
            return True, "memory provenance taint check passed"

        return _validate
