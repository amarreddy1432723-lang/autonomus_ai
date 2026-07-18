from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SECURITY_EVENTS = (
    "LOGIN_SUCCESS",
    "LOGIN_FAILURE",
    "TOKEN_ISSUED",
    "TOKEN_REVOKED",
    "POLICY_DENIED",
    "SECRET_ACCESSED",
    "SANDBOX_CREATED",
    "SANDBOX_ESCAPE_ATTEMPT",
    "PROMPT_BLOCKED",
    "TOOL_DENIED",
    "PROVIDER_BLOCKED",
    "ARTIFACT_SIGNED",
    "MISSION_CERTIFIED",
)


@dataclass(frozen=True)
class SecurityPolicy:
    policy_key: str
    name: str
    description: str
    severity: str
    protected_actions: tuple[str, ...]


@dataclass(frozen=True)
class SecurityDecision:
    policy_key: str
    decision: str
    reason: str
    obligations: tuple[str, ...] = ()


POLICIES: tuple[SecurityPolicy, ...] = (
    SecurityPolicy(
        policy_key="zero_trust.identity_required",
        name="Identity Required",
        description="Every security-sensitive action must have a verifiable subject identity.",
        severity="critical",
        protected_actions=("*",),
    ),
    SecurityPolicy(
        policy_key="zero_trust.production_human_mfa",
        name="Production Requires Human MFA",
        description="Production actions require a human actor, MFA, and explicit human approval.",
        severity="critical",
        protected_actions=("deploy", "production_deploy", "secret.access", "policy.change"),
    ),
    SecurityPolicy(
        policy_key="zero_trust.ai_no_human_approval",
        name="AI Cannot Count As Human Approval",
        description="AI specialists may recommend but never satisfy human approval requirements.",
        severity="high",
        protected_actions=("approve", "completion.approve", "merge", "production_deploy"),
    ),
    SecurityPolicy(
        policy_key="zero_trust.secret_reference_only",
        name="Secrets Are Reference Only",
        description="Secrets must be accessed through references and never exposed as direct values.",
        severity="critical",
        protected_actions=("secret.access", "tool.execute", "model.execute"),
    ),
    SecurityPolicy(
        policy_key="zero_trust.restricted_data_model_boundary",
        name="Restricted Data Model Boundary",
        description="Restricted or secret data cannot be sent to non-local or non-zero-retention model providers.",
        severity="critical",
        protected_actions=("model.route", "model.execute", "ai.execute"),
    ),
    SecurityPolicy(
        policy_key="zero_trust.high_risk_review",
        name="High Risk Requires Review",
        description="High-risk destructive or externally visible actions require review before execution.",
        severity="high",
        protected_actions=("delete", "rename", "merge", "deploy", "production_deploy", "tool.execute"),
    ),
)


COMPLIANCE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile_key": "soc2",
        "name": "SOC 2",
        "controls": ["access_control", "audit_logging", "change_management", "incident_response"],
        "retention_policy": {"audit": "7 years", "logs": "90 days", "working_memory": "72 hours"},
        "required_security_events": ["POLICY_DENIED", "SECRET_ACCESSED", "ARTIFACT_SIGNED", "MISSION_CERTIFIED"],
    },
    {
        "profile_key": "iso27001",
        "name": "ISO 27001",
        "controls": ["risk_management", "asset_control", "supplier_security", "business_continuity"],
        "retention_policy": {"audit": "7 years", "logs": "90 days", "working_memory": "72 hours"},
        "required_security_events": ["POLICY_DENIED", "TOKEN_REVOKED", "SANDBOX_ESCAPE_ATTEMPT"],
    },
    {
        "profile_key": "gdpr",
        "name": "GDPR",
        "controls": ["data_minimization", "data_residency", "deletion_rights", "processor_audit"],
        "retention_policy": {"audit": "7 years", "logs": "90 days", "working_memory": "72 hours"},
        "required_security_events": ["POLICY_DENIED", "PROVIDER_BLOCKED", "SECRET_ACCESSED"],
    },
)


def list_security_policies() -> list[SecurityPolicy]:
    return list(POLICIES)


def list_compliance_profiles() -> list[dict[str, Any]]:
    return list(COMPLIANCE_PROFILES)


def _normalized_action(action: str) -> str:
    return action.strip().lower().replace("_", ".")


