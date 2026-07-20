from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .api_schemas import (
    AgentIdentityRequest,
    AgentIdentityResponse,
    ApiTokenIssueRequest,
    ApiTokenIssueResponse,
    AuthorizationDecisionRequest,
    AuthorizationDecisionResponse,
    DecisionStatus,
    GovernanceSummaryResponse,
    IdentityPrincipal,
    PolicyDefinition,
    RoleDefinition,
    ServiceAccountRequest,
    ServiceAccountResponse,
    UserSessionRiskRequest,
    UserSessionRiskResponse,
)


ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        role_key="owner",
        name="Owner",
        permissions=["*"],
        human_only_approvals=True,
        description="Full organization authority, including billing, policy, and production approvals.",
    ),
    RoleDefinition(
        role_key="administrator",
        name="Administrator",
        permissions=[
            "organization.manage",
            "workspace.manage",
            "policy.manage",
            "audit.view",
            "user.invite",
            "telemetry.view",
            "telemetry.dashboard.view",
            "alert.view",
            "incident.manage",
            "marketplace.view",
            "extension.view",
            "extension.manage",
            "extension.install",
            "extension.publish",
        ],
        human_only_approvals=True,
        description="Manages organization operations but still follows security review and separation of duties.",
    ),
    RoleDefinition(
        role_key="developer",
        name="Developer",
        permissions=["mission.create", "repository.read", "repository.update", "tool.execute", "test.run", "telemetry.view", "marketplace.view", "extension.view", "extension.invoke"],
        description="Creates missions, edits approved code paths, and runs development tools.",
    ),
    RoleDefinition(
        role_key="reviewer",
        name="Reviewer",
        permissions=["review.create", "review.complete", "mission.view", "artifact.view"],
        human_only_approvals=True,
        description="Reviews submitted work and can approve non-production engineering decisions.",
    ),
    RoleDefinition(
        role_key="security",
        name="Security",
        permissions=["security.evaluate", "security.audit.view", "secret.review", "deployment.veto", "telemetry.view", "alert.view", "incident.manage", "extension.view", "extension.security.review"],
        human_only_approvals=True,
        description="Reviews and vetoes unsafe changes without directly modifying reviewed artifacts.",
    ),
    RoleDefinition(
        role_key="qa",
        name="QA",
        permissions=["verification.manage", "test.run", "evidence.collect", "review.complete", "telemetry.view", "telemetry.write"],
        human_only_approvals=True,
        description="Owns evidence and quality verification.",
    ),
    RoleDefinition(
        role_key="production_operator",
        name="Production Operator",
        permissions=["deployment.execute", "deployment.rollback", "environment.view", "telemetry.view", "telemetry.dashboard.view", "telemetry.write", "alert.view", "alert.manage", "incident.manage"],
        human_only_approvals=True,
        description="Deploys approved artifacts but cannot waive required reviews.",
    ),
    RoleDefinition(
        role_key="ai_operator",
        name="AI Operator",
        permissions=["mission.create", "agent.manage", "workflow.execute", "tool.authorize"],
        description="Operates AI workers but does not count as human approval.",
    ),
    RoleDefinition(
        role_key="viewer",
        name="Viewer",
        permissions=["mission.view", "artifact.view", "audit.view", "marketplace.view", "extension.view"],
        description="Read-only visibility into allowed resources.",
    ),
)


