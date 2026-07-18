"""Shared primitives for Arceus OS Kernel modules."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))

