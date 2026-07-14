from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/downloads/latest")
def get_latest_download_manifest():
    from .downloads import build_download_manifest

    return build_download_manifest()


@router.get("/")
def service_root():
    return {
        "service": "agent-service",
        "status": "running",
        "message": "This is an Arceus API service. Open the frontend UI instead.",
        "frontend": os.getenv("NEXUS_FRONTEND_URL", "http://localhost:3000/workspace"),
        "docs": "/docs",
    }
