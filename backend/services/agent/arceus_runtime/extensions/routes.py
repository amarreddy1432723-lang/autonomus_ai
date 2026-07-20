from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusPlugin,
    ArceusPluginInstallation,
    ArceusPluginInstallationPermission,
    ArceusPluginInvocation,
    ArceusPluginPublisher,
    ArceusPluginSecurityFinding,
    ArceusPluginUsageEvent,
    ArceusPluginVersion,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from .api_schemas import (
    ExtensionPermission,
    ManifestValidationRequest,
    ManifestValidationResponse,
    MarketplaceListingResponse,
    PluginLifecycleResponse,
    PermissionEvaluationRequest,
    PermissionEvaluationResponse,
    PluginInstallRequest,
    PluginInstallationResponse,
    PluginInvocationRequest,
    PluginInvocationResponse,
    PluginRuntimePolicyResponse,
    PluginSecretUseRequest,
    PluginSecretUseResponse,
    PluginUpdateRequest,
    SdkManifestResponse,
)
from .service import (
    OFFICIAL_MARKETPLACE,
    evaluate_permission_grants,
    extension_identity,
    broker_secret_use,
    invocation_receipt,
    payload_fingerprint,
    runtime_policy_for_manifest,
    sdk_manifest,
    stable_json_digest,
    validate_plugin_manifest,
)


router = APIRouter(prefix="/api/v1/extensions", tags=["arceus-extensions"])


@router.get("/marketplace", response_model=list[MarketplaceListingResponse])
def list_marketplace(_: RequestContext = Depends(require_permission("marketplace.view"))) -> list[MarketplaceListingResponse]:
    return [MarketplaceListingResponse(**item) for item in OFFICIAL_MARKETPLACE]


@router.get("/sdk/manifest", response_model=SdkManifestResponse)
def extension_sdk_manifest(_: RequestContext = Depends(require_permission("extension.view"))) -> SdkManifestResponse:
    return SdkManifestResponse(**sdk_manifest())


@router.post("/manifests/validate", response_model=ManifestValidationResponse)
def validate_manifest(
    payload: ManifestValidationRequest,
    _: RequestContext = Depends(require_permission("extension.view")),
) -> ManifestValidationResponse:
    return validate_plugin_manifest(payload.manifest, payload.package_digest)


@router.post("/installations", response_model=PluginInstallationResponse)
def install_extension(
    payload: PluginInstallRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.install")),
) -> PluginInstallationResponse:
    validation = validate_plugin_manifest(payload.manifest)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"errors": validation.errors, "warnings": validation.warnings})

    normalized = validation.normalized_manifest
    publisher = _get_or_create_publisher(db, context, normalized["publisher"])
    plugin = _get_or_create_plugin(db, context, publisher.id, validation)
    version = _get_or_create_version(db, plugin.id, validation)
    plugin.latest_version_id = version.id
    if validation.verified and not validation.review_required:
        plugin.status = "published"

    scope_id = payload.scope_id or str(context.tenant_id)
    installation = (
        db.query(ArceusPluginInstallation)
        .filter(
            ArceusPluginInstallation.tenant_id == context.tenant_id,
            ArceusPluginInstallation.plugin_id == plugin.id,
            ArceusPluginInstallation.scope_type == payload.scope_type,
            ArceusPluginInstallation.scope_id == scope_id,
        )
        .first()
    )
    status = "pending_review" if validation.review_required else "installed"
    if installation is None:
        installation = ArceusPluginInstallation(
            tenant_id=context.tenant_id,
            plugin_id=plugin.id,
            plugin_version_id=version.id,
            scope_type=payload.scope_type,
            scope_id=scope_id,
            status=status,
            installed_by=context.user_id,
            update_policy=payload.update_policy,
            configuration=payload.configuration,
            secret_references=payload.secret_references,
            extension_identity_id=extension_identity(str(validation.plugin_key), payload.scope_type, scope_id),
            last_health={"status": "not_checked"},
        )
        db.add(installation)
        db.flush()
    else:
        installation.plugin_version_id = version.id
        installation.status = status
        installation.update_policy = payload.update_policy
        installation.configuration = payload.configuration
        installation.secret_references = payload.secret_references

    db.query(ArceusPluginInstallationPermission).filter(
        ArceusPluginInstallationPermission.installation_id == installation.id
    ).delete()
    grants = payload.granted_permissions if payload.granted_permissions is not None else validation.permissions
    for grant in grants:
        db.add(
            ArceusPluginInstallationPermission(
                installation_id=installation.id,
                permission_key=grant.permission,
                scope=grant.scope,
                conditions=grant.conditions,
                risk_level=grant.risk_level,
                granted_by=context.user_id,
            )
        )
    db.commit()
    db.refresh(installation)
    return _installation_response(db, installation, validation)