POLICIES: tuple[PolicyDefinition, ...] = (
    PolicyDefinition(
        policy_key="identity.default_deny",
        name="Default Deny",
        description="If no role or explicit permission grants the action, the request is denied.",
        severity="critical",
        resource_types=["*"],
        actions=["*"],
        obligations=["explain_denial", "record_audit_event"],
    ),
    PolicyDefinition(
        policy_key="identity.tenant_isolation",
        name="Tenant Isolation",
        description="Principals can only access resources inside their organization boundary.",
        severity="critical",
        resource_types=["organization", "workspace", "project", "repository", "mission", "secret", "deployment"],
        actions=["read", "create", "update", "delete", "execute", "approve", "deploy", "manage"],
        obligations=["block_cross_tenant_access", "record_policy_denial"],
    ),
    PolicyDefinition(
        policy_key="identity.mfa_for_high_risk",
        name="MFA Required For High Risk",
        description="Critical or production actions require MFA and recent re-authentication.",
        severity="critical",
        resource_types=["secret", "deployment", "policy", "environment", "organization"],
        actions=["delete", "deploy", "approve", "manage", "secret.access", "policy.manage"],
        obligations=["complete_mfa", "reauthenticate"],
    ),
    PolicyDefinition(
        policy_key="identity.ai_no_human_approval",
        name="AI Cannot Satisfy Human Approval",
        description="AI agents can recommend and implement within scope but cannot count as required human approval.",
        severity="critical",
        resource_types=["mission", "deployment", "policy", "repository"],
        actions=["approve", "merge", "deploy", "completion.approve"],
        obligations=["request_human_approval"],
    ),
    PolicyDefinition(
        policy_key="identity.separation_of_duties",
        name="Separation Of Duties",
        description="A principal cannot be the only approver of its own critical implementation.",
        severity="high",
        resource_types=["mission", "repository", "deployment"],
        actions=["approve", "merge", "deploy"],
        obligations=["assign_independent_reviewer"],
    ),
    PolicyDefinition(
        policy_key="identity.production_operator_only",
        name="Production Operator Required",
        description="Production deployment authority is separate from development authority.",
        severity="critical",
        resource_types=["deployment", "environment"],
        actions=["deploy", "production.deploy", "deployment.execute"],
        obligations=["route_to_production_operator", "verify_release_gate"],
    ),
)


SENSITIVE_ACTIONS = [
    "organization.delete",
    "policy.manage",
    "secret.access",
    "deployment.execute",
    "production.deploy",
    "billing.manage",
    "repository.delete",
    "completion.approve",
]


def list_roles() -> list[RoleDefinition]:
    return list(ROLE_DEFINITIONS)


def list_policies() -> list[PolicyDefinition]:
    return list(POLICIES)


def _role_permissions(role_keys: list[str]) -> set[str]:
    permissions: set[str] = set()
    role_map = {role.role_key: role for role in ROLE_DEFINITIONS}
    for role_key in role_keys:
        role = role_map.get(role_key)
        if role:
            permissions.update(role.permissions)
    return permissions


def _normalized_action(action: str) -> str:
    return action.strip().lower().replace("_", ".")


def _action_candidates(action: str, resource_type: str) -> set[str]:
    normalized = _normalized_action(action)
    verb = normalized.split(".")[-1]
    return {normalized, verb, f"{resource_type}.{verb}", f"{resource_type}:{verb}"}


def _has_permission(principal: IdentityPrincipal, action: str, resource_type: str, required_permissions: list[str]) -> bool:
    effective = set(principal.permissions) | _role_permissions(principal.role_keys)
    if "*" in effective:
        return True
    if required_permissions:
        return all(required in effective for required in required_permissions)
    return bool(effective & _action_candidates(action, resource_type))


