from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusDeploymentApplication,
    ArceusDeploymentArtifact,
    ArceusDeploymentDriftReport,
    ArceusDeploymentEnvironment,
    ArceusDeploymentHealthCheck,
    ArceusDeploymentPlan,
    ArceusDeploymentRelease,
    ArceusDeploymentRequest,
    ArceusDeploymentRollback,
    ArceusDeploymentTarget,
    ArceusRuntimeProfile,
)

from ..compiler.utils import stable_hash
from .api_schemas import (
    DeploymentApplicationRequest,
    DeploymentArtifactRequest,
    DeploymentEnvironmentRequest,
    DeploymentPlanResponse,
    DeploymentReleaseRequest,
    DeploymentRequestCreate,
    DeploymentTargetRequest,
    DriftReportRequest,
    HealthCheckRequest,
    RollbackRequest,
    RuntimeProfileRequest,
)


PROVIDER_CAPABILITIES: dict[str, dict[str, bool]] = {
    "railway": {"containers": True, "serverless": False, "staticHosting": True, "managedDatabases": True, "managedRedis": True, "customDomains": True, "blueGreen": False, "canary": False, "logStreaming": True, "metrics": True, "secretManagement": True},
    "vercel": {"containers": False, "serverless": True, "staticHosting": True, "managedDatabases": False, "managedRedis": False, "customDomains": True, "blueGreen": False, "canary": True, "logStreaming": True, "metrics": True, "secretManagement": True},
    "render": {"containers": True, "serverless": False, "staticHosting": True, "managedDatabases": True, "managedRedis": True, "customDomains": True, "blueGreen": False, "canary": False, "logStreaming": True, "metrics": True, "secretManagement": True},
    "docker": {"containers": True, "serverless": False, "staticHosting": False, "managedDatabases": False, "managedRedis": False, "customDomains": False, "blueGreen": False, "canary": False, "logStreaming": True, "metrics": False, "secretManagement": False},
    "kubernetes": {"containers": True, "serverless": False, "staticHosting": True, "managedDatabases": False, "managedRedis": False, "customDomains": True, "blueGreen": True, "canary": True, "logStreaming": True, "metrics": True, "secretManagement": True},
}

PRODUCTION_STRATEGIES = {"rolling", "blue_green", "canary", "immutable"}


def create_target(db: Session, *, tenant_id: UUID, payload: DeploymentTargetRequest) -> ArceusDeploymentTarget:
    capabilities = {**PROVIDER_CAPABILITIES.get(payload.provider_type, {}), **payload.capabilities}
    target = ArceusDeploymentTarget(tenant_id=tenant_id, capabilities=capabilities, **payload.model_dump(exclude={"capabilities"}))
    db.add(target)
    db.flush()
    return target


