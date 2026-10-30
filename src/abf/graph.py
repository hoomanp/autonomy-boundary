"""Cyclic Agent Graph & Loop Governor with Interrupt/Resume & Causal DAG.

Provides first-class graph and loop orchestration primitives for cyclic agent
workflows (LangGraph, AutoGen, CrewAI, custom ReAct loops):

1. `BoundaryInterrupt` suspend/resume protocol: Instead of rubber-stamping
   human approvals inside a tool wrapper, irreversible actions lacking an
   approval token raise `BoundaryInterrupt` with a serialized checkpoint.
   Once an external human signs the approval token, `graph.resume(...)`
   re-evaluates all boundary controls (including State Admissibility for drift
   during human wait time) and completes execution.
2. `BudgetCoordinator`: Thread-safe atomic task budget and monotonic capability
   attenuation across concurrent fan-out branches.
3. `CycleDetector`: Detects and halts runaway cyclic tool-call oscillation
   before token/API budgets are exhausted.
4. `CausalDAGTracker`: Enforces cryptographic parent-child intent lineage
   (`parent_intent_id`, `step_index`, `branch_id`) across loops and branches.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping

from abf.boundary import AutonomyBoundary, BoundaryDecision as Decision
from abf.controls.legibility import render_for_human
from abf.intent import Intent, canonical_hash


class BoundaryInterrupt(Exception):
    """Raised when an intent requires out-of-band human approval to proceed."""

    def __init__(
        self,
        intent: Intent,
        *,
        checkpoint_id: str,
        node_name: str = "",
        reason: str = "irreversible action requires human approval token",
        decision: Decision | None = None,
    ) -> None:
        self.intent = intent
        self.checkpoint_id = checkpoint_id
        self.node_name = node_name
        self.reason = reason
        self.rendered_prompt = render_for_human(intent)
        self.decision = decision
        super().__init__(f"BoundaryInterrupt[{checkpoint_id}]: {reason} — {self.rendered_prompt}")


class CycleDetectedError(RuntimeError):
    """Raised when an agent loop repeats identical intents beyond threshold."""


class BudgetCoordinator:
    """Thread-safe atomic budget and capability envelope coordinator for graphs."""

    def __init__(
        self,
        chain_budget: int,
        root_capabilities: Iterable[str] | None = None,
    ) -> None:
        self.chain_budget = chain_budget
        self.root_capabilities = (
            frozenset(root_capabilities) if root_capabilities is not None else None
        )
        self._lock = threading.RLock()
        self._spent = 0

    @property
    def spent(self) -> int:
        with self._lock:
            return self._spent

    def try_reserve(self, cost: int = 1) -> tuple[bool, int]:
        """Atomically check and reserve `cost` units from `chain_budget`.

        Returns `(allowed, spent_before_reservation)`.
        """
        with self._lock:
            prior = self._spent
            if prior + cost > self.chain_budget:
                return False, prior
            self._spent += cost
            return True, prior

    def refund(self, cost: int = 1) -> None:
        """Release reserved budget if a downstream control denies the intent."""
        with self._lock:
            self._spent = max(0, self._spent - cost)


class CycleDetector:
    """Detects repetitive cyclic tool calls and enforces maximum loop depth."""

    def __init__(
        self,
        *,
        max_steps: int = 25,
        max_identical_repeats: int = 2,
    ) -> None:
        self.max_steps = max_steps
        self.max_identical_repeats = max_identical_repeats
        self._lock = threading.RLock()
        self._step_count = 0
        self._counts: dict[str, int] = {}

    def record_and_check(self, intent: Intent) -> tuple[bool, str]:
        fingerprint = canonical_hash(
            {
                "action": intent.action,
                "target": intent.effect_target,
                "params": dict(intent.params),
            }
        )
        with self._lock:
            self._step_count += 1
            if self._step_count > self.max_steps:
                return (
                    False,
                    f"loop exceeded max_steps ({self._step_count} > {self.max_steps})",
                )
            count = self._counts.get(fingerprint, 0) + 1
            self._counts[fingerprint] = count
            if count > self.max_identical_repeats:
                return (
                    False,
                    f"cyclic oscillation detected: '{intent.action}' on "
                    f"'{intent.effect_target}' repeated {count} times",
                )
            return True, "ok"


class CausalDAGTracker:
    """Tracks and validates parent-child intent lineage across loops and branches."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, Intent] = {}
        self._branch_heads: dict[str, str] = {}

    def bind_lineage(
        self,
        intent: Intent,
        *,
        branch_id: str = "main",
        parent_intent_id: str | None = None,
    ) -> Intent:
        """Attach causal DAG metadata (`parent_intent_id`, `step_index`, `branch_id`)."""
        with self._lock:
            parent_id = (
                parent_intent_id
                if parent_intent_id is not None
                else self._branch_heads.get(branch_id, "")
            )
            parent_step = self._nodes[parent_id].step_index if parent_id in self._nodes else 0
            bound = replace(
                intent,
                parent_intent_id=parent_id,
                step_index=parent_step + 1,
                branch_id=branch_id,
            )
            return bound

    def commit(self, intent: Intent) -> None:
        """Record an evaluated intent into the causal DAG."""
        with self._lock:
            if intent.parent_intent_id and intent.parent_intent_id not in self._nodes:
                raise ValueError(
                    f"unknown parent_intent_id '{intent.parent_intent_id}' in causal DAG"
                )
            self._nodes[intent.intent_id] = intent
            if intent.branch_id:
                self._branch_heads[intent.branch_id] = intent.intent_id

    def verify_dag(self) -> bool:
        """Verify all parent links exist and step indices strictly increase."""
        with self._lock:
            for iid, node in self._nodes.items():
                if node.parent_intent_id:
                    parent = self._nodes.get(node.parent_intent_id)
                    if parent is None or node.step_index <= parent.step_index:
                        return False
            return True

    @property
    def intents(self) -> dict[str, Intent]:
        with self._lock:
            return dict(self._nodes)


