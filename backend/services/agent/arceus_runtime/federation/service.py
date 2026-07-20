from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from ..compiler.utils import stable_hash


TRUST_ORDER = {"public": 1, "verified": 2, "partner": 3, "enterprise": 4, "internal": 5}
SENSITIVE_SCOPES = {"secrets", "private_repository", "billing", "identity", "customer_pii", "production_credentials"}
DEFAULT_SCOPES = {"capability_catalog", "verified_knowledge", "workflow_templates", "research_findings", "architecture_patterns", "policy_summaries"}
RESOURCE_COST = {"ai_specialists": 12.0, "compute": 0.08, "storage": 0.02, "datasets": 4.0, "tools": 2.0, "connectors": 3.0, "gpu_clusters": 18.0}


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def normalize_list(values: list[str]) -> list[str]:
    return sorted({normalize_key(item) for item in values if normalize_key(item)})


def organization_payload(payload: dict[str, Any]) -> dict[str, Any]:
    capabilities = normalize_list(payload.get("capabilities") or [])
    specializations = normalize_list(payload.get("specializations") or [])
    trust_level = normalize_key(payload.get("trust_level", "verified"))
    return {
        "organization_id": str(payload["organization_id"]),
        "name": str(payload["name"]),
        "capabilities": capabilities,
        "specializations": specializations,
        "certifications": normalize_list(payload.get("certifications") or []),
        "supported_domains": normalize_list(payload.get("supported_domains") or []),
        "resource_capacity": {normalize_key(key): float(value) for key, value in (payload.get("resource_capacity") or {}).items()},
        "trust_level": trust_level if trust_level in TRUST_ORDER else "public",
        "federation_status": normalize_key(payload.get("federation_status", "active")),
    }


