from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from abf.intent import Intent


@dataclass(frozen=True)
class ControlResult:
    control: str
    allowed: bool
    reason: str
    detail: dict[str, Any] | None = None


class Control(ABC):
    """A composable guard. Controls fail closed: any exception is a deny."""

    name: str = "control"

    @abstractmethod
    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult: ...

    def deny(self, reason: str, **detail: Any) -> ControlResult:
        return ControlResult(self.name, False, reason, detail or None)

    def allow(self, reason: str, **detail: Any) -> ControlResult:
        return ControlResult(self.name, True, reason, detail or None)
