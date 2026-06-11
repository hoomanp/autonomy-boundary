"""Input Integrity: parameters sourced from untrusted context are screened
before they can shape an action (prompt-injection and traversal patterns)."""
from __future__ import annotations

import re
from typing import Any

from abf.controls.base import Control, ControlResult
from abf.intent import Intent

SUSPECT_PATTERNS = [
    re.compile(r"ignore (all|previous|prior) instructions", re.I),
    re.compile(r"\.\./"),                # path traversal
    re.compile(r"\x00"),                 # null byte
    re.compile(r"<\s*script", re.I),
]


class InputIntegrityControl(Control):
    name = "input_integrity"

    def check(self, intent: Intent, context: dict[str, Any]) -> ControlResult:
        flat = " ".join(str(v) for v in intent.params.values())
        for pattern in SUSPECT_PATTERNS:
            if pattern.search(flat):
                return self.deny("suspect pattern in parameters", pattern=pattern.pattern)
        return self.allow("parameters passed integrity screen")