@router.get("/installations", response_model=list[PluginInstallationResponse])
def list_installations(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.view")),
) -> list[PluginInstallationResponse]:
    rows = (
        db.query(ArceusPluginInstallation)
        .filter(ArceusPluginInstallation.tenant_id == context.tenant_id, ArceusPluginInstallation.status != "removed")
        .order_by(ArceusPluginInstallation.created_at.desc())
        .limit(100)
        .all()
    )
    return [_installation_response(db, row) for row in rows]


@router.post("/installations/{installation_id}/enable", response_model=PluginInstallationResponse)
def enable_installation(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.manage")),
) -> PluginInstallationResponse:
    installation = _get_installation(db, context, installation_id)
    blocking_findings = (
        db.query(ArceusPluginSecurityFinding)
        .filter(
            ArceusPluginSecurityFinding.plugin_version_id == installation.plugin_version_id,
            ArceusPluginSecurityFinding.blocking.is_(True),
            ArceusPluginSecurityFinding.status.in_(["open", "acknowledged"]),
        )
        .count()
    )
    version = db.query(ArceusPluginVersion).filter(ArceusPluginVersion.id == installation.plugin_version_id).first()
    if blocking_findings:
        raise HTTPException(status_code=409, detail={"message": "Blocking plugin security findings must be resolved first."})
    if not version or not version.signature:
        raise HTTPException(status_code=409, detail={"message": "Unsigned plugin versions cannot be enabled."})
    installation.status = "enabled"
    installation.enabled_at = datetime.now(timezone.utc)
    installation.disabled_at = None
    db.commit()
    db.refresh(installation)
    return _installation_response(db, installation)


@router.post("/installations/{installation_id}/disable", response_model=PluginInstallationResponse)
def disable_installation(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.manage")),
) -> PluginInstallationResponse:
    installation = _get_installation(db, context, installation_id)
    installation.status = "disabled"
    installation.disabled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(installation)
    return _installation_response(db, installation)