def build_capability_index(members: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for member in members:
        for capability in [*member.get("capabilities", []), *member.get("specializations", [])]:
            if member["organization_id"] not in index[capability]:
                index[capability].append(member["organization_id"])
    return {key: sorted(value) for key, value in sorted(index.items())}


def create_federation(payload: dict[str, Any]) -> dict[str, Any]:
    members = [organization_payload(item) for item in payload.get("members") or []]
    governance = {
        "voting_model": (payload.get("governance") or {}).get("voting_model", "majority"),
        "dispute_resolution": (payload.get("governance") or {}).get("dispute_resolution", "negotiation_policy_executive_review_arbitration"),
        "approval_required_for_delegation": (payload.get("governance") or {}).get("approval_required_for_delegation", True),
        "audit_required": True,
        **(payload.get("governance") or {}),
    }
    return {
        "federation_id": "federation_" + stable_hash({"name": payload["name"], "objectives": payload["objectives"]})[:16],
        "name": payload["name"],
        "status": "forming" if len(members) < 2 else "active",
        "objectives": payload["objectives"],
        "governance": governance,
        "policies": normalize_list(payload.get("policies") or []),
        "trust_model": payload.get("trust_model", "verified_members_only"),
        "members": members,
        "capability_index": build_capability_index(members),
        "events": ["FEDERATION_CREATED"],
        "created_at": datetime.now(timezone.utc),
    }


def evaluate_join_request(payload: dict[str, Any]) -> dict[str, Any]:
    organization = organization_payload(payload["organization"])
    requested = normalize_list(payload.get("requested_scopes") or list(DEFAULT_SCOPES))
    trust = TRUST_ORDER.get(organization["trust_level"], 1)
    authorized = [scope for scope in requested if scope in DEFAULT_SCOPES and scope not in SENSITIVE_SCOPES and trust >= 2]
    denied = [scope for scope in requested if scope not in authorized]
    required = []
    if denied:
        required.extend(["federation_admin", "security_reviewer"])
    if trust < 2:
        required.append("trust_review")
    status = "joined" if not denied and trust >= 2 else "needs_approval"
    return {
        "federation_id": payload.get("federation_id"),
        "organization_id": organization["organization_id"],
        "status": status,
        "authorized_scopes": authorized,
        "denied_scopes": denied,
        "required_approvals": sorted(set(required)),
        "trust_level": organization["trust_level"],
        "events": ["ORGANIZATION_JOINED"] if status == "joined" else ["FEDERATION_POLICY_UPDATED"],
        "organization": organization,
    }


def score_organization(org: dict[str, Any], required_capabilities: list[str], policies: list[str] | None = None) -> dict[str, Any]:
    required = set(normalize_list(required_capabilities))
    capabilities = set(org.get("capabilities", [])) | set(org.get("specializations", []))
    matched = sorted(required.intersection(capabilities))
    coverage = len(matched) / max(1, len(required))
    trust_score = TRUST_ORDER.get(org.get("trust_level", "public"), 1) / 5
    certification_bonus = min(0.12, len(org.get("certifications", [])) * 0.03)
    capacity_score = min(1.0, sum(float(value) for value in (org.get("resource_capacity") or {}).values()) / 100.0)
    policy_penalty = 0.08 if policies and not set(normalize_list(policies)).intersection(set(org.get("certifications", []))) else 0
    score = round((coverage * 0.52) + (trust_score * 0.22) + (capacity_score * 0.14) + certification_bonus - policy_penalty, 4)
    return {"organization": org, "matched_capabilities": matched, "missing_capabilities": sorted(required - capabilities), "score": max(0.0, score)}


def build_delegation(payload: dict[str, Any]) -> dict[str, Any]:
    organizations = [organization_payload(item) for item in payload.get("candidate_organizations") or []]
    required = normalize_list(payload.get("required_capabilities") or [])
    matches = [score_organization(org, required, payload.get("governance_policies") or []) for org in organizations]
    matches.sort(key=lambda item: item["score"], reverse=True)
    selected = matches[0] if matches else None
    status = "contract_ready" if selected and selected["score"] >= 0.55 else "needs_capability_review"
    contract = {
        "scope": payload["global_mission"],
        "delegate_to": selected["organization"]["organization_id"] if selected else None,
        "deliverables": payload.get("deliverables") or [f"Deliver {capability}" for capability in required],
        "deadline": payload.get("deadline"),
        "evidence_requirements": payload.get("evidence_requirements") or ["work_receipt", "verification_evidence", "review_summary"],
        "sla": payload.get("sla") or {"response_time_hours": 24, "review_turnaround_hours": 48},
        "governance_policies": payload.get("governance_policies") or ["audit_required", "evidence_required"],
        "review_requirements": payload.get("review_requirements") or ["independent_review", "federation_coordinator_acceptance"],
        "immutable_after_approval": True,
        "contract_hash": stable_hash({"mission": payload["global_mission"], "selected": selected, "required": required}),
    }
    synchronization = [
        {"name": "contract_approval", "required": True, "owners": ["federation_coordinator", contract["delegate_to"]]},
        {"name": "evidence_return", "required": True, "owners": [contract["delegate_to"]]},
        {"name": "cross_review", "required": True, "owners": ["independent_member"]},
        {"name": "federation_verification", "required": True, "owners": ["federation_coordinator"]},
    ]
    return {
        "delegation_id": "delegation_" + stable_hash(contract)[:16],
        "selected_organization": selected["organization"] if selected else None,
        "capability_matches": matches,
        "contract": contract,
        "status": status,
        "synchronization_points": synchronization,
        "events": ["MISSION_DELEGATED"] if status == "contract_ready" else ["DISPUTE_OPENED"],
    }


def knowledge_share_decision(payload: dict[str, Any], members: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    required_trust = TRUST_ORDER.get(normalize_key(payload.get("trust_level_required", "verified")), 2)
    sensitivity = normalize_key(payload.get("sensitivity", "organization"))
    members_by_id = {member["organization_id"]: member for member in members or []}
    targets = payload.get("target_organization_ids") or list(members_by_id.keys())
    authorized = []
    denied = []
    filters = ["strip_private_fields", "preserve_provenance", "attach_evidence_links"]
    if sensitivity in {"restricted", "highly_restricted", "private"}:
        filters.extend(["redact_sensitive_data", "require_recipient_approval"])
    for target in targets:
        member = members_by_id.get(target)
        trust = TRUST_ORDER.get(member.get("trust_level", "public"), 1) if member else required_trust
        if trust >= required_trust and sensitivity not in {"highly_restricted", "private"}:
            authorized.append(target)
        else:
            denied.append(target)
    return {
        "share_id": "share_" + stable_hash({"source": payload["source_organization_id"], "title": payload["title"], "targets": targets})[:16],
        "status": "shared" if authorized and not denied else ("partially_shared" if authorized else "blocked"),
        "authorized_targets": authorized,
        "denied_targets": denied,
        "policy_filters": filters,
        "events": ["KNOWLEDGE_SHARED"] if authorized else ["FEDERATION_POLICY_UPDATED"],
    }


def negotiate_resources(payload: dict[str, Any]) -> dict[str, Any]:
    required = {normalize_key(key): float(value) for key, value in (payload.get("required_resources") or {}).items()}
    organizations = [organization_payload(item) for item in payload.get("candidate_organizations") or []]
    regulatory = normalize_list(payload.get("regulatory_constraints") or [])
    candidates = []
    for org in organizations:
        capacity = org.get("resource_capacity") or {}
        allocation = {key: min(required_value, float(capacity.get(key, 0))) for key, required_value in required.items()}
        coverage = sum(allocation.values()) / max(1.0, sum(required.values()))
        trust = TRUST_ORDER.get(org.get("trust_level", "public"), 1) / 5
        certification_match = 1.0 if not regulatory or set(regulatory).intersection(set(org.get("certifications", []))) else 0.0
        score = round((coverage * 0.58) + (trust * 0.25) + (certification_match * 0.17), 4)
        candidates.append({"organization": org, "allocation": allocation, "coverage": coverage, "score": score})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = candidates[0] if candidates else None
    allocation = selected["allocation"] if selected else {}
    unresolved = {key: round(value - allocation.get(key, 0), 4) for key, value in required.items() if allocation.get(key, 0) < value}
    estimated = round(sum(allocation.get(key, 0) * RESOURCE_COST.get(key, 1.0) for key in allocation), 4)
    max_cost = payload.get("max_cost")
    required_approvals = []
    if max_cost is not None and estimated > float(max_cost):
        required_approvals.append("budget_owner")
    if regulatory and selected and not set(regulatory).intersection(set(selected["organization"].get("certifications", []))):
        required_approvals.append("compliance_reviewer")
    status = "allocated" if selected and not unresolved and not required_approvals else ("needs_approval" if selected else "unavailable")
    return {
        "agreement_id": "resource_" + stable_hash({"required": required, "selected": selected})[:16],
        "status": status,
        "selected_provider": selected["organization"] if selected else None,
        "allocation": allocation,
        "estimated_cost": estimated,
        "sla": payload.get("sla") or {"availability": "best_effort", "reporting": "daily"},
        "unresolved_resources": unresolved,
        "required_approvals": required_approvals,
        "events": ["RESOURCE_ALLOCATED"] if status == "allocated" else ["DISPUTE_OPENED" if unresolved else "FEDERATION_POLICY_UPDATED"],
    }


def federation_status(memories: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item.get("content_type") for item in memories)
    member_ids = set()
    open_disputes = 0
    for item in memories:
        content = item.get("content") or {}
        if item.get("content_type") == "federation":
            for member in content.get("members", []):
                member_ids.add(member.get("organization_id"))
        if "DISPUTE_OPENED" in content.get("events", []):
            open_disputes += 1
    health = {
        "capability_discovery": "ready" if member_ids else "empty_registry",
        "delegation_protocol": "ready" if counts.get("federation_delegation", 0) else "idle",
        "knowledge_exchange": "active" if counts.get("federation_knowledge_share", 0) else "idle",
        "resource_federation": "active" if counts.get("federation_resource_agreement", 0) else "idle",
        "auditability": True,
    }
    status = "needs_attention" if open_disputes else ("active" if counts.get("federation", 0) else "not_configured")
    return {
        "status": status,
        "federation_count": counts.get("federation", 0),
        "member_count": len(member_ids),
        "delegation_count": counts.get("federation_delegation", 0),
        "open_disputes": open_disputes,
        "shared_knowledge_count": counts.get("federation_knowledge_share", 0),
        "resource_agreements": counts.get("federation_resource_agreement", 0),
        "health": health,
        "refreshed_at": datetime.now(timezone.utc),
    }
