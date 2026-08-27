"""Prefix-stable cache layout and a session_id bound as instance identity.

Issue #3: the ledger row must carry which instance acted. This teaching
kernel records a software claim — the harness session_id — not hardware
attestation. Sticky routing and prompt-cache keys reuse the same id so a
warm KV cache cannot outlive the grant that authorized the session.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


SYSTEM_PROMPT = (
    "You are a customer-operations agent. Propose refunds, memory writes, "
    "and KV lookups. You do not authorize them. The Autonomy Boundary does."
)

POLICY_PREFIX = (
    "In-force grant: capability envelope {read, write, refund}; "
    "chain_budget 8; irreversible action refund.issue requires human approval."
)


@dataclass(frozen=True)
class CacheSession:
    session_id: str
    prompt_cache_key: str
    cache_ttl: str = "5m"

    @classmethod
    def new(cls, session_id: str | None = None) -> "CacheSession":
        sid = session_id or uuid.uuid4().hex
        return cls(session_id=sid, prompt_cache_key=f"abf:{sid}")

    @property
    def instance_id(self) -> str:
        """Software instance claim bound into Intent.effective_identity."""
        return f"agent:refund:{self.session_id}"


def stable_prefix(
    *,
    system: str = SYSTEM_PROMPT,
    tools: list[dict[str, Any]] | None = None,
    policy: str = POLICY_PREFIX,
) -> list[dict[str, Any]]:
    """Cacheable prefix first; user turns and tool results stay last.

    Agent loops that prepend results or shuffle system text bust implicit
    KV cache. Keep this order so Anthropic cache_control, OpenAI
    prompt_cache_key, Gemini context cache, and OpenRouter translation
    all hit the same prefix.
    """
    prefix: list[dict[str, Any]] = [
        {"role": "system", "content": system, "cache": True},
        {"role": "system", "content": policy, "cache": True},
    ]
    if tools:
        prefix.append({"role": "system", "content": {"tools": tools}, "cache": True})
    return prefix
