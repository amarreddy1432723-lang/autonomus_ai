from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from services.shared.database import get_db

from .deps import JWT_SECRET_KEY, get_current_user_id

router = APIRouter()


def _require_admin(user_id: UUID) -> None:
    raw = os.getenv("NEXUS_ADMIN_USER_IDS", "")
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    if str(user_id) not in allowed:
        raise HTTPException(status_code=403, detail={"code": "admin_required", "message": "Admin access required."})


def _readiness_item(name: str, ok: bool, detail: str, severity: str = "blocker", action: str | None = None) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        "severity": "ok" if ok else severity,
        "action": "" if ok else (action or detail),
    }


def _release_runbook(root: Path, ready: bool) -> dict:
    verify = ".\\scripts\\full-verify.ps1 -AdminUserId $env:SMOKE_ADMIN_USER_ID -StrictSmoke"
    smoke = ".\\scripts\\smoke-test.ps1 -BackendUrl $env:SMOKE_BACKEND_URL -FrontendUrl $env:SMOKE_FRONTEND_URL -AdminUserId $env:SMOKE_ADMIN_USER_ID"
    deploy = ".\\scripts\\deploy-railway.ps1 -BackendUrl $env:SMOKE_BACKEND_URL -FrontendUrl $env:SMOKE_FRONTEND_URL -AdminUserId $env:SMOKE_ADMIN_USER_ID"
    backup = ".\\scripts\\backup-postgres.ps1 -DatabaseUrl $env:DATABASE_URL"
    restore = ".\\scripts\\restore-postgres.ps1 -DatabaseUrl $env:DATABASE_URL -BackupFile .\\backups\\arceus-latest.dump -Confirm RESTORE_ARCEUS_DATABASE"
    return {
        "recommended_next_step": "Deploy staging" if ready else "Clear blockers before deploy",
        "verify_command": verify,
        "smoke_command": smoke,
        "deploy_command": deploy,
        "backup_command": backup,
        "restore_command": restore,
        "rollback_command": "railway rollback",
        "release_notes": str(root / "RELEASE.md"),
        "operations_doc": str(root / "docs" / "OPERATIONS.md"),
        "sequence": [
            "Run full verification locally or in CI.",
            "Create a database backup before production migrations.",
            "Deploy staging and run smoke tests.",
            "Manually approve production deploy.",
            "Run post-deploy smoke tests and monitor errors/jobs.",
            "Rollback by previous Railway deployment/image SHA if smoke fails.",
        ],
    }