def _audit_event(
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    decision: str,
    policy_ids: list[str],
    reason: str,
) -> dict[str, Any]:
    return {
        "event_id": f"audit_{uuid4().hex[:12]}",
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "decision": decision,
        "policy_ids": policy_ids,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def evaluate_authorization(payload: AuthorizationDecisionRequest) -> AuthorizationDecisionResponse:
    principal = payload.principal
    resource = payload.resource
    matched: list[str] = []
    obligations: list[str] = ["record_audit_event"]
    decision: DecisionStatus = "allow"
    reason = "Permission and policy checks passed."

    if principal.status != "active":
        matched.append("identity.default_deny")
        obligations.append("reactivate_or_replace_identity")
        decision = "deny"
        reason = "Principal is not active."
    elif resource.organization_id and principal.organization_id and resource.organization_id != principal.organization_id:
        matched.append("identity.tenant_isolation")
        obligations.append("block_cross_tenant_access")
        decision = "deny"
        reason = "Resource belongs to a different organization."
    elif payload.required_human_approval and principal.identity_type not in {"human", "enterprise_user"}:
        matched.append("identity.ai_no_human_approval")
        obligations.append("request_human_approval")
        decision = "deny"
        reason = "This action requires human approval; AI/service identities cannot satisfy it."
    elif principal.identity_id in payload.existing_approver_ids and resource.risk_level in {"high", "critical"}:
        matched.append("identity.separation_of_duties")
        obligations.append("assign_independent_reviewer")
        decision = "needs_approval"
        reason = "Critical work requires an independent approver."
    elif resource.environment == "production" and _normalized_action(payload.action) in {"deploy", "production.deploy", "deployment.execute"}:
        if "production_operator" not in principal.role_keys and "*" not in principal.permissions:
            matched.append("identity.production_operator_only")
            obligations.extend(["route_to_production_operator", "verify_release_gate"])
            decision = "deny"
            reason = "Production deployment requires production operator authority."
        elif not principal.mfa_verified:
            matched.append("identity.mfa_for_high_risk")
            obligations.append("complete_mfa")
            decision = "requires_mfa"
            reason = "Production deployment requires MFA."
        elif not principal.reauthenticated:
            matched.append("identity.mfa_for_high_risk")
            obligations.append("reauthenticate")
            decision = "requires_reauth"
            reason = "Production deployment requires recent re-authentication."
    elif resource.risk_level in {"high", "critical"} and _normalized_action(payload.action) in {"delete", "manage", "policy.manage", "secret.access"}:
        if not principal.mfa_verified:
            matched.append("identity.mfa_for_high_risk")
            obligations.append("complete_mfa")
            decision = "requires_mfa"
            reason = "High-risk action requires MFA."

    if decision == "allow" and not _has_permission(principal, payload.action, resource.resource_type, payload.required_permissions):
        matched.append("identity.default_deny")
        obligations.append("request_permission_grant")
        decision = "deny"
        reason = "No role or explicit permission grants this action."

    allowed = decision == "allow"
    effective_permissions = sorted(set(principal.permissions) | _role_permissions(principal.role_keys))
    if not matched:
        matched.append("identity.default_allow_after_policy")
    audit_event = _audit_event(
        actor_id=principal.identity_id,
        action=payload.action,
        resource_type=resource.resource_type,
        resource_id=resource.resource_id,
        decision=decision,
        policy_ids=matched,
        reason=reason,
    )
    return AuthorizationDecisionResponse(
        decision_id=f"authz_{uuid4().hex[:12]}",
        allowed=allowed,
        decision=decision,
        reason=reason,
        matched_policies=matched,
        obligations=sorted(set(obligations)),
        effective_permissions=effective_permissions,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30) if allowed and resource.risk_level in {"high", "critical"} else None,
        audit_event=audit_event,
    )


def evaluate_session_risk(payload: UserSessionRiskRequest) -> UserSessionRiskResponse:
    score = 0
    actions: list[str] = []
    if not payload.device_trusted:
        score += 25
        actions.append("verify_device")
    if not payload.mfa_verified:
        score += 20
        actions.append("complete_mfa")
    if payload.failed_login_attempts:
        score += min(30, payload.failed_login_attempts * 6)
        actions.append("review_failed_logins")
    if payload.impossible_travel:
        score += 40
        actions.append("challenge_impossible_travel")
    if payload.last_seen_minutes_ago > 480:
        score += 15
        actions.append("refresh_session")

    score = min(score, 100)
    if payload.last_seen_minutes_ago > 24 * 60:
        status = "expired"
        actions.append("sign_in_again")
    elif score >= 60:
        status = "high_risk"
    elif payload.last_seen_minutes_ago > 60:
        status = "idle"
    else:
        status = "active"

    return UserSessionRiskResponse(
        session_id=payload.session_id,
        risk_score=score,
        status=status,
        required_actions=sorted(set(actions)),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )


def issue_api_token(payload: ApiTokenIssueRequest) -> ApiTokenIssueResponse:
    raw_token = f"arc_{secrets.token_urlsafe(24)}"
    checksum = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token_id = f"tok_{uuid4().hex[:12]}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    audit_event = _audit_event(
        actor_id=payload.owner_id,
        action="api_token.issue",
        resource_type="policy",
        resource_id=token_id,
        decision="allow",
        policy_ids=["identity.short_lived_credentials"],
        reason="API token was issued with scoped permissions and expiration.",
    )
    return ApiTokenIssueResponse(
        token_id=token_id,
        name=payload.name,
        prefix=raw_token[:8],
        checksum=checksum,
        scopes=payload.scopes,
        environment=payload.environment,
        expires_at=expires_at,
        one_time_token_preview=f"{raw_token[:12]}...",
        audit_event=audit_event,
    )


