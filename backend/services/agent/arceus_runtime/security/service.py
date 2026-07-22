from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusSecurityAsset,
    ArceusSecurityEvidence,
    ArceusSecurityException,
    ArceusSecurityFinding,
    ArceusSecurityIncident,
    ArceusSecurityResponseAction,
    ArceusSecurityRiskScore,
)

from .api_schemas import (
    SecurityAssetRequest,
    SecurityEvidenceRequest,
    SecurityExceptionRequest,
    SecurityFindingRequest,
    SecurityGateRequest,
    SecurityGateResponse,
    SecurityOpsIncidentRequest,
    SecurityResponseActionRequest,
)


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


SEVERITY_SCORES = {"informational": 5, "low": 20, "medium": 40, "high": 70, "critical": 90}
CRITICALITY_SCORES = {"low": 5, "medium": 15, "high": 25, "critical": 35}
AUTO_CONTAINMENT_ACTIONS = {"isolate_agent", "pause_mission", "block_deployment"}


def upsert_security_asset(db: Session, *, tenant_id: UUID, payload: SecurityAssetRequest) -> ArceusSecurityAsset:
    item = None
    if payload.external_reference:
        item = (
            db.query(ArceusSecurityAsset)
            .filter(
                ArceusSecurityAsset.tenant_id == tenant_id,
                ArceusSecurityAsset.asset_type == payload.asset_type,
                ArceusSecurityAsset.external_reference == payload.external_reference,
            )
            .first()
        )
    if item is None:
        item = ArceusSecurityAsset(tenant_id=tenant_id)
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.last_seen_at = datetime.now(timezone.utc)
    db.flush()
    return item


def normalize_finding(db: Session, *, tenant_id: UUID, payload: SecurityFindingRequest) -> tuple[ArceusSecurityFinding, bool]:
    if payload.category == "secret_exposure" and _contains_raw_secret(payload.enrichment):
        raise ValueError("RAW_SECRET_VALUES_NOT_ALLOWED")
    fingerprint = finding_fingerprint(payload)
    existing = (
        db.query(ArceusSecurityFinding)
        .filter(ArceusSecurityFinding.tenant_id == tenant_id, ArceusSecurityFinding.fingerprint == fingerprint)
        .first()
    )
    if existing is not None:
        existing.last_detected_at = datetime.now(timezone.utc)
        existing.evidence_references = sorted(set((existing.evidence_references or []) + payload.evidence_references))
        existing.enrichment = {**(existing.enrichment or {}), **payload.enrichment}
        existing.remediation = {**(existing.remediation or {}), **payload.remediation}
        if existing.status in {"resolved", "false_positive"}:
            existing.status = "open"
        db.flush()
        return existing, False

    item = ArceusSecurityFinding(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        status="open",
        **payload.model_dump(),
    )
    db.add(item)
    db.flush()
    return item, True


def calculate_risk_score(db: Session, *, tenant_id: UUID, finding: ArceusSecurityFinding) -> ArceusSecurityRiskScore:
    asset = db.query(ArceusSecurityAsset).filter(ArceusSecurityAsset.tenant_id == tenant_id, ArceusSecurityAsset.id == finding.asset_id).first()
    enrichment = finding.enrichment or {}
    base = SEVERITY_SCORES.get(finding.severity, 40)
    exploitability = _score_bool(enrichment.get("exploit_available") or enrichment.get("known_exploited"), 25, 5)
    reachability = _score_bool(enrichment.get("reachable"), 20, 5)
    exposure = 25 if getattr(asset, "internet_exposed", False) else 8
    criticality = CRITICALITY_SCORES.get(getattr(asset, "criticality", "medium"), 15)
    privilege = _bounded_int(enrichment.get("privilege_impact_score"), default=15)
    data = 25 if _has_sensitive_data(asset) or enrichment.get("sensitive_data_access") else 5
    threat = 25 if enrichment.get("active_exploitation") or enrichment.get("threat_activity") == "active" else 5
    reduction = _bounded_int(enrichment.get("compensating_control_reduction"), default=0)
    total = min(100, max(0, int((base * 0.35) + exploitability + reachability + exposure + criticality + privilege + data + threat - reduction)))
    risk_level = "emergency" if total >= 95 else "critical" if total >= 80 else "high" if total >= 65 else "moderate" if total >= 40 else "low"
    item = ArceusSecurityRiskScore(
        tenant_id=tenant_id,
        finding_id=finding.id,
        base_severity_score=base,
        exploitability_score=exploitability,
        reachability_score=reachability,
        exposure_score=exposure,
        asset_criticality_score=criticality,
        privilege_impact_score=privilege,
        data_impact_score=data,
        threat_activity_score=threat,
        compensating_control_reduction=reduction,
        total_score=total,
        risk_level=risk_level,
        explanation={
            "severity": finding.severity,
            "asset_criticality": getattr(asset, "criticality", None),
            "internet_exposed": getattr(asset, "internet_exposed", False),
            "active_exploitation": bool(enrichment.get("active_exploitation")),
            "sensitive_data": _has_sensitive_data(asset),
        },
    )
    db.add(item)
    db.flush()
    return item


