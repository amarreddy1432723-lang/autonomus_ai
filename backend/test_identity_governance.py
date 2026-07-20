from services.agent.arceus_runtime.identity.api_schemas import (
    AgentIdentityRequest,
    ApiTokenIssueRequest,
    AuthorizationDecisionRequest,
    AuthorizationResource,
    IdentityPrincipal,
    ServiceAccountRequest,
    UserSessionRiskRequest,
)
from services.agent.arceus_runtime.identity.service import (
    create_agent_identity,
    create_service_account,
    evaluate_authorization,
    evaluate_session_risk,
    governance_summary,
    issue_api_token,
    list_policies,
    list_roles,
)
from services.shared.arceus_core_models import (
    ArceusAgentIdentity,
    ArceusApiToken,
    ArceusAuthorizationDecision,
    ArceusIdentityProvider,
    ArceusServiceAccount,
    ArceusUserSession,
)


def human_principal(**overrides):
    data = {
        "identity_id": "user-1",
        "identity_type": "human",
        "display_name": "Human User",
        "organization_id": "org-1",
        "role_keys": ["developer"],
        "permissions": [],
        "mfa_verified": False,
        "reauthenticated": False,
    }
    data.update(overrides)
    return IdentityPrincipal(**data)


def test_identity_catalog_contains_rbac_roles_and_default_deny_policy() -> None:
    roles = {role.role_key: role for role in list_roles()}
    policies = {policy.policy_key: policy for policy in list_policies()}

    assert {"owner", "developer", "security", "qa", "production_operator", "ai_operator"}.issubset(roles)
    assert "identity.default_deny" in policies
    assert policies["identity.default_deny"].severity == "critical"


def test_authorization_denies_without_grant() -> None:
    decision = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(role_keys=[], permissions=[]),
            action="repository.update",
            resource=AuthorizationResource(resource_type="repository", resource_id="repo-1", organization_id="org-1"),
        )
    )

    assert decision.allowed is False
    assert decision.decision == "deny"
    assert "identity.default_deny" in decision.matched_policies
    assert "request_permission_grant" in decision.obligations


def test_authorization_blocks_cross_tenant_access() -> None:
    decision = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(),
            action="repository.read",
            resource=AuthorizationResource(resource_type="repository", resource_id="repo-1", organization_id="org-2"),
        )
    )

    assert decision.decision == "deny"
    assert "identity.tenant_isolation" in decision.matched_policies
    assert "block_cross_tenant_access" in decision.obligations


def test_authorization_requires_mfa_and_reauth_for_production_deploy() -> None:
    no_mfa = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(role_keys=["production_operator"], mfa_verified=False),
            action="deployment.execute",
            resource=AuthorizationResource(resource_type="deployment", resource_id="prod", organization_id="org-1", environment="production", risk_level="critical"),
        )
    )
    no_reauth = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(role_keys=["production_operator"], mfa_verified=True, reauthenticated=False),
            action="deployment.execute",
            resource=AuthorizationResource(resource_type="deployment", resource_id="prod", organization_id="org-1", environment="production", risk_level="critical"),
        )
    )

    assert no_mfa.decision == "requires_mfa"
    assert "complete_mfa" in no_mfa.obligations
    assert no_reauth.decision == "requires_reauth"
    assert "reauthenticate" in no_reauth.obligations


def test_ai_principal_cannot_satisfy_human_approval() -> None:
    decision = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=IdentityPrincipal(
                identity_id="agent-1",
                identity_type="agent",
                organization_id="org-1",
                role_keys=["ai_operator"],
                permissions=["completion.approve"],
            ),
            action="completion.approve",
            resource=AuthorizationResource(resource_type="mission", resource_id="mission-1", organization_id="org-1", risk_level="high"),
            required_human_approval=True,
        )
    )

    assert decision.decision == "deny"
    assert "identity.ai_no_human_approval" in decision.matched_policies


def test_separation_of_duties_requires_independent_reviewer() -> None:
    decision = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(role_keys=["reviewer"], permissions=["approve"]),
            action="approve",
            resource=AuthorizationResource(resource_type="mission", resource_id="mission-1", organization_id="org-1", risk_level="critical"),
            existing_approver_ids=["user-1"],
        )
    )

    assert decision.decision == "needs_approval"
    assert "identity.separation_of_duties" in decision.matched_policies