def create_service_account(payload: ServiceAccountRequest) -> ServiceAccountResponse:
    service_account_id = f"svc_{uuid4().hex[:12]}"
    principal = IdentityPrincipal(
        identity_id=service_account_id,
        identity_type="service_account",
        display_name=payload.name,
        organization_id=payload.organization_id,
        role_keys=["viewer"],
        permissions=payload.scopes,
        attributes={"purpose": payload.purpose, "allowed_environments": payload.allowed_environments},
    )
    return ServiceAccountResponse(
        service_account_id=service_account_id,
        principal=principal,
        token_policy={
            "short_lived": True,
            "maximum_ttl_minutes": 60,
            "allowed_environments": payload.allowed_environments,
            "secret_material_returned": False,
        },
        audit_event=_audit_event(
            actor_id=service_account_id,
            action="service_account.create",
            resource_type="organization",
            resource_id=payload.organization_id,
            decision="allow",
            policy_ids=["identity.service_account_scoped"],
            reason="Service account identity created without exposing long-lived credentials.",
        ),
    )


def create_agent_identity(payload: AgentIdentityRequest) -> AgentIdentityResponse:
    agent_identity_id = f"agent_{uuid4().hex[:12]}"
    permissions = ["mission.view", "artifact.view", "tool.authorize"]
    if payload.maximum_risk_level in {"medium", "high"}:
        permissions.append("repository.update")
    principal = IdentityPrincipal(
        identity_id=agent_identity_id,
        identity_type="agent",
        display_name=payload.profile_id.replace("_", " ").title(),
        organization_id=payload.organization_id,
        role_keys=["ai_operator"],
        permissions=permissions,
        attributes={
            "mission_id": payload.mission_id,
            "capabilities": payload.capabilities,
            "allowed_tools": payload.allowed_tools,
            "maximum_risk_level": payload.maximum_risk_level,
        },
    )
    return AgentIdentityResponse(
        agent_identity_id=agent_identity_id,
        principal=principal,
        runtime_claims={
            "mission_bound": bool(payload.mission_id),
            "capabilities": payload.capabilities,
            "allowed_tools": payload.allowed_tools,
            "maximum_risk_level": payload.maximum_risk_level,
            "credential_ttl_minutes": 30,
        },
        restrictions=[
            "cannot_count_as_human_approval",
            "cannot_access_production_secrets",
            "cannot_merge_protected_branches",
            "cannot_modify_identity_or_policy",
        ],
        audit_event=_audit_event(
            actor_id=agent_identity_id,
            action="agent_identity.create",
            resource_type="agent",
            resource_id=agent_identity_id,
            decision="allow",
            policy_ids=["identity.agent_scoped_runtime"],
            reason="Mission-scoped AI identity created with capability restrictions.",
        ),
    )


def governance_summary() -> GovernanceSummaryResponse:
    return GovernanceSummaryResponse(
        default_deny=True,
        supported_identity_types=["human", "enterprise_user", "guest", "agent", "automation_worker", "service_account", "api_client", "desktop_app", "web_app", "mobile_app"],
        built_in_roles=list_roles(),
        policies=list_policies(),
        sensitive_actions=SENSITIVE_ACTIONS,
        audit_required_for=["authorization_decision", "token_issue", "service_account_create", "agent_identity_create", "policy_denial", "secret_access", "production_action"],
        mvp_readiness={
            "clerk_provider_boundary": True,
            "organizations": True,
            "workspaces": True,
            "rbac": True,
            "abac_policy_inputs": True,
            "api_tokens": True,
            "service_accounts": True,
            "agent_identities": True,
            "audit_event_shape": True,
            "enterprise_sso": False,
            "scim": False,
            "persistent_token_vault": False,
        },
    )
