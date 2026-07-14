from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from services.shared.models import AuditLog


def _checksum(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_audit_log(
    db: Session,
    *,
    user_id: UUID,
    event_type: str,
    action: str,
    session_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor_type: str = "user",
    actor_id: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    metadata_json = dict(metadata or {})
    ip_address = None
    user_agent = None
    if request is not None:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    checksum_payload = {
        "user_id": str(user_id),
        "session_id": str(session_id) if session_id else None,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "old_value": old_value,
        "new_value": new_value,
        "metadata_json": metadata_json,
    }
    log = AuditLog(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type=actor_type,
        actor_id=actor_id or str(user_id),
        action=action,
        old_value=old_value,
        new_value=new_value,
        metadata_json=metadata_json,
        ip_address=ip_address,
        user_agent=user_agent,
        checksum=_checksum(checksum_payload),
    )
    db.add(log)
    return log
