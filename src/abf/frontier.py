"""Frontier Reasoning Model Harness (Thinking-Trace Binding & Atomic Parallel Batching).

Designed for frontier reasoning architectures:
  - Anthropic Claude 3.7 / 4.x Extended Thinking (`thinking` + `signature` blocks)
  - OpenAI o3 / o4-mini / GPT-5 (`reasoning_content` / `encrypted_content`)
  - Google Gemini 2.5 / 3.x Thinking (`thought=True` parts)
  - DeepSeek-R1 / Qwen-QwQ (`<think>...</think>` blocks)

Provides two critical safety guarantees:
1. Cryptographic Reasoning-to-Intent Binding (`reasoning_hash`):
   Hashes the model's pre-action reasoning trace into `Intent.reasoning_hash`,
   creating a four-part audit chain in the ledger:
       reasoning_hash -> intent_hash -> approval_signature -> execution_record
2. All-or-Nothing Transactional Parallel Tool Fan-Out (`evaluate_parallel_batch`):
   Frontier models routinely emit K parallel tool calls in a single turn.
   Instead of executing call 1 before discovering call 2 violates policy (or
   allowing K split calls to bypass cumulative financial/energy limits),
   `FrontierModelHarness` evaluates the entire batch + cumulative JEPA state
   trajectory before any side effect runs.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from abf.boundary import AutonomyBoundary, BoundaryDecision as Decision
from abf.controls.base import Control, ControlResult
from abf.intent import Intent, canonical_json

_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)

_DECEPTIVE_REASONING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"hide\s+this\s+from\s+(the\s+)?(user|operator|auditor)", re.I),
    re.compile(r"bypass\s+(the\s+)?(approval|boundary|policy|limit)", re.I),
    re.compile(r"split\s+(the\s+)?(transaction|refund|transfer)\s+to\s+evade", re.I),
    re.compile(r"ignore\s+safety\s+constraints", re.I),
)


@dataclass(frozen=True)
class ReasoningEnvelope:
    """Normalized representation of a frontier model's thinking trace."""

    provider: str
    thinking_text: str
    provider_signature: str = ""

    @property
    def reasoning_hash(self) -> str:
        payload = canonical_json(
            {
                "provider": self.provider,
                "thinking_text": self.thinking_text.strip(),
                "provider_signature": self.provider_signature,
            }
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_reasoning_trace(raw_response: Mapping[str, Any] | str) -> ReasoningEnvelope:
    """Extract and canonicalize reasoning traces from Claude, OpenAI, Gemini, or DeepSeek."""
    if isinstance(raw_response, str):
        match = _THINK_TAG_RE.search(raw_response)
        text = match.group(1).strip() if match else raw_response.strip()
        return ReasoningEnvelope(provider="deepseek_r1", thinking_text=text)

    # 1. Anthropic Claude Extended Thinking format: content: [{"type": "thinking", ...}]
    content = raw_response.get("content")
    if isinstance(content, list):
        thinking_chunks: list[str] = []
        signatures: list[str] = []
        for block in content:
            if isinstance(block, Mapping):
                if block.get("type") == "thinking":
                    thinking_chunks.append(str(block.get("thinking", "")))
                    if block.get("signature"):
                        signatures.append(str(block["signature"]))
                elif block.get("thought") is True and "text" in block:
                    thinking_chunks.append(str(block["text"]))
        if thinking_chunks:
            provider = str(raw_response.get("provider") or "anthropic_thinking")
            return ReasoningEnvelope(
                provider=provider,
                thinking_text="\n".join(thinking_chunks),
                provider_signature=":".join(signatures),
            )

    # 2. OpenAI o-series / DeepSeek API format: reasoning_content or reasoning dict
    if "reasoning_content" in raw_response:
        return ReasoningEnvelope(
            provider=str(raw_response.get("provider") or "openai_reasoning"),
            thinking_text=str(raw_response["reasoning_content"]),
            provider_signature=str(raw_response.get("encrypted_content", "")),
        )

    reasoning_obj = raw_response.get("reasoning")
    if isinstance(reasoning_obj, Mapping):
        summary = reasoning_obj.get("summary") or reasoning_obj.get("text") or ""
        if isinstance(summary, list):
            summary = "\n".join(
                str(s.get("text", s)) if isinstance(s, Mapping) else str(s)
                for s in summary
            )
        return ReasoningEnvelope(
            provider=str(raw_response.get("provider") or "openai_o_series"),
            thinking_text=str(summary),
            provider_signature=str(reasoning_obj.get("encrypted_content", "")),
        )

    # 3. Gemini candidates[0].content.parts with thought=True
    candidates = raw_response.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = (
            candidates[0].get("content", {}).get("parts", [])
            if isinstance(candidates[0], Mapping)
            else []
        )
        thoughts = [
            str(p.get("text", ""))
            for p in parts
            if isinstance(p, Mapping) and p.get("thought") is True
        ]
        if thoughts:
            return ReasoningEnvelope(
                provider="gemini_thinking",
                thinking_text="\n".join(thoughts),
            )

    return ReasoningEnvelope(
        provider=str(raw_response.get("provider") or "unknown"),
        thinking_text=str(raw_response.get("thinking", "")),
    )


class ReasoningAlignmentControl(Control):
    """Verifies that frontier model intents carry a valid, non-deceptive reasoning trace."""

    name = "reasoning_alignment"

    def __init__(self, *, require_reasoning_hash: bool = True) -> None:
        self.require_reasoning_hash = require_reasoning_hash

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        if self.require_reasoning_hash and not intent.reasoning_hash:
            return self.deny("intent is missing cryptographic reasoning_hash binding")

        reasoning_text = str(context.get("reasoning_text") or "")
        if reasoning_text:
            for pattern in _DECEPTIVE_REASONING_PATTERNS:
                match = pattern.search(reasoning_text)
                if match:
                    return self.deny(
                        "deceptive or policy-evading goal detected in model thinking trace",
                        matched=match.group(0),
                        reasoning_hash=intent.reasoning_hash[:12],
                    )
        return self.allow(
            "reasoning trace bound and aligned",
            reasoning_hash=intent.reasoning_hash[:12] if intent.reasoning_hash else "none",
        )


@dataclass(frozen=True)
class BatchEvaluationResult:
    """Outcome of an all-or-nothing parallel tool-call batch evaluation."""

    allowed: bool
    decisions: tuple[Decision, ...]
    outputs: tuple[Any, ...]
    failed_index: int | None = None
    reason: str = ""


class FrontierModelHarness:
    """Harness for binding frontier model thinking traces and governing parallel tool batches."""

    def __init__(
        self,
        boundary: AutonomyBoundary,
        *,
        signing_key: bytes = b"",
        private_key: bytes | None = None,
    ) -> None:
        self.boundary = boundary
        self.signing_key = signing_key
        self.private_key = private_key

    def bind_reasoning(
        self,
        intent: Intent,
        reasoning: ReasoningEnvelope | Mapping[str, Any] | str,
    ) -> Intent:
        """Bind a frontier model's thinking trace hash into `intent` and sign it."""
        envelope = (
            reasoning
            if isinstance(reasoning, ReasoningEnvelope)
            else extract_reasoning_trace(reasoning)
        )
        bound = replace(intent, reasoning_hash=envelope.reasoning_hash)
        if self.private_key is not None:
            return bound.sign_ed25519(self.private_key)
        if self.signing_key:
            return bound.sign(self.signing_key)
        return bound

    def evaluate_parallel_batch(
        self,
        intents: Sequence[Intent],
        context: Mapping[str, Any] | None = None,
        *,
        reasoning: ReasoningEnvelope | Mapping[str, Any] | str | None = None,
        executor_fn: Callable[[Intent], Any] | None = None,
    ) -> BatchEvaluationResult:
        """All-or-nothing transactional evaluation of K parallel tool calls.

        Prevents split-transaction evasion (e.g., issuing five $200 refunds in
        parallel to bypass a $500 single-call limit) by accumulating `task_spend`
        and `world_state.cumulative_spend` across the batch during pre-execution
        evaluation. Side effects only run if ALL K intents pass.
        """
        base_ctx = dict(context or {})
        envelope: ReasoningEnvelope | None = None
        if reasoning is not None:
            envelope = (
                reasoning
                if isinstance(reasoning, ReasoningEnvelope)
                else extract_reasoning_trace(reasoning)
            )
            base_ctx.setdefault("reasoning_text", envelope.thinking_text)

        bound_intents: list[Intent] = []
        for item in intents:
            if envelope is not None and not item.reasoning_hash:
                bound_intents.append(self.bind_reasoning(item, envelope))
            elif self.private_key is not None and not item.signature:
                bound_intents.append(item.sign_ed25519(self.private_key))
            elif self.signing_key and not item.signature:
                bound_intents.append(item.sign(self.signing_key))
            else:
                bound_intents.append(item)

        decisions: list[Decision] = []
        sim_spend = int(base_ctx.get("task_spend") or 0)
        sim_world = dict(base_ctx.get("world_state") or {})
        cumulative_amount = float(sim_world.get("cumulative_spend", 0.0) or 0.0)
        affected_count = int(sim_world.get("affected_resources", 0) or 0)

        for idx, intent in enumerate(bound_intents):
            step_ctx = dict(base_ctx)
            step_ctx["task_spend"] = sim_spend
            step_world = dict(sim_world)
            step_world["cumulative_spend"] = cumulative_amount
            step_world["affected_resources"] = affected_count
            step_ctx["world_state"] = step_world

            decision = self.boundary.evaluate(intent, step_ctx)
            decisions.append(decision)
            if not decision.allowed:
                self.boundary.ledger.append(
                    "parallel_batch_aborted",
                    {
                        "batch_size": len(bound_intents),
                        "failed_index": idx,
                        "failed_intent_id": intent.intent_id,
                    },
                )
                return BatchEvaluationResult(
                    allowed=False,
                    decisions=tuple(decisions),
                    outputs=(),
                    failed_index=idx,
                    reason=f"batch aborted at index {idx} ({intent.action})",
                )

            # Advance simulated cumulative state for subsequent calls in the same batch
            sim_spend += 1
            amt = float(
                intent.params.get("amount", intent.params.get("cost", 0.0)) or 0.0
            )
            cumulative_amount += amt
            affected_count += int(intent.params.get("count", 1) or 1)

        # All K intents passed! Now commit side effects.
        outputs: list[Any] = []
        for intent in bound_intents:
            out = executor_fn(intent) if executor_fn is not None else None
            outputs.append(out)
            if executor_fn is not None:
                self.boundary.record_execution(
                    intent,
                    {"batch_size": len(bound_intents), "output": out},
                )

        return BatchEvaluationResult(
            allowed=True,
            decisions=tuple(decisions),
            outputs=tuple(outputs),
            failed_index=None,
            reason="all parallel intents in batch approved and executed",
        )