def _release_readiness_report() -> dict:
    from .billing import billing_configuration_status

    root = Path(__file__).resolve().parents[3]
    app_env = os.getenv("APP_ENV", os.getenv("NODE_ENV", "development")).lower()
    production_like = app_env in {"production", "prod", "staging"}
    jwt_default = JWT_SECRET_KEY == "supersecretkeyforlocaldevelopmentonlychangeinprod!"
    billing = billing_configuration_status()
    checks = [
        _readiness_item("GitHub Actions CI", (root / ".github" / "workflows" / "ci.yml").exists(), ".github/workflows/ci.yml exists", action="Add .github/workflows/ci.yml with backend, frontend, desktop, migration, and security checks."),
        _readiness_item("Release workflow", (root / ".github" / "workflows" / "release.yml").exists(), ".github/workflows/release.yml exists", action="Add .github/workflows/release.yml with staging smoke and manual production approval."),
        _readiness_item("Backend Dockerfile", (root / "backend" / "Dockerfile").exists(), "backend/Dockerfile exists", action="Add backend/Dockerfile for immutable API/worker images."),
        _readiness_item("Frontend Dockerfile", (root / "frontend" / "Dockerfile").exists(), "frontend/Dockerfile exists", action="Add frontend/Dockerfile or document the managed frontend deploy path."),
        _readiness_item("Railway deploy script", (root / "scripts" / "deploy-railway.ps1").exists(), "scripts/deploy-railway.ps1 exists", action="Add scripts/deploy-railway.ps1 and run it only after verification passes."),
        _readiness_item("Production smoke test script", (root / "scripts" / "smoke-test.ps1").exists(), "scripts/smoke-test.ps1 exists", action="Add scripts/smoke-test.ps1 for health, readiness, frontend, and admin checks."),
        _readiness_item("Postgres backup script", (root / "scripts" / "backup-postgres.ps1").exists(), "scripts/backup-postgres.ps1 exists", action="Add backup script and run it before migrations/deploy."),
        _readiness_item("Postgres restore script", (root / "scripts" / "restore-postgres.ps1").exists(), "scripts/restore-postgres.ps1 exists", action="Add restore script with explicit confirmation guard."),
        _readiness_item("Production auth fallback disabled", not production_like or os.getenv("ALLOW_DEMO_USER", "false").lower() != "true", "ALLOW_DEMO_USER must not be true in staging/production", action="Set ALLOW_DEMO_USER=false in staging/production."),
        _readiness_item("Dev auth fallback disabled", not production_like or os.getenv("ALLOW_DEV_AUTH_FALLBACK", "false").lower() != "true", "ALLOW_DEV_AUTH_FALLBACK must not be true in staging/production", action="Set ALLOW_DEV_AUTH_FALLBACK=false in staging/production."),
        _readiness_item("JWT secret configured", not production_like or not jwt_default, "JWT_SECRET must be set to a non-default value in staging/production", action="Generate a strong JWT_SECRET and configure it in the deployment environment."),
        _readiness_item("Encryption key configured", not production_like or bool(os.getenv("APP_ENCRYPTION_KEY")), "APP_ENCRYPTION_KEY must be set in staging/production", action="Set APP_ENCRYPTION_KEY for encrypted vault/provider secrets."),
        _readiness_item("Database configured", bool(os.getenv("DATABASE_URL")), "DATABASE_URL is required", action="Set DATABASE_URL to the production PostgreSQL connection string."),
        _readiness_item("Redis configured", bool(os.getenv("REDIS_URL")), "REDIS_URL enables durable queues and cache", action="Set REDIS_URL to the production Redis instance."),
        _readiness_item("Stripe billing ready", billing["ready"], "; ".join(billing["blockers"] or ["Stripe checkout/webhook basics configured"]), action="Set Stripe secret, webhook secret, and plan price IDs."),
        _readiness_item("Sandbox provider selected", bool(os.getenv("SANDBOX_PROVIDER")), "SANDBOX_PROVIDER should be docker for production", "warning", action="Set SANDBOX_PROVIDER=docker for production runtime isolation."),
        _readiness_item("Docker sandbox image selected", os.getenv("SANDBOX_PROVIDER", "").lower() != "docker" or bool(os.getenv("SANDBOX_DOCKER_IMAGE")), "SANDBOX_DOCKER_IMAGE should be set when Docker sandbox is enabled", "warning", action="Build/push sandbox image and set SANDBOX_DOCKER_IMAGE."),
        _readiness_item("Release identifier", bool(os.getenv("APP_RELEASE") or os.getenv("GIT_SHA")), "APP_RELEASE or GIT_SHA should be set for traceability", "warning", action="Set APP_RELEASE or GIT_SHA during CI release."),
        _readiness_item("Sentry configured", bool(os.getenv("SENTRY_DSN")), "SENTRY_DSN is recommended for production error visibility", "warning", action="Set SENTRY_DSN and NEXT_PUBLIC_SENTRY_DSN."),
        _readiness_item("Rate limits enabled", os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in {"0", "false", "no"}, "RATE_LIMIT_ENABLED should stay enabled in production", "warning", action="Keep RATE_LIMIT_ENABLED=true unless explicitly debugging."),
        _readiness_item("Desktop signing configured", bool(os.getenv("WIN_CSC_LINK") or os.getenv("CSC_LINK") or os.getenv("APPLE_ID")), "Signing secrets are needed in CI for trusted installers", "warning", action="Configure Windows/macOS signing secrets in GitHub Actions."),
    ]
    blockers = [item for item in checks if not item["ok"] and item["severity"] == "blocker"]
    warnings = [item for item in checks if not item["ok"] and item["severity"] == "warning"]
    ready = not blockers
    return {
        "ready": ready,
        "environment": app_env,
        "production_like": production_like,
        "release": os.getenv("APP_RELEASE") or os.getenv("GIT_SHA") or "local",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "billing": billing,
        "summary": {"blockers": len(blockers), "warnings": len(warnings), "checks": len(checks)},
        "runbook": _release_runbook(root, ready),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _observability_health_report() -> dict:
    root = Path(__file__).resolve().parents[3]
    prometheus_config = root / "ops" / "prometheus" / "prometheus.yml"
    alert_rules = root / "ops" / "prometheus" / "arceus-alerts.yml"
    grafana_dashboard = root / "ops" / "grafana" / "arceus-code-overview.json"
    docs_runbook = root / "docs" / "observability.md"
    alert_text = alert_rules.read_text(encoding="utf-8") if alert_rules.exists() else ""
    required_alerts = [
        ("ArceusServiceDown", "API/service scrape failure"),
        ("ArceusApiHighErrorRate", "5xx error-rate spike"),
        ("ArceusApiP99LatencyHigh", "slow route latency"),
        ("ArceusWorkerQueueDepthHigh", "worker queue backlog"),
        ("ArceusWorkerDown", "no worker capacity"),
        ("ArceusDeadLetterJobs", "failed background jobs"),
    ]
    alert_coverage = [
        {"name": name, "purpose": purpose, "present": name in alert_text}
        for name, purpose in required_alerts
    ]
    sentry_backend = bool(os.getenv("SENTRY_DSN"))
    sentry_frontend = bool(os.getenv("NEXT_PUBLIC_SENTRY_DSN") or os.getenv("SENTRY_FRONTEND_DSN"))
    prometheus_enabled = os.getenv("PROMETHEUS_METRICS_ENABLED", "true").lower() not in {"0", "false", "no"}
    app_release = os.getenv("APP_RELEASE") or os.getenv("GIT_SHA") or "local"
    checks = [
        _readiness_item("Backend Sentry", sentry_backend, "SENTRY_DSN captures backend Python exceptions", "warning"),
        _readiness_item("Frontend Sentry", sentry_frontend, "NEXT_PUBLIC_SENTRY_DSN captures browser errors", "warning"),
        _readiness_item("Prometheus metrics", prometheus_enabled, "PROMETHEUS_METRICS_ENABLED exposes /metrics", "warning"),
        _readiness_item("Release tag", app_release != "local", "APP_RELEASE or GIT_SHA ties errors to a deploy", "warning"),
        _readiness_item("Prometheus config", prometheus_config.exists(), "ops/prometheus/prometheus.yml exists", "warning"),
        _readiness_item("Alert rules", alert_rules.exists(), "ops/prometheus/arceus-alerts.yml exists", "warning"),
        _readiness_item("Required alert coverage", all(item["present"] for item in alert_coverage), "service, error, latency, worker, queue, and dead-letter alerts exist", "warning"),
        _readiness_item("Grafana dashboard", grafana_dashboard.exists(), "ops/grafana/arceus-code-overview.json exists", "warning"),
        _readiness_item("Observability runbook", docs_runbook.exists(), "docs/observability.md documents setup and incident checks", "warning"),
    ]
    warnings = [item for item in checks if not item["ok"]]
    return {
        "ready": not warnings,
        "release": app_release,
        "environment": os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")),
        "metrics_endpoint": "/metrics" if prometheus_enabled else None,
        "logging": {
            "format": "json",
            "request_id_header": "X-Request-Id",
            "trace_id_header": "X-Trace-Id",
            "response_time_header": "X-Response-Time-Ms",
        },
        "sentry": {
            "backend_configured": sentry_backend,
            "frontend_configured": sentry_frontend,
            "traces_sample_rate": os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"),
        },
        "prometheus": {
            "config_path": "ops/prometheus/prometheus.yml",
            "rules_path": "ops/prometheus/arceus-alerts.yml",
            "alert_coverage": alert_coverage,
        },
        "grafana": {
            "dashboard_path": "ops/grafana/arceus-code-overview.json",
            "dashboard_ready": grafana_dashboard.exists(),
        },
        "runbook": {
            "setup": "docker compose -f docker-compose.prod-smoke.yml --profile observability up -d",
            "targets": "http://localhost:9090/targets",
            "admin_gate": "GET /api/v1/admin/observability-health",
            "docs": "docs/observability.md",
        },
        "checks": checks,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/admin/users")
def get_admin_users(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import Integer, func
    from services.shared.models import AgentJob, Subscription, UsageEvent, User

    _require_admin(user_id)
    rows = db.query(User).order_by(User.created_at.desc()).limit(100).all()
    subscription_rows = {item.user_id: item for item in db.query(Subscription).order_by(Subscription.created_at.desc()).all()}
    usage_rows = {
        row[0]: {"events": int(row[1] or 0), "tokens": int(row[2] or 0), "cost": float(row[3] or 0)}
        for row in db.query(
            UsageEvent.user_id,
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0),
        ).group_by(UsageEvent.user_id).all()
    }
    job_rows = {
        row[0]: {"jobs": int(row[1] or 0), "failed": int(row[2] or 0)}
        for row in db.query(
            AgentJob.user_id,
            func.count(AgentJob.id),
            func.sum(func.cast(AgentJob.status.in_(["failed", "timeout", "dead_letter"]), Integer)),
        ).group_by(AgentJob.user_id).all()
    }
    return {
        "users": [
            {
                "id": str(item.id),
                "email": item.email,
                "name": item.name,
                "auth_provider": item.auth_provider,
                "is_active": item.is_active,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "subscription": {
                    "plan": (subscription_rows.get(item.id).plan_type if subscription_rows.get(item.id) else "free"),
                    "status": (subscription_rows.get(item.id).status if subscription_rows.get(item.id) else "active"),
                    "provider": (subscription_rows.get(item.id).provider if subscription_rows.get(item.id) else "internal"),
                },
                "usage": usage_rows.get(item.id, {"events": 0, "tokens": 0, "cost": 0.0}),
                "jobs": job_rows.get(item.id, {"jobs": 0, "failed": 0}),
            }
            for item in rows
        ]
    }


@router.get("/api/v1/admin/usage")
def get_admin_usage(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import func
    from services.shared.models import UsageEvent
    from .pa_service import admin_usage_summary

    _require_admin(user_id)
    usage = db.query(func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.total_tokens), 0)).one()
    route_rows = db.query(
        UsageEvent.route,
        func.count(UsageEvent.id),
        func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0),
    ).group_by(UsageEvent.route).order_by(func.count(UsageEvent.id).desc()).limit(25).all()
    return {
        "usage_events": int(usage[0] or 0),
        "total_tokens": int(usage[1] or 0),
        "routes": [
            {"route": row[0], "events": int(row[1] or 0), "tokens": int(row[2] or 0), "cost": float(row[3] or 0)}
            for row in route_rows
        ],
        "pa": admin_usage_summary(db),
    }


