import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any

import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from services.shared.database import engine
from services.shared.architecture import get_ai_architecture_manifest, get_system_architecture_manifest
from services.shared.phase13 import get_phase13_manifest
from services.shared.production import enforce_production_startup, production_readiness
from services.shared.security import SecurityHeadersMiddleware
from services.shared.stack import get_stack_manifest
from services.shared.roadmap import get_roadmap_manifest
from services.shared.competitive import get_competitive_position_manifest

logger = logging.getLogger("arceus-api")


def configure_json_logging() -> None:
    if getattr(configure_json_logging, "_configured", False):
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        stream=sys.stdout,
        format="%(message)s",
        force=False,
    )
    configure_json_logging._configured = True


def configure_sentry(service_name: str) -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except Exception:
        logger.warning(json.dumps({"event": "sentry_unavailable", "service": service_name}))
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0")),
        environment=os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")),
        release=os.getenv("APP_RELEASE", os.getenv("GIT_SHA", "local")),
        send_default_pii=False,
    )
    logger.info(json.dumps({"event": "sentry_enabled", "service": service_name}))


def configure_prometheus(app: FastAPI, service_name: str) -> None:
    if os.getenv("PROMETHEUS_METRICS_ENABLED", "true").lower() in {"0", "false", "no"}:
        return
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except Exception:
        logger.warning(json.dumps({"event": "prometheus_unavailable", "service": service_name}))
        return
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info(json.dumps({"event": "prometheus_enabled", "service": service_name, "endpoint": "/metrics"}))


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
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "trace_id": request.state.trace_id,
                    "user_id": request.headers.get("x-user-id"),
                    "action": request.headers.get("x-arceus-action") or request.url.path,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                    "service": request.app.title,
                },
                separators=(",", ":"),
            )
        )
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
        dependencies = {}
        try:
            with Session(engine) as db:
                db.execute(text("SELECT 1"))
            dependencies["database"] = "ok"
        except Exception:
            dependencies["database"] = "unavailable"

        try:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            else:
                client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", "6379")),
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            client.ping()
            dependencies["redis"] = "ok"
        except Exception:
            dependencies["redis"] = "unavailable"

        required = ("database",)
        optional = ("redis",)
        critical_down = any(dependencies.get(name) != "ok" for name in required)
        optional_down = any(dependencies.get(name) != "ok" for name in optional)
        status = "blocked" if critical_down else "degraded" if optional_down else "ready"
        code = 503 if critical_down else 200
        return JSONResponse(
            status_code=code,
            content={
                "service": service_name,
                "status": status,
                "dependencies": dependencies,
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
    enforce_production_startup(service_name)
    configure_json_logging()
    configure_sentry(service_name)
    configure_prometheus(app, service_name)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_health_routes(app, service_name)
