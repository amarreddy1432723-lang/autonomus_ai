from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import Integration


PLATFORM_VERSION = "2.0.0"
SDK_LANGUAGES = ["python", "typescript", "java", "go", "rust", "csharp", "kotlin", "swift"]
SDK_MODULES = [
    "authentication",
    "missions",
    "organizations",
    "runtime",
    "knowledge_graph",
    "automation",
    "search",
    "events",
    "plugins",
    "tool_gateway",
]
EXTENSION_TYPES = {
    "ai_specialist",
    "tool",
    "connector",
    "workflow_pack",
    "mission_template",
    "policy",
    "knowledge_pack",
    "prompt_library",
    "model_provider",
    "ui_component",
    "dashboard",
    "widget",
    "cli_command",
    "language_pack",
    "theme",
    "authentication_provider",
    # Backward-compatible aliases used by the existing UI.
    "agent_skill",
    "panel",
}
PLUGIN_STATUSES = {"installed", "verified", "active", "paused", "disabled", "failed", "deleted"}
PERMISSIONS = {
    "files:read",
    "files:write",
    "terminal:run",
    "web:fetch",
    "panel:render",
    "agent:tool",
    "repositories.read",
    "repositories.write",
    "pull_requests.write",
    "missions.read",
    "missions.write",
    "organizations.read",
    "organizations.write",
    "knowledge.read",
    "knowledge.write",
    "events.subscribe",
    "events.publish",
    "connectors.invoke",
    "specialists.register",
    "workflow.import",
    "models.invoke",
    "ui.render",
    "themes.apply",
    "policies.propose",
    "auth.providers",
}
TRUSTED_PUBLISHERS = {"Arceus", "Arceus Labs", "arceus"}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