@router.get("/api/v1/admin/summary")
def get_admin_summary(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import func
    from services.shared.models import AgentJob, AuditLog, Subscription, UsageEvent, User

    _require_admin(user_id)
    usage = db.query(func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.total_tokens), 0)).one()
    plan_rows = db.query(Subscription.plan_type, Subscription.status, func.count(Subscription.id)).group_by(Subscription.plan_type, Subscription.status).all()
    failed_jobs = int(db.query(func.count(AgentJob.id)).filter(AgentJob.status.in_(["failed", "timeout", "dead_letter"])).scalar() or 0)
    total_jobs = int(db.query(func.count(AgentJob.id)).scalar() or 0)
    return {
        "users": int(db.query(func.count(User.id)).scalar() or 0),
        "active_subscriptions": int(db.query(func.count(Subscription.id)).filter(Subscription.status == "active").scalar() or 0),
        "usage_events": int(usage[0] or 0),
        "total_tokens": int(usage[1] or 0),
        "estimated_cost_usd": float(db.query(func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0)).scalar() or 0),
        "jobs": {
            "queued": int(db.query(func.count(AgentJob.id)).filter(AgentJob.status == "queued").scalar() or 0),
            "running": int(db.query(func.count(AgentJob.id)).filter(AgentJob.status == "running").scalar() or 0),
            "failed": failed_jobs,
            "total": total_jobs,
        },
        "error_rate": 0 if total_jobs == 0 else round(failed_jobs / total_jobs * 100, 2),
        "plans": [{"plan": row[0] or "free", "status": row[1] or "unknown", "count": int(row[2] or 0)} for row in plan_rows],
        "audit_events": int(db.query(func.count(AuditLog.id)).scalar() or 0),
    }


