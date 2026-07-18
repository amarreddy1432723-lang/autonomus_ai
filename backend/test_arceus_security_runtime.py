from services.agent.arceus_runtime.security.service import (
    evaluate_security_policy,
    list_compliance_profiles,
    list_security_policies,
)


def test_security_policy_catalog_contains_zero_trust_controls() -> None:
    policies = {policy.policy_key: policy for policy in list_security_policies()}

    assert "zero_trust.identity_required" in policies
    assert "zero_trust.production_human_mfa" in policies
    assert "zero_trust.secret_reference_only" in policies
    assert policies["zero_trust.production_human_mfa"].severity == "critical"


def test_security_policy_denies_missing_identity() -> None:
    decision = evaluate_security_policy(subject={}, action="tool.execute", resource={})

    assert decision.decision == "deny"
    assert decision.policy_key == "zero_trust.identity_required"
    assert "authenticate_subject" in decision.obligations


def test_security_policy_requires_mfa_for_production() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "user-1", "identity_type": "human", "human_approved": True},
        action="production_deploy",
        resource={"resource_type": "environment", "environment": "production"},
        environment="production",
    )

    assert decision.decision == "deny"
    assert decision.policy_key == "zero_trust.production_human_mfa"
    assert "complete_mfa" in decision.obligations


def test_security_policy_blocks_ai_human_approval() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "ai-1", "identity_type": "ai_specialist", "mfa_verified": True},
        action="completion.approve",
        resource={"resource_type": "mission"},
    )

    assert decision.decision == "deny"
    assert decision.policy_key == "zero_trust.ai_no_human_approval"


def test_security_policy_requires_secret_references() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "user-1", "identity_type": "human", "mfa_verified": True},
        action="secret.access",
        resource={"resource_type": "secret", "direct_secret_value": True},
    )

    assert decision.decision == "deny"
    assert decision.policy_key == "zero_trust.secret_reference_only"


def test_security_policy_blocks_restricted_data_on_standard_cloud_model() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "user-1", "identity_type": "human"},
        action="ai.execute",
        resource={"data_classification": "restricted", "provider_class": "cloud", "data_retention_policy": "standard"},
    )

    assert decision.decision == "deny"
    assert decision.policy_key == "zero_trust.restricted_data_model_boundary"


def test_security_policy_allows_restricted_data_on_zero_retention_model() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "user-1", "identity_type": "human"},
        action="ai.execute",
        resource={"data_classification": "restricted", "provider_class": "cloud", "data_retention_policy": "zero_retention"},
    )

    assert decision.decision == "allow"


def test_security_policy_requires_review_for_high_risk_tool_execution() -> None:
    decision = evaluate_security_policy(
        subject={"identity_id": "user-1", "identity_type": "human"},
        action="tool.execute",
        resource={"tool": "github", "action": "merge"},
        risk_level="high",
    )

    assert decision.decision == "needs_approval"
    assert decision.policy_key == "zero_trust.high_risk_review"
    assert "create_security_review" in decision.obligations


def test_compliance_profiles_are_available_for_release_gate() -> None:
    profiles = {profile["profile_key"]: profile for profile in list_compliance_profiles()}

    assert {"soc2", "iso27001", "gdpr"}.issubset(profiles)
    assert "POLICY_DENIED" in profiles["soc2"]["required_security_events"]