@router.post("/installations/{installation_id}/health", response_model=PluginLifecycleResponse)
def check_installation_health(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.view")),
) -> PluginLifecycleResponse:
    installation = _get_installation(db, context, installation_id)
    version = db.query(ArceusPluginVersion).filter(ArceusPluginVersion.id == installation.plugin_version_id).first()
    blocking_findings = (
        db.query(ArceusPluginSecurityFinding)
        .filter(
            ArceusPluginSecurityFinding.plugin_version_id == installation.plugin_version_id,
            ArceusPluginSecurityFinding.blocking.is_(True),
            ArceusPluginSecurityFinding.status.in_(["open", "acknowledged"]),
        )
        .count()
    )
    health = {
        "status": "unhealthy" if blocking_findings else "healthy",
        "version": version.version if version else "unknown",
        "blocking_security_findings": blocking_findings,
        "enabled": installation.status == "enabled",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    installation.last_health = health
    db.commit()
    return PluginLifecycleResponse(installation_id=installation.id, status=installation.status, message="Health check recorded.", health=health)


@router.post("/installations/{installation_id}/update", response_model=PluginInstallationResponse)
def update_installation(
    installation_id: UUID,
    payload: PluginUpdateRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.manage")),
) -> PluginInstallationResponse:
    installation = _get_installation(db, context, installation_id)
    validation = validate_plugin_manifest(payload.manifest)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"errors": validation.errors, "warnings": validation.warnings})
    current_grants = {grant["permission"] for grant in _permission_grants(db, installation.id)}
    requested_grants = {grant.permission for grant in (payload.granted_permissions or validation.permissions)}
    added_permissions = sorted(requested_grants - current_grants)
    if added_permissions and not payload.allow_new_permissions:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Plugin update requests new permissions. Review the permission diff before updating.",
                "permission_diff": {"added": added_permissions, "removed": sorted(current_grants - requested_grants)},
            },
        )
    plugin = db.query(ArceusPlugin).filter(ArceusPlugin.id == installation.plugin_id).first()
    if plugin is None:
        raise HTTPException(status_code=404, detail={"message": "Plugin not found."})
    version = _get_or_create_version(db, plugin.id, validation)
    plugin.latest_version_id = version.id
    installation.plugin_version_id = version.id
    installation.status = "pending_review" if validation.review_required else "installed"
    if payload.granted_permissions is not None or added_permissions:
        db.query(ArceusPluginInstallationPermission).filter(
            ArceusPluginInstallationPermission.installation_id == installation.id
        ).delete()
        for grant in payload.granted_permissions or validation.permissions:
            db.add(
                ArceusPluginInstallationPermission(
                    installation_id=installation.id,
                    permission_key=grant.permission,
                    scope=grant.scope,
                    conditions=grant.conditions,
                    risk_level=grant.risk_level,
                    granted_by=context.user_id,
                )
            )
    db.commit()
    db.refresh(installation)
    return _installation_response(db, installation, validation)


@router.post("/installations/{installation_id}/remove", response_model=PluginLifecycleResponse)
def remove_installation(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.manage")),
) -> PluginLifecycleResponse:
    installation = _get_installation(db, context, installation_id)
    installation.status = "removed"
    installation.disabled_at = datetime.now(timezone.utc)
    for grant in db.query(ArceusPluginInstallationPermission).filter(ArceusPluginInstallationPermission.installation_id == installation.id).all():
        grant.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return PluginLifecycleResponse(installation_id=installation.id, status=installation.status, message="Extension removed and permission grants revoked.")


@router.get("/installations/{installation_id}/security-findings")
def list_installation_security_findings(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.security.review")),
):
    installation = _get_installation(db, context, installation_id)
    rows = (
        db.query(ArceusPluginSecurityFinding)
        .filter(ArceusPluginSecurityFinding.plugin_version_id == installation.plugin_version_id)
        .order_by(ArceusPluginSecurityFinding.created_at.desc())
        .all()
    )
    return [
        {
            "finding_id": str(row.id),
            "severity": row.severity,
            "category": row.category,
            "title": row.title,
            "description": row.description,
            "blocking": row.blocking,
            "status": row.status,
            "rule_id": row.rule_id,
        }
        for row in rows
    ]


@router.get("/installations/{installation_id}/runtime-policy", response_model=PluginRuntimePolicyResponse)
def get_runtime_policy(
    installation_id: UUID,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.view")),
) -> PluginRuntimePolicyResponse:
    installation = _get_installation(db, context, installation_id)
    version = db.query(ArceusPluginVersion).filter(ArceusPluginVersion.id == installation.plugin_version_id).first()
    manifest = version.manifest if version else {}
    return runtime_policy_for_manifest(manifest, installation_id=installation.id)


@router.post("/secrets/use", response_model=PluginSecretUseResponse)
def request_secret_use(
    payload: PluginSecretUseRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.invoke")),
) -> PluginSecretUseResponse:
    installation = _get_installation(db, context, payload.installation_id)
    grants = _permission_grants(db, installation.id)
    response = broker_secret_use(
        installation_status=installation.status,
        granted_permissions=grants,
        secret_references=installation.secret_references or [],
        secret_ref=payload.secret_ref,
        purpose=payload.purpose,
        target_domain=payload.target_domain,
    )
    if response.allowed:
        db.add(
            ArceusPluginUsageEvent(
                tenant_id=context.tenant_id,
                plugin_id=installation.plugin_id,
                installation_id=installation.id,
                mission_id=payload.mission_id,
                metric="secret_broker_use",
                quantity=1,
                idempotency_key=response.broker_receipt_id,
                metadata_json={"secret_ref": payload.secret_ref, "purpose": payload.purpose, "target_domain": payload.target_domain},
            )
        )
        db.commit()
    return response


