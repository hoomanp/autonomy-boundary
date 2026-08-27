"""Live provider calls stay out of CI; they need keys and extras."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ABF_HARNESS_LIVE"),
    reason="live provider calls are not part of CI",
)


def test_live_flag_only():
    assert os.environ.get("ABF_HARNESS_LIVE")
