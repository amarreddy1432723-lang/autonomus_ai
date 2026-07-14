from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/downloads/latest")
def get_latest_download_manifest():
    from .downloads import build_download_manifest

    return build_download_manifest()


@router.get("/api/v1/production/readiness")
def get_public_production_readiness():
    from .routes_admin import _release_readiness_report

    report = _release_readiness_report()
    checks = [
        {
            "name": item.get("name"),
            "ok": bool(item.get("ok")),
            "severity": item.get("severity"),
        }
        for item in report.get("checks", [])
    ]
    return {
        "service": "agent-service",
        "status": "ready" if report.get("ready") else "blocked",
        "ready": bool(report.get("ready")),
        "environment": report.get("environment"),
        "release": report.get("release"),
        "summary": report.get("summary") or {
            "blockers": len(report.get("blockers") or []),
            "warnings": len(report.get("warnings") or []),
            "checks": len(checks),
        },
        "checks": checks,
        "checked_at": report.get("checked_at"),
    }


@router.get("/")
def service_root():
    return {
        "service": "agent-service",
        "status": "running",
        "message": "This is an Arceus API service. Open the frontend UI instead.",
        "frontend": os.getenv("NEXUS_FRONTEND_URL", "http://localhost:3000/workspace"),
        "docs": "/docs",
    }
