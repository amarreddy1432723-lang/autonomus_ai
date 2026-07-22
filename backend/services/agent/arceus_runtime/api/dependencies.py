from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.arceus_core_models import ArceusRolePermission, ArceusTenant, ArceusTenantMembership, ArceusUser

from ...deps import get_current_user_id
from ..application.errors import InvalidIdempotencyKey, PermissionDenied
from ..identity.service import ROLE_DEFINITIONS


ALL_LOCAL_PERMISSIONS = frozenset(
    {
        "mission.create",
        "mission.view",
        "mission.compile",
        "mission.start",
        "mission.pause",
        "mission.plan",
        "planning.intelligence",
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
        "context.build",
        "model_registry.view",
        "model_registry.manage",
        "model.gateway",
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
        "billing.view",
        "billing.manage",
        "billing.meter",
        "billing.enforce",
        "admin.enterprise.view",
        "admin.enterprise.manage",
        "admin.identity.manage",
        "admin.access_review.manage",
        "admin.audit.export",
        "admin.support.manage",
        "admin.policy.manage",
        "admin.tenant.operate",
        "deployment.view",
        "deployment.manage",
        "deployment.plan",
        "deployment.execute",
        "deployment.rollback",
        "deployment.health",
        "deployment.drift",
        "environment.view",
        "environment.manage",
        "release.view",
        "release.manage",
        "infrastructure.plan",
        "infrastructure.apply",
        "infrastructure.drift",
        "model_execution.view",
        "tool_execution.view",
        "policy_evaluation.view",
        "event.replay",
        "usage.view",
        "runtime.health",
        "identity.view",
        "identity.authorize",
        "identity.session.evaluate",
        "identity.token.issue",
        "identity.service_account.create",
        "identity.agent.create",
        "identity.provider.sync",
        "identity.governance.view",
        "policy.view",
        "policy.manage",
        "telemetry.view",
        "telemetry.write",
        "telemetry.dashboard.view",
        "alert.view",
        "alert.manage",
        "incident.manage",
        "runtime.report",
        "runtime.execute",
        "runtime.schedule",
        "runtime.lease",
        "runtime.checkpoint",
        "approval.vote",
        "collaboration.view",
        "collaboration.manage",
        "collaboration.message",
        "collaboration.presence",
        "decision.create",
        "decision.approve",
        "review.create",
        "review.complete",
        "agent.register",
        "agent.view",
        "agent.manage",
        "agent.heartbeat",
        "agent.metrics.view",
        "agent.assign",
        "agent.message",
        "prompt.view",
        "prompt.compile",
        "prompt.validate",
        "prompt.manage",
        "task.view",
        "task.create",
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
        "security.ops.view",
        "security.ops.manage",
        "security.finding.write",
        "security.response.manage",
        "security.exception.approve",
        "security.evidence.write",
        "data.catalog.view",
        "data.catalog.manage",
        "data.contract.manage",
        "data.event.publish",
        "data.pipeline.view",
        "data.metric.view",
        "data.metric.manage",
        "data.metric.write",
        "data.quality.manage",
        "data.quality.write",
        "data.experiment.manage",
        "workspace.view",
        "workspace.create",
        "workspace.repository.manage",
        "project.view",
        "project.create",
        "project.manage",
        "operations.view",
        "operations.manage",
        "constitution.view",
        "constitution.evaluate",
        "organization.standards.view",
        "organization.fitness.view",
        "organization.lesson.propose",
        "reasoning.view",
        "evolution.simulate",
        "evolution.propose",
        "knowledge.view",
        "knowledge.create",
        "knowledge.search",
        "knowledge.index",
        "knowledge.impact",
        "repository.view",
        "repository.search",
        "repository.index",
        "product.view",
        "product.requirement.create",
        "product.experiment.create",
        "automation.view",
        "automation.trigger.create",
        "automation.template.create",
        "automation.execute",
        "experience.workspace.view",
        "experience.intent.view",
        "experience.intent.execute",
        "experience.timeline.view",
        "experience.dashboard.view",
        "experience.voice",
        "experience.search",
        "runtime.kernel.view",
        "runtime.kernel.manage",
        "runtime.kernel.lease",
        "runtime.kernel.checkpoint",
        "platform.view",
        "platform.manage",
        "marketplace.view",
        "extension.view",
        "extension.manage",
        "extension.install",
        "extension.invoke",
        "extension.publish",
        "extension.security.review",
        "platform.federation",
        "learning.view",
        "learning.record.create",
        "learning.promote",
        "learning.evaluate",
        "strategy.view",
        "strategy.objective.create",
        "strategy.simulate",
        "strategy.decision.record",
        "kernel.view",
        "kernel.events.view",
        "kernel.validate",
        "kernel.replay",
        "compute.view",
        "compute.plan",
        "compute.schedule",
        "compute.infer",
        "graph.view",
        "graph.query",
        "graph.search",
        "graph.sync",
        "governance.view",
        "governance.model.view",
        "governance.policy.view",
        "governance.evaluate",
        "governance.approve",
        "governance.compliance.view",
        "governance.audit.view",
        "memory.create",
        "memory.approve",
        "memory.view",
        "memory.store",
        "memory.search",
        "memory.summarize",
        "memory.archive",
        "memory.delete",
        "research.project.create",
        "research.hypothesis.create",
        "research.experiment.create",
        "research.findings.view",
        "research.publish",
        "research.innovation.view",
        "federation.create",
        "federation.join",
        "federation.delegate",
        "federation.view",
        "federation.knowledge.share",
        "federation.resources.negotiate",
        "civilization.view",
        "civilization.evolve",
        "civilization.propose",
        "civilization.metrics.view",
        "civilization.simulate",
        "civilization.constitution.view",
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


def _role_permissions(db: Session, role_keys: frozenset[str]) -> frozenset[str]:
    builtin = {role.role_key: set(role.permissions) for role in ROLE_DEFINITIONS}
    permissions: set[str] = set()
    for role_key in role_keys:
        permissions.update(builtin.get(role_key, set()))
    persisted = (
        db.query(ArceusRolePermission)
        .filter(ArceusRolePermission.role_key.in_(list(role_keys)), ArceusRolePermission.active.is_(True))
        .all()
        if role_keys
        else []
    )
    permissions.update(item.permission_key for item in persisted)
    return frozenset(permissions)


def _tenant_slug_from_request(request: Request) -> str:
    clerk_org_id = request.headers.get("x-clerk-org-id") or request.headers.get("x-organization-id")
    if clerk_org_id:
        return f"clerk-{clerk_org_id}".lower().replace("_", "-")[:240]
    return "default"


def _ensure_runtime_identity(db: Session, user_id: UUID, request: Request) -> tuple[ArceusTenant, ArceusUser, ArceusTenantMembership]:
    tenant_slug = _tenant_slug_from_request(request)
    tenant_name = request.headers.get("x-organization-name") or ("Default Tenant" if tenant_slug == "default" else tenant_slug)
    tenant = db.query(ArceusTenant).filter(ArceusTenant.slug == tenant_slug).first()
    if tenant is None:
        tenant = ArceusTenant(
            name=tenant_name,
            slug=tenant_slug,
            status="active",
            plan_key="local",
            settings={
                "clerk_org_id": request.headers.get("x-clerk-org-id"),
                "enterprise_sso": request.headers.get("x-enterprise-sso") in {"1", "true", "yes"},
                "scim_enabled": request.headers.get("x-scim-enabled") in {"1", "true", "yes"},
            },
        )
        db.add(tenant)
        db.flush()

    external_identity_id = request.headers.get("x-clerk-user-id") or f"legacy:{user_id}"
    user = db.query(ArceusUser).filter(ArceusUser.external_identity_id == external_identity_id).first()
    if user is None:
        user = ArceusUser(
            id=user_id,
            external_identity_id=external_identity_id,
            email=request.headers.get("x-user-email") or f"{user_id}@local.arceus",
            display_name=request.headers.get("x-user-name") or "Local User",
            status="active",
            preferences={
                "clerk_session_id": request.headers.get("x-clerk-session-id"),
                "device_trust": request.headers.get("x-device-trusted") in {"1", "true", "yes"},
            },
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
    tenant, user, membership = _ensure_runtime_identity(db, user_id, request)
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
        permissions=_role_permissions(db, frozenset({membership.role_key})),
        client_type=request.headers.get("x-client-type", "api"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def require_permission(permission: str):
    def dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if "*" not in context.permissions and permission not in context.permissions:
            raise PermissionDenied("Permission denied.", details={"permission": permission})
        return context

    return dependency


def require_idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    value = (idempotency_key or "").strip()
    if not value or len(value) > 128:
        raise InvalidIdempotencyKey("A valid Idempotency-Key header is required.")
    return value
