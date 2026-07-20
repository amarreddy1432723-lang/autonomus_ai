from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..compiler.utils import stable_hash


RISK_ORDER = {"low": 1, "moderate": 2, "high": 3, "critical": 4}
DATA_RISK = {"public": 0, "internal": 10, "confidential": 24, "restricted": 36, "highly_restricted": 48}
LIFECYCLE_RISK = {"research": 4, "development": 8, "verification": 12, "approval": 18, "deployment": 28, "monitoring": 16, "retirement": 12}


@dataclass(frozen=True)
class GovernancePolicy:
    policy_key: str
    name: str
    domain: str
    description: str
    severity: str
    applies_to: tuple[str, ...]
    requirements: tuple[str, ...]
    version: str = "1.0"


POLICIES = (
    GovernancePolicy(
        "governance.human_oversight",
        "Human Oversight",
        "governance",
        "High-risk or critical actions require designated human approval.",
        "high",
        ("deployment", "production", "delete", "secret", "payment", "plugin", "automation"),
        ("documented_rationale", "human_approval", "audit_event"),
    ),
    GovernancePolicy(
        "governance.data_privacy",
        "Sensitive Data Protection",
        "privacy",
        "AI processing of confidential or restricted data requires minimization, masking, consent, and retention controls.",
        "critical",
        ("data", "model", "tool", "automation", "connector"),
        ("data_classification", "minimization", "masking", "retention_policy", "consent_basis"),
    ),
    GovernancePolicy(
        "governance.supply_chain",
        "Supply Chain Provenance",
        "supply_chain",
        "Plugins, containers, dependencies, and generated artifacts require provenance and vulnerability review.",
        "high",
        ("plugin", "dependency", "container", "workflow", "sdk", "artifact"),
        ("provenance", "signature_or_checksum", "sbom", "vulnerability_scan"),
    ),
    GovernancePolicy(
        "governance.model_registry",
        "Registered Model Execution",
        "ai_governance",
        "No AI model executes outside registry, risk assessment, lifecycle state, and monitoring policy.",
        "high",
        ("model", "ai_execution", "agent", "automation"),
        ("model_registered", "risk_profile", "approval_status", "usage_monitoring"),
    ),
    GovernancePolicy(
        "governance.content_safety",
        "Content Safety and Prompt Injection Defense",
        "safety",
        "Unsafe content, prompt injection, credential leakage, and tool-boundary attacks must be detected before execution.",
        "critical",
        ("prompt", "document", "connector", "plugin", "automation", "tool"),
        ("trusted_context", "instruction_hierarchy", "secret_scan", "tool_boundary"),
    ),
    GovernancePolicy(
        "governance.compliance_pack",
        "Compliance Policy Pack",
        "compliance",
        "Regulated work maps to executable framework controls and audit evidence.",
        "high",
        ("deployment", "payment", "healthcare", "customer_data", "enterprise"),
        ("framework_mapping", "control_validation", "evidence", "audit_trail"),
    ),
)


COMPLIANCE_CONTROLS = {
    "gdpr": (
        {"control": "lawful_basis", "requirement": "Document lawful basis and consent for personal data processing."},
        {"control": "data_minimization", "requirement": "Limit prompts, retrieval, and retention to necessary fields."},
        {"control": "erasure_ready", "requirement": "Support deletion and revocation workflows."},
    ),
    "hipaa": (
        {"control": "phi_access_boundary", "requirement": "Restrict health data access to approved roles and tools."},
        {"control": "audit_controls", "requirement": "Record access, transformation, and disclosure events."},
        {"control": "encryption", "requirement": "Encrypt PHI at rest and in transit."},
    ),
    "soc2": (
        {"control": "change_management", "requirement": "Require review, verification, and rollback for production changes."},
        {"control": "access_control", "requirement": "Enforce least privilege and separation of duties."},
        {"control": "monitoring", "requirement": "Monitor incidents, availability, and privileged actions."},
    ),
    "iso27001": (
        {"control": "risk_treatment", "requirement": "Record risk owner, treatment, and residual risk."},
        {"control": "supplier_security", "requirement": "Validate third-party providers and dependencies."},
    ),
    "pci": (
        {"control": "cardholder_data_scope", "requirement": "Keep payment data out of AI prompts unless explicitly approved."},
        {"control": "key_management", "requirement": "Do not expose secrets, tokens, or card data to models."},
    ),
    "nist_csf": (
        {"control": "identify_protect_detect", "requirement": "Map governance decision to identify, protect, detect, respond, recover."},
    ),
    "iso42001": (
        {"control": "ai_management_system", "requirement": "Track model lifecycle, risk profile, oversight, and monitoring."},
        {"control": "human_oversight", "requirement": "Require human review for high-impact AI decisions."},
    ),
}


