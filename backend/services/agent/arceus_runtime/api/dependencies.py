from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.arceus_core_models import ArceusTenant, ArceusTenantMembership, ArceusUser

from ...deps import get_current_user_id
from ..application.errors import InvalidIdempotencyKey, PermissionDenied


ALL_LOCAL_PERMISSIONS = frozenset(
    {
        "mission.create",
        "mission.view",
        "mission.compile",
        "mission.start",
        "mission.pause",
        "mission.plan",
        "mission.resume",
        "mission.cancel",
        "mission.clarify",
        "mission.approve_plan",
        "approval.view",
        "artifact.view",
        "evidence.view",
        "verification.view",
        "verification.manage",
        "evidence.collect",
        "completion.view",
        "completion.approve",
        "decision.view",
        "organization.view",
        "capability.view",
        "compiler.view",
        "context.view",
        "model_registry.view",
        "model_registry.manage",
        "provider_registry.view",
        "provider_registry.manage",
        "tool_registry.view",
        "tool_registry.manage",
        "ai.route",
        "ai.execute",
        "tool.authorize",
        "tool.execute",
        "budget.view",
        "budget.manage",
        "model_execution.view",
        "tool_execution.view",
        "policy_evaluation.view",
        "event.replay",
        "usage.view",
        "runtime.health",
        "runtime.schedule",
        "runtime.lease",
        "runtime.checkpoint",
        "approval.vote",
        "task.view",
        "task.retry",
        "task.skip",
        "workflow.retry",
        "workflow.skip",
        "audit.view",
        "security.policy.view",
        "security.evaluate",
        "security.audit.view",
        "security.incident.create",
        "security.compliance.view",
        "workspace.view",
        "workspace.create",
        "workspace.repository.manage",
    }
)


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    correlation_id: UUID
    tenant_id: UUID
    user_id: UUID
    membership_id: UUID
    role_keys: frozenset[str]
    permissions: frozenset[str]
    client_type: str
    ip_address: str | None
    user_agent: str | None


def _ensure_runtime_identity(db: Session, user_id: UUID) -> tuple[ArceusTenant, ArceusUser, ArceusTenantMembership]:
    tenant = db.query(ArceusTenant).filter(ArceusTenant.slug == "default").first()
    if tenant is None:
        tenant = ArceusTenant(name="Default Tenant", slug="default", status="active", plan_key="local")
        db.add(tenant)
        db.flush()

    external_identity_id = f"legacy:{user_id}"
    user = db.query(ArceusUser).filter(ArceusUser.external_identity_id == external_identity_id).first()
    if user is None:
        user = ArceusUser(
            id=user_id,
            external_identity_id=external_identity_id,
            email=f"{user_id}@local.arceus",
            display_name="Local User",
            status="active",
        )
        db.add(user)
        db.flush()

    membership = (
        db.query(ArceusTenantMembership)
        .filter(ArceusTenantMembership.tenant_id == tenant.id, ArceusTenantMembership.user_id == user.id)
        .first()
    )
    if membership is None:
        membership = ArceusTenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role_key="owner",
            status="active",
        )
        db.add(membership)
        db.flush()

    db.commit()
    return tenant, user, membership


def get_request_context(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RequestContext:
    tenant, user, membership = _ensure_runtime_identity(db, user_id)
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
    correlation_id = getattr(request.state, "correlation_id", None) or uuid.uuid4()
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    return RequestContext(
        request_id=request_id,
        correlation_id=correlation_id,
        tenant_id=tenant.id,
        user_id=user.id,
        membership_id=membership.id,
        role_keys=frozenset({membership.role_key}),
        permissions=ALL_LOCAL_PERMISSIONS,
        client_type=request.headers.get("x-client-type", "api"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def require_permission(permission: str):
    def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if permission not in context.permissions:
            raise PermissionDenied("Permission denied.", details={"permission": permission})
        return context

    return dependency


def require_idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    value = (idempotency_key or "").strip()
    if not value or len(value) > 128:
        raise InvalidIdempotencyKey("A valid Idempotency-Key header is required.")
    return value
