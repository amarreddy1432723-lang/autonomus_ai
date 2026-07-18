from __future__ import annotations

import hashlib
import json
from typing import Any


def calculate_request_hash(operation_key: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"operation": operation_key, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
