from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAgentIdentity,
    ArceusApiToken,
    ArceusAuthorizationDecision,
    ArceusIdentityProvider,
    ArceusServiceAccount,
    ArceusUserSession,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AgentIdentityRequest,
    ApiTokenIssueRequest,
    AuthorizationDecisionRequest,
    IdentityProviderSyncRequest,
    IdentityProviderSyncResponse,
    IdentityPrincipal,
    ServiceAccountRequest,
    UserSessionRiskRequest,
)
from .service import (
    create_agent_identity,
    create_service_account,
    evaluate_authorization,
    evaluate_session_risk,
    governance_summary,
    issue_api_token,
    list_policies,
    list_roles,
)


router = APIRouter(prefix="/api/v1/identity", tags=["identity-governance"])


def _record_audit(
    db: Session,
    context: RequestContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None,
    result: str,
    metadata: dict,
) -> None:
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        metadata={**metadata, "correlation_id": str(context.correlation_id)},
    )


@router.get("/me")
def get_current_identity(
    request: Request,
    context: RequestContext = Depends(require_permission("identity.view")),
):
    principal = IdentityPrincipal(
        identity_id=str(context.user_id),
        identity_type="human",
        display_name="Current User",
        organization_id=str(context.tenant_id),
        role_keys=sorted(context.role_keys),
        permissions=sorted(context.permissions),
        status="active",
        attributes={
            "membership_id": str(context.membership_id),
            "client_type": context.client_type,
            "ip_address": context.ip_address,
            "user_agent": context.user_agent,
            "clerk_org_id": request.headers.get("x-clerk-org-id"),
            "clerk_session_id": request.headers.get("x-clerk-session-id"),
            "enterprise_sso": request.headers.get("x-enterprise-sso") in {"1", "true", "yes"},
            "scim_enabled": request.headers.get("x-scim-enabled") in {"1", "true", "yes"},
            "device_trusted": request.headers.get("x-device-trusted") in {"1", "true", "yes"},
        },
    )
    return api_response(principal.model_dump(mode="json"), request)


@router.get("/roles")
def get_identity_roles(
    request: Request,
    _context: RequestContext = Depends(require_permission("identity.view")),
):
    return collection_response([role.model_dump(mode="json") for role in list_roles()], request)


@router.get("/policies")
def get_identity_policies(
    request: Request,
    _context: RequestContext = Depends(require_permission("policy.view")),
):
    return collection_response([policy.model_dump(mode="json") for policy in list_policies()], request)