@router.post("/permissions/evaluate", response_model=PermissionEvaluationResponse)
def evaluate_permission(
    payload: PermissionEvaluationRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.invoke")),
) -> PermissionEvaluationResponse:
    installation = _get_installation(db, context, payload.installation_id)
    grants = _permission_grants(db, installation.id)
    return evaluate_permission_grants(
        installation_status=installation.status,
        granted_permissions=grants,
        requested_permission=payload.permission,
        risk_level=payload.risk_level,
        scope=payload.scope,
    )


@router.post("/invocations", response_model=PluginInvocationResponse)
def invoke_extension(
    payload: PluginInvocationRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("extension.invoke")),
) -> PluginInvocationResponse:
    installation = _get_installation(db, context, payload.installation_id)
    grants = _permission_grants(db, installation.id)
    decision = evaluate_permission_grants(
        installation_status=installation.status,
        granted_permissions=grants,
        requested_permission=payload.permission,
        risk_level=payload.risk_level,
        scope={},
    )
    receipt = invocation_receipt(
        capability_id=payload.capability_id,
        permission=payload.permission,
        dry_run=payload.dry_run,
        allowed=decision.allowed,
        reason=decision.reason,
    )
    invocation = ArceusPluginInvocation(
        tenant_id=context.tenant_id,
        installation_id=installation.id,
        capability_id=payload.capability_id,
        mission_id=payload.mission_id,
        workflow_node_id=payload.workflow_node_id,
        actor_identity_id=str(context.user_id),
        extension_identity_id=installation.extension_identity_id,
        trace_id=f"trace_{uuid4().hex[:16]}",
        status="succeeded" if decision.allowed and payload.dry_run else ("authorized" if decision.allowed else "denied"),
        input_fingerprint=payload_fingerprint(payload.input_payload),
        receipt=receipt,
    )
    db.add(invocation)
    db.flush()
    if decision.allowed:
        plugin_id = installation.plugin_id
        db.add(
            ArceusPluginUsageEvent(
                tenant_id=context.tenant_id,
                plugin_id=plugin_id,
                installation_id=installation.id,
                invocation_id=invocation.id,
                mission_id=payload.mission_id,
                metric="invocation",
                quantity=1,
                idempotency_key=f"plugin-invocation:{invocation.id}",
                metadata_json={"capability_id": payload.capability_id, "dry_run": payload.dry_run},
            )
        )
    db.commit()
    return PluginInvocationResponse(invocation_id=invocation.id, status=invocation.status, allowed=decision.allowed, receipt=receipt, audit_recorded=True)


def _get_or_create_publisher(db: Session, context: RequestContext, publisher: dict[str, str]) -> ArceusPluginPublisher:
    row = (
        db.query(ArceusPluginPublisher)
        .filter(ArceusPluginPublisher.tenant_id == context.tenant_id, ArceusPluginPublisher.publisher_key == publisher["key"])
        .first()
    )
    if row is None:
        row = ArceusPluginPublisher(
            tenant_id=context.tenant_id,
            publisher_key=publisher["key"],
            display_name=publisher["name"],
            verification_level="arceus" if publisher["key"] == "arceus" else "unverified",
            status="active",
            metadata_json={},
        )
        db.add(row)
        db.flush()
    return row