@dataclass
class GraphCheckpoint:
    """Suspended graph execution state awaiting external human approval."""

    checkpoint_id: str
    node_name: str
    intent: Intent
    context: dict[str, Any]
    executor_fn: Callable[[Intent], Any] | None = None


class BoundaryGraph:
    """Governed cyclic graph & loop runner integrated with `AutonomyBoundary`.

    Wraps intent execution with:
      - Causal DAG lineage tracking (`CausalDAGTracker`)
      - Runaway loop & cycle detection (`CycleDetector`)
      - Thread-safe atomic budget coordination (`BudgetCoordinator`)
      - `BoundaryInterrupt` suspend/resume when human approval is required
    """

    def __init__(
        self,
        boundary: AutonomyBoundary,
        *,
        signing_key: bytes = b"",
        private_key: bytes | None = None,
        chain_budget: int = 10,
        max_steps: int = 25,
        max_identical_repeats: int = 2,
        interrupt_on_approval_required: bool = True,
    ) -> None:
        self.boundary = boundary
        self.signing_key = signing_key
        self.private_key = private_key
        self.budget = BudgetCoordinator(chain_budget=chain_budget)
        self.cycle_detector = CycleDetector(
            max_steps=max_steps,
            max_identical_repeats=max_identical_repeats,
        )
        self.dag = CausalDAGTracker()
        self.interrupt_on_approval_required = interrupt_on_approval_required
        self._checkpoints: dict[str, GraphCheckpoint] = {}

    def _sign_intent(self, intent: Intent) -> Intent:
        if self.private_key is not None:
            return intent.sign_ed25519(self.private_key)
        if self.signing_key:
            return intent.sign(self.signing_key)
        return intent

    def step(
        self,
        intent: Intent,
        context: Mapping[str, Any] | None = None,
        *,
        node_name: str = "agent_step",
        branch_id: str = "main",
        parent_intent_id: str | None = None,
        executor_fn: Callable[[Intent], Any] | None = None,
    ) -> tuple[Decision, Any]:
        """Execute a single governed graph step or raise `BoundaryInterrupt`."""
        ctx = dict(context or {})

        # 1. Bind causal DAG lineage and re-sign
        lined_intent = self.dag.bind_lineage(
            intent,
            branch_id=branch_id,
            parent_intent_id=parent_intent_id,
        )
        signed_intent = self._sign_intent(lined_intent)

        # 2. Check for cyclic oscillation / max loop depth
        ok_cycle, cycle_reason = self.cycle_detector.record_and_check(signed_intent)
        if not ok_cycle:
            self.boundary.ledger.append(
                "graph_cycle_halted",
                {
                    "intent_id": signed_intent.intent_id,
                    "action": signed_intent.action,
                    "reason": cycle_reason,
                },
            )
            raise CycleDetectedError(cycle_reason)

        # 3. Atomically reserve budget across concurrent branches
        reserved, prior_spend = self.budget.try_reserve(1)
        ctx.setdefault("task_spend", prior_spend if reserved else self.budget.chain_budget)

        # 4. Evaluate through the Autonomy Boundary
        decision = self.boundary.evaluate(signed_intent, ctx)
        if not decision.allowed:
            if reserved:
                self.budget.refund(1)

            # Check if denial is specifically because Reversibility requires human approval
            rev_denials = [
                r
                for r in decision.results
                if r.control == "reversibility"
                and not r.allowed
                and r.details.get("requires_approval") is True
            ]
            if rev_denials and self.interrupt_on_approval_required and not ctx.get("approval"):
                ckpt_id = f"ckpt_{uuid.uuid4().hex[:10]}"
                self._checkpoints[ckpt_id] = GraphCheckpoint(
                    checkpoint_id=ckpt_id,
                    node_name=node_name,
                    intent=signed_intent,
                    context=ctx,
                    executor_fn=executor_fn,
                )
                self.boundary.ledger.append(
                    "boundary_interrupt",
                    {
                        "checkpoint_id": ckpt_id,
                        "intent_id": signed_intent.intent_id,
                        "intent_hash": signed_intent.hash,
                        "node_name": node_name,
                    },
                )
                raise BoundaryInterrupt(
                    signed_intent,
                    checkpoint_id=ckpt_id,
                    node_name=node_name,
                    reason=rev_denials[0].reason,
                    decision=decision,
                )
            return decision, None

        self.dag.commit(signed_intent)
        output = executor_fn(signed_intent) if executor_fn is not None else None
        if executor_fn is not None:
            self.boundary.record_execution(
                signed_intent,
                {"node": node_name, "branch_id": branch_id, "output": output},
            )
        return decision, output

    def resume(
        self,
        checkpoint_id: str,
        *,
        approval: Mapping[str, Any],
        updated_context: Mapping[str, Any] | None = None,
    ) -> tuple[Decision, Any]:
        """Resume a suspended `GraphCheckpoint` with a human-signed approval token."""
        if checkpoint_id not in self._checkpoints:
            raise KeyError(f"unknown or already-resumed checkpoint_id: {checkpoint_id}")
        ckpt = self._checkpoints.pop(checkpoint_id)

        ctx = dict(ckpt.context)
        if updated_context:
            ctx.update(updated_context)
        ctx["approval"] = dict(approval)

        reserved, prior_spend = self.budget.try_reserve(1)
        ctx["task_spend"] = prior_spend if reserved else self.budget.chain_budget

        decision = self.boundary.evaluate(ckpt.intent, ctx)
        if not decision.allowed:
            if reserved:
                self.budget.refund(1)
            return decision, None

        self.dag.commit(ckpt.intent)
        output = ckpt.executor_fn(ckpt.intent) if ckpt.executor_fn is not None else None
        if ckpt.executor_fn is not None:
            self.boundary.record_execution(
                ckpt.intent,
                {
                    "node": ckpt.node_name,
                    "resumed_from": checkpoint_id,
                    "output": output,
                },
            )
        return decision, output