def test_session_risk_flags_untrusted_unverified_impossible_travel() -> None:
    response = evaluate_session_risk(
        UserSessionRiskRequest(
            user_id="user-1",
            device_trusted=False,
            mfa_verified=False,
            failed_login_attempts=4,
            impossible_travel=True,
        )
    )

    assert response.status == "high_risk"
    assert response.risk_score >= 60
    assert "challenge_impossible_travel" in response.required_actions


def test_api_token_issue_returns_checksum_not_full_token() -> None:
    response = issue_api_token(
        ApiTokenIssueRequest(name="CI token", owner_id="user-1", scopes=["repository.read", "test.run"], expires_in_days=7)
    )

    assert response.prefix.startswith("arc_")
    assert len(response.checksum) == 64
    assert response.one_time_token_preview.endswith("...")
    assert response.audit_event["action"] == "api_token.issue"


def test_service_account_has_scoped_non_secret_token_policy() -> None:
    response = create_service_account(
        ServiceAccountRequest(name="Release bot", organization_id="org-1", scopes=["deployment.execute"], allowed_environments=["staging"])
    )

    assert response.principal.identity_type == "service_account"
    assert response.token_policy["secret_material_returned"] is False
    assert response.principal.permissions == ["deployment.execute"]


def test_agent_identity_is_mission_scoped_and_restricted() -> None:
    response = create_agent_identity(
        AgentIdentityRequest(
            profile_id="backend_engineer",
            organization_id="org-1",
            mission_id="mission-1",
            capabilities=["fastapi_development"],
            allowed_tools=["repository.patch"],
            maximum_risk_level="medium",
        )
    )

    assert response.principal.identity_type == "agent"
    assert response.runtime_claims["mission_bound"] is True
    assert "cannot_count_as_human_approval" in response.restrictions


def test_governance_summary_marks_enterprise_sso_as_future_work() -> None:
    summary = governance_summary()

    assert summary.default_deny is True
    assert summary.mvp_readiness["rbac"] is True
    assert summary.mvp_readiness["enterprise_sso"] is False


def test_identity_persistence_models_store_governance_records_without_secret_material() -> None:
    token = issue_api_token(
        ApiTokenIssueRequest(name="Vault token", owner_id="user-1", scopes=["repository.read"], expires_in_days=1)
    )
    api_token = ArceusApiToken(
        name=token.name,
        prefix=token.prefix,
        checksum_sha256=token.checksum,
        scopes=token.scopes,
        environment=token.environment,
        expires_at=token.expires_at,
        metadata_json={"vault_backed": True, "secret_material_stored": False},
    )
    decision = evaluate_authorization(
        AuthorizationDecisionRequest(
            principal=human_principal(permissions=["repository.read"]),
            action="repository.read",
            resource=AuthorizationResource(resource_type="repository", resource_id="repo-1", organization_id="org-1"),
        )
    )
    persisted_decision = ArceusAuthorizationDecision(
        actor_type="human",
        actor_id="user-1",
        action="repository.read",
        resource_type="repository",
        resource_id="repo-1",
        decision=decision.decision,
        allowed=decision.allowed,
        reason=decision.reason,
        matched_policies=decision.matched_policies,
        obligations=decision.obligations,
        effective_permissions=decision.effective_permissions,
        request_payload={},
    )
    service_account = ArceusServiceAccount(name="CI", scopes=["test.run"], allowed_environments=["staging"])
    agent_identity = ArceusAgentIdentity(profile_id="qa", capabilities=["test"], allowed_tools=["pytest"], restrictions=["cannot_count_as_human_approval"])
    session = ArceusUserSession(user_id=None, status="high_risk", risk_score=75, expires_at=token.expires_at)
    provider = ArceusIdentityProvider(provider_key="clerk", provider_type="clerk", capabilities=["mfa"], scim_enabled=True)

    assert api_token.checksum_sha256 == token.checksum
    assert "one_time_token" not in api_token.metadata_json
    assert persisted_decision.allowed is True
    assert service_account.scopes == ["test.run"]
    assert agent_identity.restrictions == ["cannot_count_as_human_approval"]
    assert session.risk_score == 75
    assert provider.scim_enabled is True