@router.get("/api/v1/admin/system-health")
def get_admin_system_health(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import func, text
    from services.shared.models import AgentJob

    _require_admin(user_id)
    db_ok = True
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive health endpoint
        db_ok = False
        db_error = str(exc)
    redis_status = {"configured": bool(os.getenv("REDIS_URL")), "ok": False, "queue_depth": None, "error": None}
    if os.getenv("REDIS_URL"):
        try:
            import redis  # type: ignore

            client = redis.from_url(os.getenv("REDIS_URL"), socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            redis_status.update({"ok": True, "queue_depth": int(client.llen(os.getenv("CELERY_QUEUE_NAME", "celery")))})
        except Exception as exc:  # pragma: no cover - optional dependency/runtime
            redis_status["error"] = str(exc)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    stale_jobs = int(db.query(func.count(AgentJob.id)).filter(AgentJob.status.in_(["claimed", "running"]), AgentJob.updated_at < stale_cutoff).scalar() or 0)
    return {
        "database": {"ok": db_ok, "error": db_error},
        "redis": redis_status,
        "workers": {
            "queue_depth": redis_status.get("queue_depth"),
            "stale_jobs": stale_jobs,
            "configured_mode": "redis" if os.getenv("REDIS_URL") else "in_process_dev_fallback",
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/v1/admin/abuse-flags")
def get_admin_abuse_flags(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import func
    from services.shared.models import AgentJob, UsageEvent, User

    _require_admin(user_id)
    day_start = datetime.now(timezone.utc) - timedelta(days=1)
    usage_rows = db.query(
        UsageEvent.user_id,
        func.count(UsageEvent.id).label("events"),
        func.coalesce(func.sum(UsageEvent.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0).label("cost"),
    ).filter(UsageEvent.created_at >= day_start).group_by(UsageEvent.user_id).all()
    failed_rows = {
        row[0]: int(row[1] or 0)
        for row in db.query(AgentJob.user_id, func.count(AgentJob.id))
        .filter(AgentJob.created_at >= day_start, AgentJob.status.in_(["failed", "timeout", "dead_letter"]))
        .group_by(AgentJob.user_id)
        .all()
    }
    users = {item.id: item for item in db.query(User).filter(User.id.in_([row[0] for row in usage_rows] or [user_id])).all()}
    flags = []
    for row in usage_rows:
        reasons = []
        if int(row.events or 0) >= 500:
            reasons.append("high request volume")
        if int(row.tokens or 0) >= 1_000_000:
            reasons.append("high token volume")
        if float(row.cost or 0) >= 25:
            reasons.append("high estimated spend")
        if failed_rows.get(row.user_id, 0) >= 20:
            reasons.append("many failed jobs")
        if reasons:
            user_row = users.get(row.user_id)
            flags.append({
                "user_id": str(row.user_id),
                "email": user_row.email if user_row else None,
                "reasons": reasons,
                "events_24h": int(row.events or 0),
                "tokens_24h": int(row.tokens or 0),
                "cost_24h": float(row.cost or 0),
                "failed_jobs_24h": failed_rows.get(row.user_id, 0),
            })
    return {"flags": flags, "window": "24h"}


@router.get("/api/v1/admin/billing-health")
def get_admin_billing_health(user_id: UUID = Depends(get_current_user_id)):
    from .billing import billing_configuration_status

    _require_admin(user_id)
    return billing_configuration_status()


@router.get("/api/v1/admin/release-readiness")
def get_admin_release_readiness(user_id: UUID = Depends(get_current_user_id)):
    _require_admin(user_id)
    return _release_readiness_report()


@router.get("/api/v1/admin/observability-health")
def get_admin_observability_health(user_id: UUID = Depends(get_current_user_id)):
    _require_admin(user_id)
    return _observability_health_report()


@router.get("/api/v1/admin/jobs")
def get_admin_jobs(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob

    _require_admin(user_id)
    rows = db.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(100).all()
    return {
        "jobs": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "mode": item.mode,
                "status": item.status,
                "approval_state": item.approval_state,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in rows
        ]
    }


@router.post("/api/v1/admin/jobs/{job_id}/kill")
def kill_admin_job(job_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob, AuditLog

    _require_admin(user_id)
    job = db.query(AgentJob).filter(AgentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Job not found."})
    terminal_states = {"completed", "failed", "cancelled", "dead_letter", "timeout"}
    previous_status = job.status
    if job.status not in terminal_states:
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        metadata = dict(job.metadata_json or {})
        metadata["admin_cancelled_at"] = datetime.now(timezone.utc).isoformat()
        metadata["admin_cancelled_by"] = str(user_id)
        job.metadata_json = metadata
        logs = list(job.logs or [])
        logs.append({"kind": "cancelled", "message": "Cancelled by admin", "timestamp": datetime.now(timezone.utc).isoformat()})
        job.logs = logs
    db.add(AuditLog(
        user_id=job.user_id,
        session_id=job.code_session_id,
        event_type="admin.job.kill",
        entity_type="agent_job",
        entity_id=job.id,
        actor_type="admin",
        actor_id=str(user_id),
        action="Admin cancelled job",
        old_value={"status": previous_status},
        new_value={"status": job.status},
    ))
    db.commit()
    db.refresh(job)
    return {"id": str(job.id), "status": job.status, "previous_status": previous_status}


@router.post("/api/v1/admin/jobs/{job_id}/retry")
def retry_admin_job(job_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob, AuditLog
    from .agent_jobs import reset_background_job_for_retry, serialize_job

    _require_admin(user_id)
    job = db.query(AgentJob).filter(AgentJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Job not found."})
    previous_status = job.status
    retried = reset_background_job_for_retry(db, job.user_id, job.id)
    db.add(AuditLog(
        user_id=job.user_id,
        session_id=job.code_session_id,
        event_type="admin.job.retry",
        entity_type="agent_job",
        entity_id=job.id,
        actor_type="admin",
        actor_id=str(user_id),
        action="Admin retried job",
        old_value={"status": previous_status},
        new_value={"status": retried.status, "retry_count": int((retried.metadata_json or {}).get("retry_count") or 0)},
    ))
    db.commit()
    db.refresh(retried)
    return {"job": serialize_job(retried), "previous_status": previous_status}


@router.get("/api/v1/admin/audit-logs")
def get_admin_audit_logs(
    audit_user_id: Optional[UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from services.shared.models import AuditLog

    _require_admin(user_id)
    query = db.query(AuditLog)
    if audit_user_id:
        query = query.filter(AuditLog.user_id == audit_user_id)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    rows = query.order_by(AuditLog.occurred_at.desc()).limit(limit).all()
    return {
        "audit_logs": [
            {
                "id": item.id,
                "user_id": str(item.user_id),
                "event_type": item.event_type,
                "entity_type": item.entity_type,
                "entity_id": str(item.entity_id) if item.entity_id else None,
                "action": item.action,
                "metadata": item.metadata_json or {},
                "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
            }
            for item in rows
        ]
    }


@router.get("/api/v1/admin/audit-logs/{audit_id}")
def get_admin_audit_log_detail(audit_id: int, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AuditLog

    _require_admin(user_id)
    item = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "audit_log_not_found", "message": "Audit log not found."})
    return {
        "audit_log": {
            "id": item.id,
            "user_id": str(item.user_id),
            "session_id": str(item.session_id) if item.session_id else None,
            "event_type": item.event_type,
            "entity_type": item.entity_type,
            "entity_id": str(item.entity_id) if item.entity_id else None,
            "actor_type": item.actor_type,
            "actor_id": item.actor_id,
            "action": item.action,
            "old_value": item.old_value,
            "new_value": item.new_value,
            "metadata": item.metadata_json or {},
            "ip_address": item.ip_address,
            "user_agent": item.user_agent,
            "checksum": item.checksum,
            "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
        }
    }