def _get_or_create_plugin(db: Session, context: RequestContext, publisher_id: UUID, validation: ManifestValidationResponse) -> ArceusPlugin:
    row = (
        db.query(ArceusPlugin)
        .filter(ArceusPlugin.tenant_id == context.tenant_id, ArceusPlugin.plugin_key == validation.plugin_key)
        .first()
    )
    if row is None:
        row = ArceusPlugin(
            tenant_id=context.tenant_id,
            plugin_key=str(validation.plugin_key),
            name=str(validation.name),
            description=validation.normalized_manifest.get("description") or "",
            publisher_id=publisher_id,
            category="official" if validation.publisher_key == "arceus" else "private",
            status="draft",
            metadata_json={"extension_types": validation.extension_types},
        )
        db.add(row)
        db.flush()
    return row


def _get_or_create_version(db: Session, plugin_id: UUID, validation: ManifestValidationResponse) -> ArceusPluginVersion:
    row = (
        db.query(ArceusPluginVersion)
        .filter(ArceusPluginVersion.plugin_id == plugin_id, ArceusPluginVersion.version == validation.version)
        .first()
    )
    manifest = validation.normalized_manifest
    package_digest = manifest.get("integrity", {}).get("package_digest")
    signature = manifest.get("integrity", {}).get("signature")
    if row is None:
        row = ArceusPluginVersion(
            plugin_id=plugin_id,
            version=str(validation.version),
            manifest=manifest,
            manifest_digest=validation.manifest_digest or stable_json_digest(manifest),
            package_digest=package_digest,
            signature=signature,
            status="approved" if validation.signed and not validation.review_required else "pending_review",
            security_score=validation.security_score,
            compatibility=manifest.get("compatibility") or {},
        )
        db.add(row)
        db.flush()
    else:
        row.manifest = manifest
        row.manifest_digest = validation.manifest_digest or stable_json_digest(manifest)
        row.package_digest = package_digest
        row.signature = signature
        row.security_score = validation.security_score
    return row


def _get_installation(db: Session, context: RequestContext, installation_id: UUID) -> ArceusPluginInstallation:
    row = (
        db.query(ArceusPluginInstallation)
        .filter(ArceusPluginInstallation.tenant_id == context.tenant_id, ArceusPluginInstallation.id == installation_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Plugin installation not found."})
    return row


def _permission_grants(db: Session, installation_id: UUID) -> list[dict]:
    rows = (
        db.query(ArceusPluginInstallationPermission)
        .filter(ArceusPluginInstallationPermission.installation_id == installation_id)
        .all()
    )
    return [
        {
            "permission": row.permission_key,
            "permission_key": row.permission_key,
            "scope": row.scope,
            "conditions": row.conditions,
            "risk_level": row.risk_level,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }
        for row in rows
    ]


def _installation_response(
    db: Session,
    installation: ArceusPluginInstallation,
    validation: ManifestValidationResponse | None = None,
) -> PluginInstallationResponse:
    plugin = db.query(ArceusPlugin).filter(ArceusPlugin.id == installation.plugin_id).first()
    version = db.query(ArceusPluginVersion).filter(ArceusPluginVersion.id == installation.plugin_version_id).first()
    permissions = [
        {
            "permission": grant["permission"],
            "risk_level": grant["risk_level"],
            "scope": grant["scope"],
            "conditions": grant["conditions"],
        }
        for grant in _permission_grants(db, installation.id)
    ]
    signed = validation.signed if validation is not None else bool(version and version.signature)
    review_required = validation.review_required if validation is not None else installation.status == "pending_review"
    return PluginInstallationResponse(
        installation_id=installation.id,
        plugin_id=installation.plugin_id,
        plugin_version_id=installation.plugin_version_id,
        plugin_key=plugin.plugin_key if plugin else "unknown",
        name=plugin.name if plugin else "Unknown Plugin",
        version=version.version if version else "0.0.0",
        scope_type=installation.scope_type,
        scope_id=installation.scope_id,
        status=installation.status,
        extension_identity_id=installation.extension_identity_id,
        granted_permissions=[ExtensionPermission(**item) for item in permissions],
        review_required=review_required,
        signed=signed,
        security_score=validation.security_score if validation is not None else (version.security_score if version else 0.0),
    )