CONTENT_PATTERNS = {
    "credential_leakage": ("sk-", "bearer ", "password=", "token=", "secret=", "api_key"),
    "prompt_injection": ("ignore previous", "system prompt", "developer message", "jailbreak", "override instructions"),
    "malware": ("ransomware", "keylogger", "credential stealer", "persistence mechanism"),
    "unsafe_automation": ("delete production", "drop database", "disable audit", "bypass approval"),
}


def list_governance_policies() -> list[dict[str, Any]]:
    return [
        {
            "policy_key": policy.policy_key,
            "name": policy.name,
            "domain": policy.domain,
            "description": policy.description,
            "severity": policy.severity,
            "applies_to": list(policy.applies_to),
            "requirements": list(policy.requirements),
            "version": policy.version,
        }
        for policy in POLICIES
    ]


def normalize_level(value: str) -> str:
    cleaned = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in {"highlyrestricted", "highly_restricted"}:
        return "highly_restricted"
    return cleaned


def classify_risk(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 32:
        return "moderate"
    return "low"


def selected_policy(action: str, object_type: str, capabilities: list[str]) -> GovernancePolicy:
    haystack = " ".join([action, object_type, *capabilities]).lower()
    for policy in POLICIES:
        if any(term in haystack for term in policy.applies_to):
            return policy
    return POLICIES[0]


def content_safety_scan(payload: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(value)
        for value in [
            payload.get("action"),
            payload.get("object_type"),
            payload.get("context", {}),
            payload.get("artifact", {}),
        ]
    ).lower()
    findings = [
        {"type": finding, "severity": "critical" if finding in {"credential_leakage", "malware"} else "high"}
        for finding, patterns in CONTENT_PATTERNS.items()
        if any(pattern in text for pattern in patterns)
    ]
    return {
        "safe": not findings,
        "findings": findings,
        "controls": ["trusted_context_validation", "instruction_hierarchy", "secret_redaction", "tool_boundary_enforcement"],
    }


def privacy_impact(payload: dict[str, Any]) -> dict[str, Any]:
    classification = normalize_level(payload.get("data_classification", "internal"))
    contains_sensitive = classification in {"confidential", "restricted", "highly_restricted"}
    controls = ["data_classification", "access_control"]
    if contains_sensitive:
        controls.extend(["minimization", "masking", "purpose_limitation", "retention_enforcement"])
    if classification in {"restricted", "highly_restricted"}:
        controls.extend(["consent_basis_required", "regional_residency_check", "no_public_model_without_zero_retention"])
    return {
        "classification": classification,
        "requires_consent": classification in {"restricted", "highly_restricted"},
        "ai_access": "blocked_without_approval" if classification == "highly_restricted" else ("restricted" if contains_sensitive else "allowed"),
        "controls": controls,
    }


def compliance_mapping(frameworks: list[str], *, risk_level: str) -> dict[str, Any]:
    normalized = [normalize_level(item) for item in frameworks]
    controls: list[dict[str, Any]] = []
    for framework in normalized:
        controls.extend({"framework": framework, **control} for control in COMPLIANCE_CONTROLS.get(framework, ()))
    blockers = []
    warnings = []
    if risk_level in {"high", "critical"} and not controls:
        blockers.append("high_risk_action_requires_compliance_framework_mapping")
    if "pci" in normalized:
        warnings.append("payment_scope_requires_secret_and_cardholder_data_exclusion")
    if "hipaa" in normalized:
        warnings.append("health_data_requires_phi_audit_controls")
    return {
        "frameworks": normalized,
        "controls": controls,
        "blockers": blockers,
        "warnings": warnings,
        "ready": not blockers,
    }


def supply_chain_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact") or {}
    object_type = normalize_level(payload.get("object_type", ""))
    relevant = object_type in {"plugin", "dependency", "container", "workflow", "sdk", "artifact"} or bool(artifact)
    provenance = artifact.get("provenance") or artifact.get("source")
    checksum = artifact.get("checksum") or artifact.get("sha256") or artifact.get("signature")
    sbom = artifact.get("sbom") or artifact.get("sbom_url")
    vulnerabilities = artifact.get("vulnerabilities") or []
    findings = []
    if relevant and not provenance:
        findings.append({"type": "missing_provenance", "severity": "high"})
    if relevant and not checksum:
        findings.append({"type": "missing_signature_or_checksum", "severity": "moderate"})
    if relevant and not sbom:
        findings.append({"type": "missing_sbom", "severity": "moderate"})
    for vuln in vulnerabilities:
        severity = normalize_level(str(vuln.get("severity", "moderate"))) if isinstance(vuln, dict) else "moderate"
        if severity in {"high", "critical"}:
            findings.append({"type": "known_vulnerability", "severity": severity, "detail": vuln})
    return {
        "required": relevant,
        "valid": not any(item["severity"] in {"high", "critical"} for item in findings),
        "findings": findings,
        "controls": ["provenance", "signature_or_checksum", "sbom", "vulnerability_scan"],
    }


def model_risk_profile(model: Any, provider: Any | None = None) -> dict[str, Any]:
    capabilities = set(model.capabilities or [])
    risks = []
    score = 10
    if "code_generation" in capabilities or "tool_use" in capabilities:
        risks.append("unsafe_tool_or_code_generation")
        score += 20
    if "autonomous_execution" in capabilities or "agent" in capabilities:
        risks.append("autonomous_action_risk")
        score += 25
    if model.data_retention_policy not in {"zero", "none", "no_retention"}:
        risks.append("provider_retention_policy")
        score += 12
    if provider is not None and getattr(provider, "enterprise_agreement_required", False):
        risks.append("enterprise_agreement_required")
        score += 10
    reliability = float(model.reliability_score or 0.8)
    if reliability < 0.75:
        risks.append("operational_reliability")
        score += 18
    risk_level = classify_risk(score)
    return {
        "model_key": model.model_key,
        "provider_key": model.provider_key,
        "display_name": model.display_name,
        "status": model.status,
        "lifecycle_stage": "deployment" if model.status == "available" else model.status,
        "risk_level": risk_level,
        "approval_status": "approved" if risk_level in {"low", "moderate"} and model.status == "available" else "needs_review",
        "known_risks": risks,
        "controls": ["registry_entry", "risk_profile", "usage_monitoring", "output_verification"],
        "monitoring_intensity": monitoring_for_risk(risk_level)["intensity"],
    }


def default_model_registry() -> list[dict[str, Any]]:
    return [
        {
            "model_key": "arceus-codex-auto",
            "provider_key": "local",
            "display_name": "Arceus Codex Auto",
            "status": "available",
            "lifecycle_stage": "development",
            "risk_level": "moderate",
            "approval_status": "approved_for_local_dev",
            "known_risks": ["deterministic_fallback", "limited_external_reasoning"],
            "controls": ["local_execution", "receipt_required", "rollback_required"],
            "monitoring_intensity": "standard",
        }
    ]


def monitoring_for_risk(risk_level: str) -> dict[str, Any]:
    if risk_level == "critical":
        return {"intensity": "continuous", "log_level": "full_audit", "automation_boundary": "human_approved_only"}
    if risk_level == "high":
        return {"intensity": "enhanced", "log_level": "decision_and_evidence", "automation_boundary": "approval_gated"}
    if risk_level == "moderate":
        return {"intensity": "standard", "log_level": "decision", "automation_boundary": "policy_limited"}
    return {"intensity": "sampled", "log_level": "summary", "automation_boundary": "autonomous_allowed"}


def evaluate_governance(payload: dict[str, Any]) -> dict[str, Any]:
    action = normalize_level(payload.get("action", ""))
    object_type = normalize_level(payload.get("object_type", ""))
    data_classification = normalize_level(payload.get("data_classification", "internal"))
    lifecycle_stage = normalize_level(payload.get("lifecycle_stage", "development"))
    capabilities = [normalize_level(item) for item in payload.get("capabilities", [])]
    policy = selected_policy(action, object_type, capabilities)

    score = 8 + DATA_RISK.get(data_classification, 10) + LIFECYCLE_RISK.get(lifecycle_stage, 8)
    high_risk_terms = {"deploy", "production", "delete", "secret", "payment", "plugin", "connector", "automation", "model", "execute", "merge"}
    score += sum(8 for term in high_risk_terms if term in action or term in object_type)
    score += 12 if payload.get("model_key") and object_type in {"model", "ai_execution", "agent", "automation"} else 0
    score += 8 if not payload.get("evidence_ids") else -5
    score += 10 if lifecycle_stage in {"deployment", "approval"} and not payload.get("approvals") else 0

    safety = content_safety_scan(payload)
    privacy = privacy_impact(payload)
    supply_chain = supply_chain_assessment(payload)
    if not safety["safe"]:
        score += max(18, len(safety["findings"]) * 12)
    if privacy["ai_access"] == "blocked_without_approval":
        score += 20
    if not supply_chain["valid"]:
        score += 18

    risk_level = classify_risk(min(score, 100))
    compliance = compliance_mapping(payload.get("frameworks", []), risk_level=risk_level)
    required_approvals = required_approvals_for(risk_level, payload)

    blockers = []
    if not safety["safe"]:
        blockers.append("content_safety_findings")
    if privacy["ai_access"] == "blocked_without_approval" and not payload.get("approvals"):
        blockers.append("sensitive_data_requires_approval")
    if supply_chain["required"] and not supply_chain["valid"]:
        blockers.append("supply_chain_validation_failed")
    blockers.extend(compliance["blockers"])

    if blockers:
        decision = "deny" if risk_level == "critical" and not payload.get("approvals") else "needs_approval"
        reason = f"Governance blocked or gated action due to {', '.join(blockers)}."
    elif required_approvals and not payload.get("approvals"):
        decision = "needs_approval"
        reason = "Human oversight is required before execution."
    else:
        decision = "allow"
        reason = "Action is within executable governance policy."

    controls = sorted(set([*policy.requirements, *privacy["controls"], *supply_chain["controls"], *safety["controls"], "audit_event"]))
    events = ["RISK_REASSESSED", "COMPLIANCE_CHECK_COMPLETED", "AUDIT_LOG_WRITTEN"]
    if not safety["safe"]:
        events.append("PROMPT_ATTACK_DETECTED")
    if supply_chain["required"]:
        events.append("SUPPLY_CHAIN_VALIDATED")
    return {
        "policy_key": policy.policy_key,
        "action": payload.get("action"),
        "object_type": payload.get("object_type"),
        "decision": decision,
        "risk_level": risk_level,
        "risk_score": min(score, 100),
        "reason": reason,
        "required_approvals": required_approvals,
        "controls": controls,
        "compliance": compliance,
        "privacy": privacy,
        "content_safety": safety,
        "supply_chain": supply_chain,
        "monitoring": monitoring_for_risk(risk_level),
        "events": events,
    }


def required_approvals_for(risk_level: str, payload: dict[str, Any]) -> list[str]:
    approvals = []
    if risk_level in {"high", "critical"}:
        approvals.append("human_reviewer")
    if risk_level == "critical":
        approvals.append("security_reviewer")
    if normalize_level(payload.get("lifecycle_stage", "")) == "deployment":
        approvals.append("production_operator")
    if normalize_level(payload.get("data_classification", "")) in {"restricted", "highly_restricted"}:
        approvals.append("privacy_reviewer")
    return sorted(set(approvals))


def compliance_report(frameworks: list[str], evaluations: list[Any] | None = None) -> dict[str, Any]:
    normalized = [normalize_level(item) for item in frameworks] or ["soc2", "iso42001"]
    control_map = compliance_mapping(normalized, risk_level="moderate")
    deny_count = sum(1 for item in evaluations or [] if getattr(item, "decision", "") == "deny")
    approval_count = sum(1 for item in evaluations or [] if getattr(item, "decision", "") == "needs_approval")
    blockers = list(control_map["blockers"])
    warnings = list(control_map["warnings"])
    if deny_count:
        blockers.append("recent_denied_governance_decisions")
    if approval_count:
        warnings.append("open_governance_reviews")
    return {
        "frameworks": normalized,
        "controls": control_map["controls"],
        "blockers": blockers,
        "warnings": warnings,
        "ready": not blockers,
        "checked_at": datetime.now(timezone.utc),
    }


def governance_dashboard(models: list[dict[str, Any]], evaluations: list[Any], audit_events: list[Any]) -> dict[str, Any]:
    decision_counts = {"allow": 0, "needs_approval": 0, "deny": 0}
    risk_counts = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
    for item in evaluations:
        decision_counts[getattr(item, "decision", "allow")] = decision_counts.get(getattr(item, "decision", "allow"), 0) + 1
        resource = getattr(item, "resource", {}) or {}
        risk_counts[resource.get("risk_level", "moderate")] = risk_counts.get(resource.get("risk_level", "moderate"), 0) + 1
    critical_models = sum(1 for item in models if item.get("risk_level") == "critical")
    high_models = sum(1 for item in models if item.get("risk_level") == "high")
    status = "blocked" if decision_counts["deny"] else ("review_required" if decision_counts["needs_approval"] or critical_models else "healthy")
    return {
        "status": status,
        "risk": {"counts": risk_counts, "high_or_critical_models": high_models + critical_models},
        "compliance": {"frameworks": ["soc2", "iso42001"], "continuous_validation": True},
        "privacy": {"data_classes": list(DATA_RISK.keys()), "sensitive_controls_enabled": True},
        "model_registry": {"registered": len(models), "needs_review": sum(1 for item in models if item.get("approval_status") != "approved")},
        "incidents": {"open": sum(1 for event in audit_events if "INCIDENT" in getattr(event, "action", ""))},
        "policy_activity": {"decisions": decision_counts, "audit_events": len(audit_events)},
        "open_reviews": decision_counts["needs_approval"],
        "refreshed_at": datetime.now(timezone.utc),
    }


def governance_memory_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "payload": payload, "content_hash": stable_hash({"kind": kind, "payload": payload})}