def evaluate_security_gate(db: Session, *, tenant_id: UUID, payload: SecurityGateRequest) -> SecurityGateResponse:
    query = db.query(ArceusSecurityFinding).filter(
        ArceusSecurityFinding.tenant_id == tenant_id,
        ArceusSecurityFinding.status.in_(["open", "triaged", "remediating"]),
    )
    if payload.asset_ids:
        query = query.filter(ArceusSecurityFinding.asset_id.in_(payload.asset_ids))
    findings = query.all()
    active_exception_ids = set()
    if payload.allow_active_exceptions:
        exceptions = (
            db.query(ArceusSecurityException)
            .filter(
                ArceusSecurityException.tenant_id == tenant_id,
                ArceusSecurityException.status == "active",
                ArceusSecurityException.expires_at > datetime.now(timezone.utc),
            )
            .all()
        )
        active_exception_ids = {item.finding_id for item in exceptions}

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for finding in findings:
        if finding.id in active_exception_ids:
            continue
        risk = latest_risk_score(db, tenant_id=tenant_id, finding_id=finding.id)
        risk_level = risk.risk_level if risk else "critical" if finding.severity == "critical" else "high" if finding.severity == "high" else "moderate"
        item = {"finding_id": str(finding.id), "title": finding.title, "severity": finding.severity, "risk_level": risk_level}
        if risk_level in {"critical", "emergency"} or finding.severity == "critical":
            blockers.append(item)
        elif risk_level == "high" or finding.severity == "high":
            warnings.append(item)

    obligations = ["record_security_gate_decision"]
    decision = "allow"
    if blockers:
        decision = "block"
        obligations.extend(["create_remediation_mission", "security_review_required"])
    elif warnings and payload.environment_type == "production":
        decision = "needs_approval"
        obligations.append("production_security_approval")
    return SecurityGateResponse(gate_type=payload.gate_type, decision=decision, blockers=blockers, warnings=warnings, obligations=obligations)


def latest_risk_score(db: Session, *, tenant_id: UUID, finding_id: UUID) -> ArceusSecurityRiskScore | None:
    return (
        db.query(ArceusSecurityRiskScore)
        .filter(ArceusSecurityRiskScore.tenant_id == tenant_id, ArceusSecurityRiskScore.finding_id == finding_id)
        .order_by(ArceusSecurityRiskScore.calculated_at.desc())
        .first()
    )


def declare_security_incident(db: Session, *, tenant_id: UUID, payload: SecurityOpsIncidentRequest) -> ArceusSecurityIncident:
    values = payload.model_dump(mode="python", exclude={"affected_asset_ids", "finding_ids"})
    item = ArceusSecurityIncident(
        tenant_id=tenant_id,
        status="declared",
        affected_asset_ids=[str(item) for item in payload.affected_asset_ids],
        finding_ids=[str(item) for item in payload.finding_ids],
        **values,
    )
    db.add(item)
    db.flush()
    return item


def create_response_action(db: Session, *, tenant_id: UUID, payload: SecurityResponseActionRequest) -> ArceusSecurityResponseAction:
    automatic_allowed = payload.action_type in AUTO_CONTAINMENT_ACTIONS and payload.risk_level in {"low", "moderate", "high"}
    approval_status = "not_required" if automatic_allowed else "pending"
    execution_status = "queued" if automatic_allowed else "blocked"
    item = ArceusSecurityResponseAction(
        tenant_id=tenant_id,
        automatic_allowed=automatic_allowed,
        approval_status=approval_status,
        execution_status=execution_status,
        metadata_json=payload.metadata,
        **payload.model_dump(exclude={"metadata"}),
    )
    db.add(item)
    db.flush()
    return item


