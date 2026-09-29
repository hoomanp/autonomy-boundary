from __future__ import annotations
import re
from typing import Any, Callable, Sequence

from abf.controls.base import Control, ControlResult
from abf.intent import Intent

DEFAULT_SUSPECT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore (all|previous|prior) instructions", re.I),
    re.compile(r"\.\./"),                # path traversal
    re.compile(r"\x00"),                 # null byte
    re.compile(r"<\s*script", re.I),
]

# A validator callable takes (intent, context) and returns (allowed, failure_reason)
ValidatorFn = Callable[[Intent, dict[str, Any]], tuple[bool, str]]


class InputIntegrityControl(Control):
    """Input Integrity: parameters and targets sourced from untrusted context
    are screened before they can shape an action.

    Supports regex scanning against prompt injection / traversal patterns,
    as well as pluggable validator functions for typed schemas (e.g. Pydantic)
    and enterprise guardrail services (e.g. Llama Guard, NeMo, Lakera).
    """

    name = "input_integrity"

    def __init__(
        self,
        patterns: Sequence[re.Pattern[str]] | None = None,
        *,
        validators: Sequence[ValidatorFn] | None = None,
        screen_target: bool = True,
    ) -> None:
        self.patterns = list(patterns if patterns is not None else DEFAULT_SUSPECT_PATTERNS)
        self.validators = list(validators or [])
        self.screen_target = screen_target

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        # 1. Screen parameters and target against suspect patterns
        param_strings = [str(v) for v in intent.params.values()]
        if self.screen_target:
            param_strings.append(intent.resource)
            if intent.resolved_target:
                param_strings.append(intent.resolved_target)

        flat = " ".join(param_strings)
        for pattern in self.patterns:
            if pattern.search(flat):
                return self.deny("suspect pattern in parameters or target", pattern=pattern.pattern)

        # 2. Execute pluggable validators (e.g. schema validation, enterprise classifiers)
        for validator in self.validators:
            try:
                ok, reason = validator(intent, context)
                if not ok:
                    return self.deny(f"validator denied input: {reason}")
            except Exception as exc:  # fail closed
                return self.deny(f"validator raised exception: {exc!r}")

        return self.allow("parameters and target passed integrity screen")
