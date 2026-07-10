import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from services.shared.database import engine
from services.shared.architecture import get_ai_architecture_manifest, get_system_architecture_manifest
from services.shared.phase13 import get_phase13_manifest
from services.shared.production import production_readiness
from services.shared.security import SecurityHeadersMiddleware
from services.shared.stack import get_stack_manifest
from services.shared.roadmap import get_roadmap_manifest
from services.shared.competitive import get_competitive_position_manifest


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        request_id = (
            request.headers.get("x-request-id")
            or request.headers.get("x-trace-id")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id
        request.state.trace_id = request.headers.get("x-trace-id") or request_id

        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = request.state.trace_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        response.headers["X-Api-Version"] = request.headers.get("x-api-version", "v1")
        return response


def success_response(data: Any, request_id: str | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "request_id": request_id or str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **(meta or {}),
        },
    }


def pagination_meta(page: int, page_size: int, total: int) -> dict[str, Any]:
    return {
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_next": page * page_size < total,
            "cursor": None,
        }
    }


def clamp_pagination(page: int = 1, page_size: int = 20) -> tuple[int, int, int]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    return page, page_size, offset


def register_health_routes(app: FastAPI, service_name: str):
    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        return {
            "service": service_name,
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/ready")
    @app.get("/api/v1/ready")
    def ready():
        try:
            with Session(engine) as db:
                db.execute(text("SELECT 1"))
            database = "ok"
            status = "ready"
            code = 200
        except Exception:
            database = "unavailable"
            status = "degraded"
            code = 503
        return JSONResponse(
            status_code=code,
            content={
                "service": service_name,
                "status": status,
                "dependencies": {"database": database},
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    @app.get("/api/v1/stack")
    def stack():
        manifest = get_stack_manifest()
        return {
            "service": service_name,
            "stack": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/roadmap")
    def roadmap():
        manifest = get_roadmap_manifest()
        return {
            "service": service_name,
            "roadmap": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/competitive-position")
    def competitive_position():
        manifest = get_competitive_position_manifest()
        return {
            "service": service_name,
            "competitive_position": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/architecture/system")
    def system_architecture():
        manifest = get_system_architecture_manifest()
        return {
            "service": service_name,
            "architecture": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/architecture/ai")
    def ai_architecture():
        manifest = get_ai_architecture_manifest()
        return {
            "service": service_name,
            "architecture": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/evaluation/status")
    def evaluation_status():
        manifest = get_phase13_manifest()
        return {
            "service": service_name,
            "evaluation": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/future-roadmap")
    def future_roadmap():
        manifest = get_phase13_manifest()
        return {
            "service": service_name,
            "future_roadmap": manifest,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @app.get("/api/v1/production/readiness")
    def readiness():
        return {
            **production_readiness(service_name),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


def install_api_foundation(app: FastAPI, service_name: str):
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_health_routes(app, service_name)
