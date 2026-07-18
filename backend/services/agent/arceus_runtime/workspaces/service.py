from __future__ import annotations

import re
from collections import Counter
from typing import Any


ACTIVE_MISSION_STATUSES = {"compiling", "organizing", "plan_pending", "awaiting_plan_approval", "ready", "running", "paused", "blocked", "reviewing", "verifying"}


def workspace_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "workspace"


def workspace_settings(defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "shell": "arceus_code",
        "primary_navigation": "missions",
        "offline_mode": {"enabled": True, "sync_strategy": "conflict_aware"},
        "desktop_modules": [
            "mission_explorer",
            "repository_explorer",
            "ai_organization_panel",
            "context_viewer",
            "review_center",
            "decision_center",
            "terminal",
            "notifications",
            "command_palette",
        ],
        **(defaults or {}),
    }


def repository_fingerprint(*, provider: str, repository_url: str, local_workspace_path: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    languages = metadata.get("languages") or []
    frameworks = metadata.get("frameworks") or []
    build_systems = metadata.get("build_systems") or []
    return {
        "provider": provider,
        "repository_url": repository_url,
        "local_workspace_path": local_workspace_path,
        "languages": languages,
        "frameworks": frameworks,
        "build_systems": build_systems,
        "repository_health": metadata.get("repository_health", "unknown"),
        "indexed": bool(metadata.get("indexed", False)),
    }


def organization_role_summary(members: list[Any]) -> list[dict[str, Any]]:
    counts = Counter(getattr(member, "role_key", "unknown") for member in members)
    return [{"role_key": role_key, "count": count} for role_key, count in sorted(counts.items())]