@router.post("/authorize")
def authorize_identity_action(
    payload: AuthorizationDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.authorize")),
    db: Session = Depends(get_db),
):
    response = evaluate_authorization(payload)
    row = ArceusAuthorizationDecision(
        tenant_id=context.tenant_id,
        actor_type=payload.principal.identity_type,
        actor_id=payload.principal.identity_id,
        action=payload.action,
        resource_type=payload.resource.resource_type,
        resource_id=payload.resource.resource_id,
        decision=response.decision,
        allowed=response.allowed,
        reason=response.reason,
        matched_policies=response.matched_policies,
        obligations=response.obligations,
        effective_permissions=response.effective_permissions,
        request_payload=payload.model_dump(mode="json"),
        expires_at=response.expires_at,
    )
    db.add(row)
    db.flush()
    _record_audit(
        db,
        context,
        action="AUTHORIZATION_DECISION_RECORDED",
        resource_type="authorization_decision",
        resource_id=row.id,
        result=response.decision,
        metadata={
            "actor_type": payload.principal.identity_type,
            "actor_id": payload.principal.identity_id,
            "action": payload.action,
            "resource_type": payload.resource.resource_type,
            "resource_id": payload.resource.resource_id,
            "matched_policies": response.matched_policies,
            "obligations": response.obligations,
            "reason": response.reason,
        },
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/sessions/risk")
def evaluate_identity_session_risk(
    payload: UserSessionRiskRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.session.evaluate")),
    db: Session = Depends(get_db),
):
    response = evaluate_session_risk(payload)
    session_row = ArceusUserSession(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        external_session_id=payload.session_id,
        device_id=payload.session_id,
        ip_address=payload.ip_address or context.ip_address,
        user_agent=payload.user_agent or context.user_agent,
        status=response.status,
        risk_score=response.risk_score,
        mfa_verified=payload.mfa_verified,
        device_trusted=payload.device_trusted,
        expires_at=response.expires_at,
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={
            "required_actions": response.required_actions,
            "failed_login_attempts": payload.failed_login_attempts,
            "impossible_travel": payload.impossible_travel,
        },
    )
    db.add(session_row)
    db.flush()
    _record_audit(
        db,
        context,
        action="SESSION_RISK_EVALUATED",
        resource_type="session",
        resource_id=session_row.id,
        result=response.status,
        metadata={"risk_score": response.risk_score, "required_actions": response.required_actions},
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/tokens/issue")
def issue_identity_api_token(
    payload: ApiTokenIssueRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.token.issue")),
    db: Session = Depends(get_db),
):
    scoped_payload = payload.model_copy(update={"owner_id": str(context.user_id)})
    response = issue_api_token(scoped_payload)
    token_row = ArceusApiToken(
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
        name=response.name,
        prefix=response.prefix,
        checksum_sha256=response.checksum,
        scopes=response.scopes,
        environment=response.environment,
        status="active",
        expires_at=response.expires_at,
        metadata_json={"token_id": response.token_id, "vault_backed": True, "secret_material_stored": False},
    )
    db.add(token_row)
    db.flush()
    _record_audit(
        db,
        context,
        action="API_TOKEN_ISSUED",
        resource_type="api_token",
        resource_id=token_row.id,
        result="allow",
        metadata={"token_id": response.token_id, "prefix": response.prefix, "scopes": response.scopes, "checksum_only": True},
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/service-accounts")
def create_identity_service_account(
    payload: ServiceAccountRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.service_account.create")),
    db: Session = Depends(get_db),
):
    scoped_payload = payload.model_copy(update={"organization_id": str(context.tenant_id)})
    response = create_service_account(scoped_payload)
    row = ArceusServiceAccount(
        tenant_id=context.tenant_id,
        name=payload.name,
        purpose=payload.purpose,
        scopes=payload.scopes,
        allowed_environments=payload.allowed_environments,
        status="active",
        created_by=context.user_id,
        metadata_json={"service_account_id": response.service_account_id, "token_policy": response.token_policy},
    )
    db.add(row)
    db.flush()
    _record_audit(
        db,
        context,
        action="SERVICE_ACCOUNT_CREATED",
        resource_type="service_account",
        resource_id=row.id,
        result="allow",
        metadata={"service_account_id": response.service_account_id, "scopes": payload.scopes, "allowed_environments": payload.allowed_environments},
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/agents")
def create_identity_agent(
    payload: AgentIdentityRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.agent.create")),
    db: Session = Depends(get_db),
):
    scoped_payload = payload.model_copy(update={"organization_id": str(context.tenant_id)})
    response = create_agent_identity(scoped_payload)
    row = ArceusAgentIdentity(
        tenant_id=context.tenant_id,
        profile_id=payload.profile_id,
        mission_id=UUID(payload.mission_id) if payload.mission_id else None,
        capabilities=payload.capabilities,
        allowed_tools=payload.allowed_tools,
        maximum_risk_level=payload.maximum_risk_level,
        status="active",
        runtime_claims=response.runtime_claims,
        restrictions=response.restrictions,
    )
    db.add(row)
    db.flush()
    _record_audit(
        db,
        context,
        action="AGENT_IDENTITY_CREATED",
        resource_type="agent_identity",
        resource_id=row.id,
        result="allow",
        metadata={"agent_identity_id": response.agent_identity_id, "capabilities": payload.capabilities, "restrictions": response.restrictions},
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.get("/governance-summary")
def get_identity_governance_summary(
    request: Request,
    _context: RequestContext = Depends(require_permission("identity.governance.view")),
):
    return api_response(governance_summary().model_dump(mode="json"), request)


@router.post("/providers/sync-clerk")
def sync_clerk_identity_provider(
    payload: IdentityProviderSyncRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("identity.provider.sync")),
    db: Session = Depends(get_db),
):
    capabilities = sorted(
        set(
            payload.capabilities
            or [
                "login",
                "signup",
                "mfa",
                "oauth",
                "session_management",
                "organizations",
            ]
        )
    )
    issuer = payload.issuer or os.getenv("CLERK_ISSUER") or request.headers.get("x-clerk-issuer")
    provider = (
        db.query(ArceusIdentityProvider)
        .filter(ArceusIdentityProvider.tenant_id == context.tenant_id, ArceusIdentityProvider.provider_key == payload.provider_key)
        .first()
    )
    if provider is None:
        provider = ArceusIdentityProvider(
            tenant_id=context.tenant_id,
            provider_key=payload.provider_key,
            provider_type=payload.provider_type,
            issuer=issuer,
            status="active",
        )
        db.add(provider)
    provider.provider_type = payload.provider_type
    provider.issuer = issuer
    provider.status = "active"
    provider.capabilities = capabilities
    provider.scim_enabled = payload.scim_enabled
    provider.enterprise_sso_enabled = payload.enterprise_sso_enabled
    provider.device_trust_enabled = payload.device_trust_enabled
    provider.metadata_json = {
        **payload.metadata,
        "clerk_org_id": request.headers.get("x-clerk-org-id"),
        "clerk_session_id_present": bool(request.headers.get("x-clerk-session-id")),
        "configured_from_env": bool(os.getenv("CLERK_ISSUER") or os.getenv("CLERK_JWKS_URL") or os.getenv("CLERK_SECRET_KEY")),
    }
    db.flush()
    _record_audit(
        db,
        context,
        action="IDENTITY_PROVIDER_SYNCED",
        resource_type="identity_provider",
        resource_id=provider.id,
        result="active",
        metadata={"provider_key": provider.provider_key, "capabilities": capabilities, "enterprise_sso_enabled": payload.enterprise_sso_enabled, "scim_enabled": payload.scim_enabled},
    )
    db.commit()
    response = IdentityProviderSyncResponse(
        provider_id=provider.id,
        provider_key=provider.provider_key,
        provider_type=provider.provider_type,
        status=provider.status,
        capabilities=provider.capabilities,
        scim_enabled=provider.scim_enabled,
        enterprise_sso_enabled=provider.enterprise_sso_enabled,
        device_trust_enabled=provider.device_trust_enabled,
        audit_recorded=True,
    )
    return api_response(response.model_dump(mode="json"), request)