def _identity_type(subject: dict[str, Any]) -> str:
    return str(subject.get("identity_type") or subject.get("actor_type") or "unknown").strip().lower()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def evaluate_security_policy(
    *,
    subject: dict[str, Any],
    action: str,
    resource: dict[str, Any],
    environment: str = "development",
    risk_level: str = "medium",
    policy_key: str | None = None,
) -> SecurityDecision:
    normalized_action = _normalized_action(action)
    env = environment.strip().lower()
    risk = risk_level.strip().lower()
    identity_type = _identity_type(subject)

    if not subject.get("identity_id") and not subject.get("actor_id"):
        return SecurityDecision(
            policy_key="zero_trust.identity_required",
            decision="deny",
            reason="A verifiable subject identity is required.",
            obligations=("authenticate_subject",),
        )

    if policy_key and policy_key not in {policy.policy_key for policy in POLICIES}:
        return SecurityDecision(
            policy_key=policy_key,
            decision="deny",
            reason="Unknown policy key; fail closed.",
            obligations=("register_policy", "manual_security_review"),
        )

    if normalized_action in {"approve", "completion.approve", "merge", "production.deploy", "production_deploy"} and identity_type.startswith("ai"):
        return SecurityDecision(
            policy_key="zero_trust.ai_no_human_approval",
            decision="deny",
            reason="AI participants cannot satisfy human approval or merge authority.",
            obligations=("request_human_approval",),
        )

    if env == "production" or normalized_action in {"production.deploy", "production_deploy"}:
        if identity_type != "human":
            return SecurityDecision(
                policy_key="zero_trust.production_human_mfa",
                decision="deny",
                reason="Production actions require a human identity.",
                obligations=("route_to_production_operator",),
            )
        if not _bool(subject.get("mfa_verified")):
            return SecurityDecision(
                policy_key="zero_trust.production_human_mfa",
                decision="deny",
                reason="Production actions require MFA verification.",
                obligations=("complete_mfa",),
            )
        if not _bool(subject.get("human_approved")):
            return SecurityDecision(
                policy_key="zero_trust.production_human_mfa",
                decision="needs_approval",
                reason="Production action requires explicit human approval.",
                obligations=("create_approval_request",),
            )

    if normalized_action == "secret.access" or resource.get("resource_type") == "secret":
        if _bool(resource.get("direct_secret_value")):
            return SecurityDecision(
                policy_key="zero_trust.secret_reference_only",
                decision="deny",
                reason="Direct secret values are not permitted; use secret references only.",
                obligations=("replace_with_secret_reference",),
            )
        if identity_type.startswith("ai") and resource.get("environment") == "production":
            return SecurityDecision(
                policy_key="zero_trust.secret_reference_only",
                decision="deny",
                reason="AI participants cannot access production secrets.",
                obligations=("broker_temporary_credential_to_human_operator",),
            )
        if not _bool(subject.get("mfa_verified")):
            return SecurityDecision(
                policy_key="zero_trust.secret_reference_only",
                decision="needs_approval",
                reason="Secret access requires MFA-backed authorization.",
                obligations=("complete_mfa", "record_secret_access"),
            )

    data_classification = str(resource.get("data_classification") or resource.get("classification") or "").strip().lower()
    provider_class = str(resource.get("provider_class") or resource.get("model_provider_class") or "").strip().lower()
    retention = str(resource.get("data_retention_policy") or resource.get("retention_policy") or "").strip().lower()
    if normalized_action in {"model.route", "model.execute", "ai.execute"} and data_classification in {"restricted", "secret"}:
        if provider_class != "local" and retention != "zero_retention":
            return SecurityDecision(
                policy_key="zero_trust.restricted_data_model_boundary",
                decision="deny",
                reason="Restricted or secret data requires a local or zero-retention model boundary.",
                obligations=("use_local_model", "remove_sensitive_context"),
            )

    destructive_actions = {"delete", "rename", "merge", "deploy", "production.deploy", "production_deploy", "tool.execute"}
    if risk in {"high", "critical"} and normalized_action in destructive_actions and not _bool(subject.get("review_approved")):
        return SecurityDecision(
            policy_key="zero_trust.high_risk_review",
            decision="needs_approval",
            reason="High-risk action requires independent review before execution.",
            obligations=("create_security_review", "collect_evidence"),
        )

    return SecurityDecision(
        policy_key=policy_key or "zero_trust.default_allow",
        decision="allow",
        reason="No blocking Zero Trust policy matched.",
        obligations=("record_audit_event",),
    )
