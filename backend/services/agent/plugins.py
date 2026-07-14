from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import Integration


REQUIRED_PERMISSIONS = {"files:read", "files:write", "terminal:run", "web:fetch", "panel:render", "agent:tool"}


SAMPLE_MARKETPLACE = [
    {
        "id": "arceus-sql-reviewer",
        "name": "SQL Reviewer",
        "version": "0.1.0",
        "description": "Adds a /sql-review skill for schema and query review.",
        "type": "agent_skill",
        "permissions": ["files:read", "agent:tool"],
    },
    {
        "id": "arceus-api-tester",
        "name": "API Tester",
        "version": "0.1.0",
        "description": "Adds request collection helpers for API projects.",
        "type": "tool",
        "permissions": ["web:fetch", "agent:tool"],
    },
    {
        "id": "arceus-design-checks",
        "name": "Design Checks",
        "version": "0.1.0",
        "description": "Adds a compact UI review panel for spacing, typography, and contrast checks.",
        "type": "panel",
        "permissions": ["panel:render", "files:read"],
    },
]


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    name = str(manifest.get("name") or "").strip()
    version = str(manifest.get("version") or "").strip()
    entry = str(manifest.get("entry") or "").strip()
    plugin_type = str(manifest.get("type") or manifest.get("plugin_type") or "tool").strip()
    permissions = manifest.get("permissions") or []
    if not name or not version:
        raise HTTPException(status_code=400, detail="Plugin manifest requires name and version")
    if plugin_type not in {"agent_skill", "panel", "tool"}:
        raise HTTPException(status_code=400, detail="Plugin type must be agent_skill, panel, or tool")
    if not isinstance(permissions, list):
        raise HTTPException(status_code=400, detail="Plugin permissions must be a list")
    unknown = sorted(set(map(str, permissions)) - REQUIRED_PERMISSIONS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown plugin permission(s): {', '.join(unknown)}")
    return {
        "name": name,
        "version": version,
        "entry": entry,
        "type": plugin_type,
        "description": str(manifest.get("description") or ""),
        "permissions": list(map(str, permissions)),
        "tools": manifest.get("tools") or [],
        "panels": manifest.get("panels") or [],
        "skills": manifest.get("skills") or [],
        "source": manifest.get("source") or "manual",
    }


def list_marketplace_plugins() -> list[dict[str, Any]]:
    return SAMPLE_MARKETPLACE


def list_installed_plugins(db: Session, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(Integration)
        .filter(Integration.user_id == user_id, Integration.provider == "plugin", Integration.status != "deleted")
        .order_by(Integration.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "status": row.status,
            "manifest": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


def install_plugin(db: Session, user_id: UUID, manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_manifest(manifest)
    existing = (
        db.query(Integration)
        .filter(
            Integration.user_id == user_id,
            Integration.provider == "plugin",
            Integration.metadata_json["name"].as_string() == normalized["name"],
            Integration.status != "deleted",
        )
        .first()
    )
    if existing:
        existing.metadata_json = {**(existing.metadata_json or {}), **normalized}
        existing.status = "active"
        row = existing
    else:
        row = Integration(
            user_id=user_id,
            provider="plugin",
            status="active",
            scopes=normalized["permissions"],
            provider_user_id=normalized["name"],
            metadata_json=normalized,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "status": row.status, "manifest": row.metadata_json}


def set_plugin_status(db: Session, user_id: UUID, plugin_id: UUID, status: str) -> dict[str, Any]:
    if status not in {"active", "disabled", "deleted"}:
        raise HTTPException(status_code=400, detail="Plugin status must be active, disabled, or deleted")
    row = db.query(Integration).filter(Integration.id == plugin_id, Integration.user_id == user_id, Integration.provider == "plugin").first()
    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found")
    row.status = status
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "status": row.status, "manifest": row.metadata_json or {}}
