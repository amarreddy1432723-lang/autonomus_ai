from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import RuntimeHealthResponse


router = APIRouter(tags=["runtime-health"])


def classify_runtime_health(summary: dict) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    outbox_statuses = summary.get("outbox_statuses") or {}
    task_statuses = summary.get("task_statuses") or {}
    approval_statuses = summary.get("approval_statuses") or {}

    if int(outbox_statuses.get("dead_letter", 0)) > 0:
        blockers.append("dead_letter_outbox_messages")
    if int(summary.get("stale_processing_outbox", 0)) > 0:
        blockers.append("stale_processing_outbox_messages")
    if int(task_statuses.get("failed", 0)) > 0:
        warnings.append("failed_tasks")
    if int(task_statuses.get("blocked", 0)) > 0:
        warnings.append("blocked_tasks")
    if int(approval_statuses.get("pending", 0)) > 0:
        warnings.append("pending_approvals")
    if int(outbox_statuses.get("failed", 0)) > 0:
        warnings.append("retrying_outbox_messages")

    if blockers:
        return "blocked", blockers, warnings
    if warnings:
        return "degraded", blockers, warnings
    return "healthy", blockers, warnings


@router.get("/api/v1/runtime/health")
def get_runtime_health(
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.health")),
    db: Session = Depends(get_db),
):
    summary = SqlAlchemyUnitOfWork(db).runtime_health.summary(tenant_id=context.tenant_id)
    status, blockers, warnings = classify_runtime_health(summary)
    response = RuntimeHealthResponse(
        tenant_id=context.tenant_id,
        status=status,
        ready=status != "blocked",
        blockers=blockers,
        warnings=warnings,
        checked_at=datetime.now(timezone.utc),
        **summary,
    )
    return api_response(response.model_dump(mode="json"), request)