def create_runtime_profile(db: Session, *, tenant_id: UUID, payload: RuntimeProfileRequest) -> ArceusRuntimeProfile:
    item = ArceusRuntimeProfile(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def create_application(db: Session, *, tenant_id: UUID, payload: DeploymentApplicationRequest) -> ArceusDeploymentApplication:
    slug = unique_slug(db, ArceusDeploymentApplication, tenant_id=tenant_id, project_id=payload.project_id, value=payload.name)
    item = ArceusDeploymentApplication(tenant_id=tenant_id, slug=slug, metadata_json=payload.metadata, **payload.model_dump(exclude={"metadata"}))
    db.add(item)
    db.flush()
    return item


def create_environment(db: Session, *, tenant_id: UUID, payload: DeploymentEnvironmentRequest) -> ArceusDeploymentEnvironment:
    target = db.query(ArceusDeploymentTarget).filter(ArceusDeploymentTarget.tenant_id == tenant_id, ArceusDeploymentTarget.id == payload.target_id).first()
    if target is None:
        raise ValueError("DEPLOYMENT_TARGET_NOT_FOUND")
    status = "ready" if target.status == "active" else "failed"
    item = ArceusDeploymentEnvironment(tenant_id=tenant_id, status=status, metadata_json=payload.metadata, **payload.model_dump(exclude={"metadata"}))
    db.add(item)
    db.flush()
    return item


def create_release(db: Session, *, tenant_id: UUID, payload: DeploymentReleaseRequest) -> ArceusDeploymentRelease:
    item = ArceusDeploymentRelease(tenant_id=tenant_id, status="draft", provenance=payload.provenance, **payload.model_dump(exclude={"provenance"}))
    db.add(item)
    db.flush()
    return item


def attach_artifact(db: Session, *, tenant_id: UUID, payload: DeploymentArtifactRequest) -> ArceusDeploymentArtifact:
    item = ArceusDeploymentArtifact(tenant_id=tenant_id, metadata_json=payload.metadata, **payload.model_dump(exclude={"metadata"}))
    db.add(item)
    db.flush()
    release = db.query(ArceusDeploymentRelease).filter(ArceusDeploymentRelease.tenant_id == tenant_id, ArceusDeploymentRelease.id == payload.release_id).first()
    if release:
        artifact_ids = list(release.artifact_ids or [])
        if str(item.id) not in artifact_ids:
            release.artifact_ids = [*artifact_ids, str(item.id)]
    return item


def create_deployment_request(db: Session, *, tenant_id: UUID, payload: DeploymentRequestCreate) -> ArceusDeploymentRequest:
    item = ArceusDeploymentRequest(tenant_id=tenant_id, status="requested", **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def plan_deployment(db: Session, *, tenant_id: UUID, deployment_request_id: UUID, persist: bool = True) -> DeploymentPlanResponse:
    request = db.query(ArceusDeploymentRequest).filter(ArceusDeploymentRequest.tenant_id == tenant_id, ArceusDeploymentRequest.id == deployment_request_id).first()
    if request is None:
        raise ValueError("DEPLOYMENT_REQUEST_NOT_FOUND")
    release = db.query(ArceusDeploymentRelease).filter(ArceusDeploymentRelease.tenant_id == tenant_id, ArceusDeploymentRelease.id == request.release_id).first()
    environment = db.query(ArceusDeploymentEnvironment).filter(ArceusDeploymentEnvironment.tenant_id == tenant_id, ArceusDeploymentEnvironment.id == request.environment_id).first()
    if release is None or environment is None:
        raise ValueError("DEPLOYMENT_SUBJECT_NOT_FOUND")
    target = db.query(ArceusDeploymentTarget).filter(ArceusDeploymentTarget.tenant_id == tenant_id, ArceusDeploymentTarget.id == environment.target_id).first()
    artifacts = db.query(ArceusDeploymentArtifact).filter(ArceusDeploymentArtifact.tenant_id == tenant_id, ArceusDeploymentArtifact.release_id == release.id).all()
    warnings: list[str] = []
    blockers: list[str] = []
    env_type = environment.environment_type
    capabilities = target.capabilities if target else {}
    if environment.status not in {"ready", "degraded"}:
        blockers.append("Target environment is not ready.")
    if env_type == "production" and request.strategy not in PRODUCTION_STRATEGIES:
        blockers.append("Production deployments require rolling, blue-green, canary, or immutable strategy.")
    if request.strategy == "blue_green" and not capabilities.get("blueGreen"):
        warnings.append("Provider does not advertise native blue-green support; manual routing may be required.")
    if request.strategy == "canary" and not capabilities.get("canary"):
        blockers.append("Selected provider target does not support canary deployment.")
    if env_type == "production" and release.status not in {"approved", "deployable"}:
        blockers.append("Production release must be approved or deployable.")
    if not artifacts:
        blockers.append("Release has no deployment artifacts.")
    unsigned = [artifact for artifact in artifacts if not artifact.signed]
    failed_scans = [artifact for artifact in artifacts if artifact.scan_status in {"failed", "pending"}]
    if env_type == "production" and unsigned:
        blockers.append("Production deployment requires signed artifacts.")
    if env_type == "production" and failed_scans:
        blockers.append("Production deployment requires completed artifact security scans.")
    if release.provenance and not release.provenance.get("builder_trusted", True):
        blockers.append("Release provenance was produced by an untrusted builder.")
    migration_plan = migration_plan_for(release.provenance or {}, env_type=env_type)
    if migration_plan["risk"] == "critical":
        blockers.append("Critical database migration requires a separate backup and human approval.")
    elif migration_plan["risk"] == "high":
        warnings.append("Database migration should be reviewed before deployment.")
    risk_score = risk_score_for(environment=environment, strategy=request.strategy, artifacts=artifacts, migration_plan=migration_plan, blockers=blockers, warnings=warnings)
    traffic_plan = traffic_plan_for(strategy=request.strategy, environment_type=env_type)
    rollback_plan = rollback_plan_for(environment=environment, release=release, artifacts=artifacts)
    if env_type == "production" and not rollback_plan["available"]:
        blockers.append("Production deployment requires a rollback release or retained previous release.")
    payload = {
        "request_id": str(request.id),
        "release_id": str(release.id),
        "environment_id": str(environment.id),
        "strategy": request.strategy,
        "artifact_digests": [artifact.digest for artifact in artifacts],
        "traffic_plan": traffic_plan,
        "rollback_plan": rollback_plan,
        "blockers": blockers,
        "warnings": warnings,
    }
    plan_hash = stable_hash(payload)
    estimated_cost = estimate_cost_cents(strategy=request.strategy, environment_type=env_type, artifact_count=len(artifacts))
    response = DeploymentPlanResponse(
        request_id=request.id,
        release_id=release.id,
        environment_id=environment.id,
        strategy=request.strategy,
        infrastructure_changes=infrastructure_changes_for(target=target, environment=environment),
        configuration_changes=configuration_changes_for(release=release, environment=environment),
        secret_binding_changes=secret_changes_for(environment=environment),
        migration_plan=migration_plan,
        traffic_plan=traffic_plan,
        health_verification_plan=health_plan_for(environment=environment, release=release),
        rollback_plan=rollback_plan,
        estimated_duration_seconds=duration_for(request.strategy, env_type),
        estimated_cost_cents=estimated_cost,
        risk_score=risk_score,
        warnings=warnings,
        blockers=blockers,
        deployable=not blockers,
        plan_hash=plan_hash,
    )
    if persist:
        request.status = "awaiting_approval" if response.deployable and env_type == "production" else "queued" if response.deployable else "planning"
        db_plan = ArceusDeploymentPlan(
            tenant_id=tenant_id,
            request_id=request.id,
            release_id=release.id,
            environment_id=environment.id,
            strategy=request.strategy,
            infrastructure_changes=response.infrastructure_changes,
            configuration_changes=response.configuration_changes,
            secret_binding_changes=response.secret_binding_changes,
            migration_plan=response.migration_plan,
            traffic_plan=response.traffic_plan,
            health_verification_plan=response.health_verification_plan,
            rollback_plan=response.rollback_plan,
            estimated_duration_seconds=response.estimated_duration_seconds,
            estimated_cost_cents=response.estimated_cost_cents,
            risk_score=response.risk_score,
            warnings=response.warnings,
            blockers=response.blockers,
            plan_hash=response.plan_hash,
        )
        db.add(db_plan)
        db.flush()
        response.id = db_plan.id
    return response


def record_health_check(db: Session, *, tenant_id: UUID, payload: HealthCheckRequest) -> ArceusDeploymentHealthCheck:
    item = ArceusDeploymentHealthCheck(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def create_rollback(db: Session, *, tenant_id: UUID, payload: RollbackRequest) -> ArceusDeploymentRollback:
    steps = payload.rollback_steps or [
        {"order": 1, "action": "stop_new_release"},
        {"order": 2, "action": "restore_previous_release"},
        {"order": 3, "action": "verify_health"},
    ]
    item = ArceusDeploymentRollback(tenant_id=tenant_id, rollback_steps=steps, **payload.model_dump(exclude={"rollback_steps"}))
    db.add(item)
    db.flush()
    return item


def record_drift(db: Session, *, tenant_id: UUID, payload: DriftReportRequest) -> ArceusDeploymentDriftReport:
    status = "resolved" if payload.desired_hash == payload.actual_hash else "open"
    item = ArceusDeploymentDriftReport(tenant_id=tenant_id, status=status, **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def health_summary(db: Session, *, tenant_id: UUID, environment_id: UUID) -> dict[str, Any]:
    environment = db.query(ArceusDeploymentEnvironment).filter(ArceusDeploymentEnvironment.tenant_id == tenant_id, ArceusDeploymentEnvironment.id == environment_id).first()
    if environment is None:
        raise ValueError("DEPLOYMENT_ENVIRONMENT_NOT_FOUND")
    failed_checks = db.query(ArceusDeploymentHealthCheck).filter(ArceusDeploymentHealthCheck.tenant_id == tenant_id, ArceusDeploymentHealthCheck.environment_id == environment_id, ArceusDeploymentHealthCheck.status == "failed").count()
    warning_checks = db.query(ArceusDeploymentHealthCheck).filter(ArceusDeploymentHealthCheck.tenant_id == tenant_id, ArceusDeploymentHealthCheck.environment_id == environment_id, ArceusDeploymentHealthCheck.status == "warning").count()
    drift = db.query(ArceusDeploymentDriftReport).filter(ArceusDeploymentDriftReport.tenant_id == tenant_id, ArceusDeploymentDriftReport.environment_id == environment_id, ArceusDeploymentDriftReport.status == "open").count()
    rollback_available = bool(environment.current_release_id)
    blockers = []
    if failed_checks:
        blockers.append("Deployment health checks are failing.")
    if drift:
        blockers.append("Open environment drift must be accepted or resolved.")
    status = "failed" if failed_checks else "degraded" if warning_checks or drift else environment.status
    return {
        "environment_id": environment_id,
        "status": status,
        "last_release_id": environment.current_release_id,
        "failed_checks": failed_checks,
        "warning_checks": warning_checks,
        "open_drift_reports": drift,
        "rollback_available": rollback_available,
        "blockers": blockers,
    }


def migration_plan_for(provenance: dict[str, Any], *, env_type: str) -> dict[str, Any]:
    migration = provenance.get("migration") or provenance.get("database_migration") or {}
    if not migration:
        return {"required": False, "risk": "none", "backup_required": False, "rollback_supported": True}
    destructive = bool(migration.get("destructive") or migration.get("data_loss_risk"))
    locks = bool(migration.get("locks_tables"))
    risk = "critical" if destructive and env_type == "production" else "high" if destructive or locks else "medium"
    return {"required": True, "risk": risk, "backup_required": env_type == "production", "rollback_supported": bool(migration.get("rollback_supported", not destructive))}


def traffic_plan_for(*, strategy: str, environment_type: str) -> dict[str, Any]:
    if strategy == "canary":
        stages = [
            {"order": 1, "newReleasePercentage": 5, "minimumDurationSeconds": 300, "manualApprovalRequired": environment_type == "production"},
            {"order": 2, "newReleasePercentage": 25, "minimumDurationSeconds": 600, "manualApprovalRequired": False},
            {"order": 3, "newReleasePercentage": 100, "minimumDurationSeconds": 300, "manualApprovalRequired": False},
        ]
    elif strategy == "blue_green":
        stages = [{"order": 1, "newReleasePercentage": 0, "minimumDurationSeconds": 300, "manualApprovalRequired": True}, {"order": 2, "newReleasePercentage": 100, "minimumDurationSeconds": 60, "manualApprovalRequired": environment_type == "production"}]
    else:
        stages = [{"order": 1, "newReleasePercentage": 100, "minimumDurationSeconds": 60, "manualApprovalRequired": environment_type == "production"}]
    return {"stages": stages, "rollbackOnViolation": True, "maximumErrorRateIncrease": 1.0, "maximumLatencyIncreasePercent": 20}


def rollback_plan_for(*, environment: ArceusDeploymentEnvironment, release: ArceusDeploymentRelease, artifacts: list[ArceusDeploymentArtifact]) -> dict[str, Any]:
    return {
        "available": bool(environment.current_release_id) or release.status in {"approved", "deployable"},
        "previous_release_id": str(environment.current_release_id) if environment.current_release_id else None,
        "artifact_digests": [item.digest for item in artifacts],
        "steps": ["retain previous release", "shift traffic back", "verify health", "mark release rolled back"],
    }


def infrastructure_changes_for(*, target: ArceusDeploymentTarget | None, environment: ArceusDeploymentEnvironment) -> list[dict[str, Any]]:
    changes = [{"kind": "environment", "action": "ensure", "name": environment.name, "provider": target.provider_type if target else "unknown"}]
    if environment.environment_type == "preview":
        changes.append({"kind": "ttl", "action": "configure", "expires_at": environment.ttl_expires_at.isoformat() if environment.ttl_expires_at else None})
    return changes


def configuration_changes_for(*, release: ArceusDeploymentRelease, environment: ArceusDeploymentEnvironment) -> list[dict[str, Any]]:
    return [{"kind": "release_version", "action": "set", "value": release.version}, {"kind": "environment", "action": "bind", "value": environment.environment_type}]


def secret_changes_for(*, environment: ArceusDeploymentEnvironment) -> list[dict[str, Any]]:
    refs = (environment.metadata_json or {}).get("secret_refs") or []
    return [{"kind": "secret_binding", "action": "verify_reference", "secret_ref": ref} for ref in refs]


def health_plan_for(*, environment: ArceusDeploymentEnvironment, release: ArceusDeploymentRelease) -> dict[str, Any]:
    return {"checks": [{"type": "http", "target": (environment.metadata_json or {}).get("health_url", "/health"), "required": True}], "release_version": release.version}


def estimate_cost_cents(*, strategy: str, environment_type: str, artifact_count: int) -> Decimal:
    base = Decimal("25") + Decimal(artifact_count * 5)
    if environment_type == "production":
        base += Decimal("100")
    if strategy in {"blue_green", "canary", "shadow"}:
        base += Decimal("75")
    return base.quantize(Decimal("0.000001"))


def duration_for(strategy: str, environment_type: str) -> int:
    base = 180 if environment_type != "production" else 600
    return base + {"recreate": 60, "rolling": 180, "blue_green": 300, "canary": 900, "shadow": 600, "immutable": 240, "in_place": 120}.get(strategy, 180)


def risk_score_for(*, environment: ArceusDeploymentEnvironment, strategy: str, artifacts: list[ArceusDeploymentArtifact], migration_plan: dict[str, Any], blockers: list[str], warnings: list[str]) -> int:
    score = 10
    if environment.environment_type == "production":
        score += 30
    if environment.protection_level in {"protected", "critical"}:
        score += 15
    if strategy in {"recreate", "in_place"}:
        score += 15
    if migration_plan.get("risk") == "high":
        score += 15
    if migration_plan.get("risk") == "critical":
        score += 30
    score += len([artifact for artifact in artifacts if not artifact.signed]) * 10
    score += len(warnings) * 5 + len(blockers) * 20
    return min(100, score)


def unique_slug(db: Session, model, *, tenant_id: UUID, value: str, project_id: UUID | None = None) -> str:
    base = slug(value)
    candidate = base
    index = 2
    while True:
        query = db.query(model).filter(model.tenant_id == tenant_id, model.slug == candidate)
        if project_id is not None:
            query = query.filter(model.project_id == project_id)
        if query.first() is None:
            return candidate
        candidate = f"{base}-{index}"
        index += 1


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "application"