SAMPLE_MARKETPLACE = [
    {
        "id": "arceus-github",
        "name": "GitHub Integration",
        "version": "1.2.0",
        "publisher": "Arceus",
        "description": "Connect repositories, approved hunks, pull requests, checks, and release evidence.",
        "type": "connector",
        "permissions": ["repositories.read", "repositories.write", "pull_requests.write", "events.publish"],
        "capabilities": [
            {"id": "github.repo_picker", "version": "1.0.0", "kind": "connector", "health": "healthy"},
            {"id": "github.pull_request_flow", "version": "1.0.0", "kind": "connector", "health": "healthy"},
        ],
        "entry": "connectors/github.py",
        "signature": "arceus:first-party",
        "verification_status": "verified",
    },
    {
        "id": "arceus-sql-reviewer",
        "name": "SQL Reviewer",
        "version": "0.1.0",
        "publisher": "Arceus",
        "description": "Adds a governed SQL review specialist for schema, query, and migration checks.",
        "type": "ai_specialist",
        "permissions": ["files:read", "agent:tool", "knowledge.read"],
        "capabilities": [
            {"id": "database.schema_review", "version": "0.1.0", "kind": "ai_specialist", "health": "healthy"},
            {"id": "database.query_optimization", "version": "0.1.0", "kind": "ai_specialist", "health": "healthy"},
        ],
        "entry": "specialists/sql_reviewer.py",
        "signature": "arceus:first-party",
        "verification_status": "verified",
    },
    {
        "id": "arceus-launch-workflow",
        "name": "Startup Launch Workflow",
        "version": "0.2.0",
        "publisher": "Arceus",
        "description": "Workflow pack for idea discovery, architecture, roadmap, build proof, release, and post-launch learning.",
        "type": "workflow_pack",
        "permissions": ["missions.write", "workflow.import", "events.subscribe"],
        "capabilities": [
            {"id": "workflow.startup_launch", "version": "0.2.0", "kind": "workflow_pack", "health": "healthy"},
        ],
        "entry": "workflows/startup_launch.yml",
        "signature": "arceus:first-party",
        "verification_status": "verified",
    },
    {
        "id": "arceus-design-checks",
        "name": "Design Checks",
        "version": "0.1.0",
        "publisher": "Arceus",
        "description": "Adds a compact UI extension for spacing, typography, contrast, and interaction checks.",
        "type": "ui_component",
        "permissions": ["panel:render", "ui.render", "files:read"],
        "capabilities": [
            {"id": "ui.design_review_panel", "version": "0.1.0", "kind": "ui_component", "health": "healthy"},
        ],
        "entry": "ui/design_checks.js",
        "signature": "arceus:first-party",
        "verification_status": "verified",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _major(version: str) -> int:
    try:
        return int(str(version).split(".", 1)[0])
    except Exception:
        return 0


def _manifest_root(manifest: dict[str, Any]) -> dict[str, Any]:
    plugin = manifest.get("plugin")
    if isinstance(plugin, dict):
        return {**plugin, **{key: value for key, value in manifest.items() if key != "plugin"}}
    return dict(manifest)


def _normalize_capabilities(manifest: dict[str, Any], extension_type: str) -> list[dict[str, Any]]:
    raw = manifest.get("capabilities") or []
    capabilities: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            capabilities.append({"id": item, "version": manifest["version"], "kind": extension_type, "health": "unknown"})
        elif isinstance(item, dict):
            capability_id = str(item.get("id") or item.get("name") or "").strip()
            if capability_id:
                capabilities.append({
                    "id": capability_id,
                    "version": str(item.get("version") or manifest["version"]),
                    "kind": str(item.get("kind") or extension_type),
                    "requirements": item.get("requirements") or [],
                    "permissions": item.get("permissions") or manifest.get("permissions") or [],
                    "health": str(item.get("health") or "unknown"),
                    "owner": manifest["id"],
                })

    for key, kind in (("tools", "tool"), ("connectors", "connector"), ("skills", "ai_specialist"), ("panels", "ui_component")):
        for item in manifest.get(key) or []:
            if isinstance(item, str):
                capabilities.append({"id": item, "version": manifest["version"], "kind": kind, "health": "unknown", "owner": manifest["id"]})
            elif isinstance(item, dict):
                capability_id = str(item.get("id") or item.get("name") or "").strip()
                if capability_id:
                    capabilities.append({
                        "id": capability_id,
                        "version": str(item.get("version") or manifest["version"]),
                        "kind": kind,
                        "requirements": item.get("requirements") or [],
                        "permissions": item.get("permissions") or manifest.get("permissions") or [],
                        "health": str(item.get("health") or "unknown"),
                        "owner": manifest["id"],
                    })
    return capabilities


def verify_manifest_signature(manifest: dict[str, Any]) -> dict[str, Any]:
    publisher = str(manifest.get("publisher") or manifest.get("author") or "").strip()
    signature = str(manifest.get("signature") or "").strip()
    trusted_publisher = publisher in TRUSTED_PUBLISHERS
    signed = bool(signature)
    verified = signed and (trusted_publisher or signature.startswith("sha256:") or signature.startswith("sig:"))
    executable = verified
    return {
        "signed": signed,
        "trusted_publisher": trusted_publisher,
        "verified": verified,
        "executable": executable,
        "reason": "verified" if verified else "Unsigned or untrusted extensions can be installed for review, but cannot execute.",
    }


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    root = _manifest_root(manifest)
    plugin_id = str(root.get("id") or root.get("plugin_id") or root.get("name") or "").strip()
    name = str(root.get("name") or "").strip()
    version = str(root.get("version") or "").strip()
    publisher = str(root.get("publisher") or root.get("author") or "").strip() or "Unknown"
    entry = str(root.get("entry") or "").strip()
    extension_type = str(root.get("type") or root.get("plugin_type") or root.get("category") or "tool").strip()
    permissions = root.get("permissions") or []
    dependencies = root.get("dependencies") or []
    runtime = root.get("runtime") or {}

    if not plugin_id or not name or not version:
        raise HTTPException(status_code=400, detail="Plugin manifest requires id, name, and version")
    if not SEMVER_RE.match(version):
        raise HTTPException(status_code=400, detail="Plugin version must use semantic versioning")
    if extension_type not in EXTENSION_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported extension type: {extension_type}")
    if not isinstance(permissions, list):
        raise HTTPException(status_code=400, detail="Plugin permissions must be a list")
    if not isinstance(dependencies, list):
        raise HTTPException(status_code=400, detail="Plugin dependencies must be a list")
    unknown = sorted(set(map(str, permissions)) - PERMISSIONS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown plugin permission(s): {', '.join(unknown)}")

    min_runtime = str(runtime.get("min_version") or root.get("min_runtime_version") or "1.0.0")
    if _major(min_runtime) > _major(PLATFORM_VERSION):
        raise HTTPException(status_code=400, detail=f"Plugin requires Arceus runtime {min_runtime}, current runtime is {PLATFORM_VERSION}")

    normalized = {
        "id": plugin_id,
        "name": name,
        "version": version,
        "publisher": publisher,
        "entry": entry,
        "type": extension_type,
        "description": str(root.get("description") or ""),
        "permissions": list(map(str, permissions)),
        "dependencies": dependencies,
        "runtime": {"min_version": min_runtime},
        "tools": root.get("tools") or [],
        "panels": root.get("panels") or [],
        "skills": root.get("skills") or [],
        "connectors": root.get("connectors") or [],
        "signature": str(root.get("signature") or ""),
        "source": root.get("source") or "manual",
        "compatibility": {"platform_version": PLATFORM_VERSION, "compatible": True},
    }
    normalized["capabilities"] = _normalize_capabilities({**normalized, "capabilities": root.get("capabilities") or []}, extension_type)
    normalized["verification"] = verify_manifest_signature(normalized)
    return normalized


def list_marketplace_plugins() -> list[dict[str, Any]]:
    return [validate_manifest({**plugin, "source": "marketplace"}) for plugin in SAMPLE_MARKETPLACE]


def serialize_plugin(row: Integration) -> dict[str, Any]:
    manifest = row.metadata_json or {}
    verification = manifest.get("verification") or verify_manifest_signature(manifest)
    return {
        "id": str(row.id),
        "plugin_id": manifest.get("id") or row.provider_user_id,
        "status": row.status,
        "manifest": manifest,
        "lifecycle": manifest.get("lifecycle") or [],
        "capabilities": manifest.get("capabilities") or [],
        "verification": verification,
        "executable": bool(verification.get("executable")) and row.status in {"active", "verified"},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_installed_plugins(db: Session, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(Integration)
        .filter(Integration.user_id == user_id, Integration.provider == "plugin", Integration.status != "deleted")
        .order_by(Integration.created_at.desc())
        .all()
    )
    return [serialize_plugin(row) for row in rows]


def get_plugin(db: Session, user_id: UUID, plugin_id: UUID) -> dict[str, Any]:
    row = db.query(Integration).filter(Integration.id == plugin_id, Integration.user_id == user_id, Integration.provider == "plugin").first()
    if not row or row.status == "deleted":
        raise HTTPException(status_code=404, detail="Plugin not found")
    return serialize_plugin(row)


def install_plugin(db: Session, user_id: UUID, manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_manifest(manifest)
    lifecycle_event = {"event": "PLUGIN_INSTALLED", "status": "verified" if normalized["verification"]["verified"] else "installed", "at": _now()}
    status = "verified" if normalized["verification"]["verified"] else "installed"
    if normalized["verification"]["verified"]:
        lifecycle_event["next"] = "loaded"
    normalized["lifecycle"] = [lifecycle_event]

    existing = (
        db.query(Integration)
        .filter(
            Integration.user_id == user_id,
            Integration.provider == "plugin",
            Integration.provider_user_id == normalized["id"],
            Integration.status != "deleted",
        )
        .first()
    )
    if existing:
        previous_lifecycle = (existing.metadata_json or {}).get("lifecycle") or []
        normalized["lifecycle"] = previous_lifecycle + [{"event": "PLUGIN_UPDATED", "status": status, "at": _now()}]
        existing.metadata_json = {**(existing.metadata_json or {}), **normalized}
        existing.scopes = normalized["permissions"]
        existing.status = status
        row = existing
    else:
        row = Integration(
            user_id=user_id,
            provider="plugin",
            status=status,
            scopes=normalized["permissions"],
            provider_user_id=normalized["id"],
            metadata_json=normalized,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_plugin(row)


def update_plugin(db: Session, user_id: UUID, plugin_id: UUID, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    row = db.query(Integration).filter(Integration.id == plugin_id, Integration.user_id == user_id, Integration.provider == "plugin").first()
    if not row or row.status == "deleted":
        raise HTTPException(status_code=404, detail="Plugin not found")
    normalized = validate_manifest(manifest or row.metadata_json or {})
    lifecycle = list((row.metadata_json or {}).get("lifecycle") or [])
    lifecycle.append({"event": "PLUGIN_UPDATED", "status": row.status, "at": _now()})
    normalized["lifecycle"] = lifecycle
    row.metadata_json = normalized
    row.scopes = normalized["permissions"]
    if row.status == "active" and not normalized["verification"]["executable"]:
        row.status = "installed"
    db.commit()
    db.refresh(row)
    return serialize_plugin(row)


def set_plugin_status(db: Session, user_id: UUID, plugin_id: UUID, status: str) -> dict[str, Any]:
    if status not in PLUGIN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Plugin status must be one of: {', '.join(sorted(PLUGIN_STATUSES))}")
    row = db.query(Integration).filter(Integration.id == plugin_id, Integration.user_id == user_id, Integration.provider == "plugin").first()
    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found")
    manifest = row.metadata_json or {}
    verification = manifest.get("verification") or verify_manifest_signature(manifest)
    if status == "active" and not verification.get("executable"):
        raise HTTPException(status_code=403, detail="Unsigned or unverified plugins cannot be activated")
    lifecycle = list(manifest.get("lifecycle") or [])
    lifecycle.append({"event": f"PLUGIN_{status.upper()}", "status": status, "at": _now()})
    manifest["lifecycle"] = lifecycle
    row.metadata_json = manifest
    row.status = status
    db.commit()
    db.refresh(row)
    return serialize_plugin(row)


def list_extensions(db: Session, user_id: UUID) -> dict[str, Any]:
    plugins = list_installed_plugins(db, user_id)
    extensions = []
    capabilities = []
    for plugin in plugins:
        manifest = plugin["manifest"]
        if plugin["status"] not in {"active", "verified"}:
            continue
        extensions.append({
            "plugin_id": plugin["plugin_id"],
            "name": manifest.get("name"),
            "type": manifest.get("type"),
            "status": plugin["status"],
            "permissions": manifest.get("permissions") or [],
            "executable": plugin["executable"],
        })
        for capability in manifest.get("capabilities") or []:
            capabilities.append({
                **capability,
                "owner": manifest.get("id"),
                "plugin_name": manifest.get("name"),
                "status": plugin["status"],
                "permissions": capability.get("permissions") or manifest.get("permissions") or [],
            })
    return {"extensions": extensions, "capabilities": capabilities, "count": len(extensions)}


def sdk_manifest() -> dict[str, Any]:
    return {
        "platform": "arceus",
        "runtime_version": PLATFORM_VERSION,
        "languages": SDK_LANGUAGES,
        "modules": SDK_MODULES,
        "event_bus": {
            "events": [
                "PLUGIN_INSTALLED",
                "PLUGIN_UPDATED",
                "PLUGIN_REMOVED",
                "CONNECTOR_AUTHORIZED",
                "SPECIALIST_REGISTERED",
                "WORKFLOW_IMPORTED",
                "KNOWLEDGE_PACK_LOADED",
                "EXTENSION_FAILED",
            ],
            "delivery": "immutable_event_log",
        },
        "extension_types": sorted(EXTENSION_TYPES),
        "permission_catalog": sorted(PERMISSIONS),
        "security": {
            "signature_required_for_execution": True,
            "sandboxed_runtime": True,
            "audit_required": True,
            "direct_plugin_to_plugin_calls": "discouraged",
        },
    }