def approve_exception(db: Session, *, tenant_id: UUID, payload: SecurityExceptionRequest) -> ArceusSecurityException:
    item = ArceusSecurityException(tenant_id=tenant_id, status="active", **payload.model_dump())
    db.add(item)
    finding = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == tenant_id, ArceusSecurityFinding.id == payload.finding_id).first()
    if finding and finding.status == "open":
        finding.status = "accepted"
    db.flush()
    return item


def store_security_evidence(db: Session, *, tenant_id: UUID, payload: SecurityEvidenceRequest) -> ArceusSecurityEvidence:
    item = ArceusSecurityEvidence(tenant_id=tenant_id, metadata_json=payload.metadata, **payload.model_dump(exclude={"metadata"}))
    db.add(item)
    db.flush()
    return item


def security_dashboard(db: Session, *, tenant_id: UUID) -> dict[str, Any]:
    open_findings = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == tenant_id, ArceusSecurityFinding.status.in_(["open", "triaged", "remediating"])).count()
    critical_findings = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == tenant_id, ArceusSecurityFinding.status.in_(["open", "triaged", "remediating"]), ArceusSecurityFinding.severity == "critical").count()
    high_findings = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == tenant_id, ArceusSecurityFinding.status.in_(["open", "triaged", "remediating"]), ArceusSecurityFinding.severity == "high").count()
    exposed_critical_assets = db.query(ArceusSecurityAsset).filter(ArceusSecurityAsset.tenant_id == tenant_id, ArceusSecurityAsset.internet_exposed.is_(True), ArceusSecurityAsset.criticality == "critical").count()
    active_incidents = db.query(ArceusSecurityIncident).filter(ArceusSecurityIncident.tenant_id == tenant_id, ArceusSecurityIncident.status.in_(["declared", "triaged", "investigating", "contained"])).count()
    pending_actions = db.query(ArceusSecurityResponseAction).filter(ArceusSecurityResponseAction.tenant_id == tenant_id, ArceusSecurityResponseAction.execution_status.in_(["queued", "blocked", "executing"])).count()
    active_exceptions = db.query(ArceusSecurityException).filter(ArceusSecurityException.tenant_id == tenant_id, ArceusSecurityException.status == "active", ArceusSecurityException.expires_at > datetime.now(timezone.utc)).count()
    release_gate_status = "block" if critical_findings else "needs_approval" if high_findings else "allow"
    return {
        "open_findings": open_findings,
        "critical_findings": critical_findings,
        "high_findings": high_findings,
        "exposed_critical_assets": exposed_critical_assets,
        "active_incidents": active_incidents,
        "pending_response_actions": pending_actions,
        "active_exceptions": active_exceptions,
        "release_gate_status": release_gate_status,
    }


def finding_fingerprint(payload: SecurityFindingRequest) -> str:
    stable = {
        "asset_id": str(payload.asset_id),
        "category": payload.category,
        "affected_component": payload.affected_component,
        "vulnerability_ids": sorted(payload.vulnerability_ids),
        "location": payload.location,
        "source_rule": payload.enrichment.get("rule_id") or payload.source_finding_id,
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_action(action: str) -> str:
    return action.strip().lower().replace("_", ".")


def _score_bool(value: Any, true_score: int, false_score: int) -> int:
    return true_score if _bool(value) else false_score


def _bounded_int(value: Any, *, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _has_sensitive_data(asset: Any) -> bool:
    classifications = [str(item).lower() for item in (getattr(asset, "data_classifications", None) or [])]
    return any(item in {"pii", "phi", "pci", "secret", "restricted", "confidential"} for item in classifications)


def _contains_raw_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {"secret", "secret_value", "raw_secret", "password", "token", "api_key", "private_key"}:
                return True
            if _contains_raw_secret(child):
                return True
    if isinstance(value, list):
        return any(_contains_raw_secret(item) for item in value)
    return False


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
