from __future__ import annotations

import os
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.security import resolve_user_id_from_auth_or_clerk

JWT_SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonlychangeinprod!")
JWT_ALGORITHM = "HS256"


def get_current_user_id(
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="x-user-id"),
    db: Session = Depends(get_db),
) -> UUID:
    return resolve_user_id_from_auth_or_clerk(db, authorization, x_user_id, JWT_SECRET_KEY, JWT_ALGORITHM)


def require_entitlement_or_402(db: Session, user_id: UUID, feature: str) -> dict:
    from .billing import require_feature_entitlement

    return require_feature_entitlement(db, user_id, feature)


def require_session_project_role(db: Session, user_id: UUID, session, minimum: str = "editor") -> None:
    if not getattr(session, "project_id", None):
        return
    from .code_workspace import require_project_role

    require_project_role(db, user_id, session.project_id, minimum)


def parse_vault_key(x_vault_key: str | None) -> bytes | None:
    if not x_vault_key:
        return None
    try:
        return bytes.fromhex(x_vault_key)
    except Exception:
        return None
