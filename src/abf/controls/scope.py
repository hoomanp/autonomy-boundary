"""Scope: the agent may only act on resources inside its declared scope.

Scope is checked against the post-resolution target, not the display path.
Optionally verifies that the target system actually enforces the declared
boundary via active probing (addressing the declared-vs-enforced divergence
seen in the September 2026 DSEWiki incident).
"""
from __future__ import annotations

from fnmatch import fnmatch
from typing import Any, Callable

from abf.controls.base import Control, ControlResult
from abf.intent import Intent

TargetProbeFn = Callable[[Intent, dict[str, Any]], tuple[bool, str]]


class ScopeControl(Control):
    name = "scope"

    def __init__(
        self,
        allowed_resources: list[str],
        *,
        probe: TargetProbeFn | None = None,
    ) -> None:
        self.allowed_resources = allowed_resources
        self.probe = probe

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        target = intent.effect_target
        matched_pattern = None
        for pattern in self.allowed_resources:
            if fnmatch(target, pattern):
                matched_pattern = pattern
                break

        if not matched_pattern:
            return self.deny(
                "resource outside declared scope",
                resource=target,
                scope=self.allowed_resources,
            )

        if self.probe is not None:
            try:
                ok, reason = self.probe(intent, context)
                if not ok:
                    return self.deny(
                        f"target enforcement divergence: {reason}",
                        resource=target,
                    )
            except Exception as exc:  # fail closed
                return self.deny(f"target enforcement probe raised: {exc!r}")

        return self.allow(f"resource matches scope pattern '{matched_pattern}'")


class ProbedScopeControl(ScopeControl):
    """Scope control with cached target enforcement probing per action/endpoint."""

    def __init__(
        self,
        allowed_resources: list[str],
        probe_target_fn: Callable[[str, Intent], tuple[bool, str]],
    ) -> None:
        self._cached_probes: dict[str, tuple[bool, str]] = {}

        def _cached_probe(intent: Intent, context: dict[str, Any]) -> tuple[bool, str]:
            key = f"{intent.action}:{intent.effect_target}"
            if key not in self._cached_probes:
                self._cached_probes[key] = probe_target_fn(key, intent)
            return self._cached_probes[key]

        super().__init__(allowed_resources, probe=_cached_probe)
