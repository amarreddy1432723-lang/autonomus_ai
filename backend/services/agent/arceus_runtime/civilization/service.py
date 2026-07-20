from __future__ import annotations

import re
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from ..compiler.utils import stable_hash


CIVILIZATION_CONSTITUTION = {
    "version": "1.0",
    "immutable_principles": [
        "Human authority remains final for governance, values, and strategic risk.",
        "Evolution must be evidence-based and reversible where feasible.",
        "Agents may think, tools may act, policies control, evidence proves, humans govern.",
        "Knowledge must preserve provenance, confidence, freshness, and uncertainty.",
    ],
    "governance_boundaries": [
        "No production deployment without required authority.",
        "No constitutional change without explicit governance approval.",
        "No sensitive knowledge sharing across boundaries without policy approval.",
        "No organization may approve its own critical unsafe action alone.",
    ],
    "human_authority": [
        "define_vision",
        "approve_governance",
        "accept_strategic_risk",
        "resolve_exceptional_conflicts",
        "determine_organizational_values",
    ],
    "approval_rules": [
        "capability_promotion_requires_evidence",
        "strategic_expansion_requires_human_approval",
        "constitution_update_requires_governance_review",
        "destructive_or_external_actions_require_explicit_approval",
    ],
    "evolution_constraints": [
        "simulate_major_changes_before_execution",
        "verify_before_promotion",
        "preserve_organization_lineage",
        "retain_superseded_knowledge_without_treating_it_as_current",
    ],
    "ethical_obligations": [
        "protect_private_data",
        "avoid hidden automation",
        "surface uncertainty",
        "optimize long-term reliability and sustainability",
    ],
    "change_policy": "constitutional_changes_require_explicit_human_governance_and_auditable_evidence",
}

ECOSYSTEM_ACTORS = [
    "products",
    "services",
    "customers",
    "partners",
    "suppliers",
    "researchers",
    "developers",
    "operations",
    "executives",
    "ai_organizations",
]

KNOWLEDGE_LAYERS = ["facts", "patterns", "principles", "standards", "constitutional_knowledge"]

CAPABILITY_STAGES = ["research", "prototype", "pilot", "validated", "enterprise_standard", "platform_standard"]

DEFAULT_ORGANIZATIONS = [
    {
        "organization_id": "engineering",
        "name": "Engineering Organization",
        "mission": "Build, review, verify, and evolve software systems.",
        "capabilities": ["architecture", "implementation", "testing", "deployment"],
        "health": "healthy",
    },
    {
        "organization_id": "research",
        "name": "Research Organization",
        "mission": "Discover, validate, and promote new knowledge.",
        "capabilities": ["hypothesis_generation", "experimentation", "evidence_synthesis"],
        "health": "healthy",
    },
    {
        "organization_id": "governance",
        "name": "Governance Organization",
        "mission": "Enforce policy, safety, approval, and audit boundaries.",
        "capabilities": ["policy_evaluation", "approval_review", "compliance"],
        "health": "healthy",
    },
]


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_") or "general"


def constitution() -> dict[str, Any]:
    return dict(CIVILIZATION_CONSTITUTION)


def civilization_id_for(tenant_id: str | None = None) -> str:
    return "civilization_" + stable_hash({"tenant_id": tenant_id or "default", "type": "arceus_civilization"})[:16]


def detect_capability_gaps(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = [normalize_key(item) for item in payload.get("required_capabilities") or []]
    if not required:
        text = payload.get("goal", "").lower()
        if any(term in text for term in ("security", "compliance", "auth", "permission")):
            required.extend(["security_review", "authorization_review"])
        if any(term in text for term in ("research", "experiment", "hypothesis")):
            required.extend(["research_planning", "evidence_validation"])
        if any(term in text for term in ("deploy", "scale", "infrastructure", "production")):
            required.extend(["cloud_operations", "resilience_engineering"])
        if any(term in text for term in ("model", "agent", "ai", "routing")):
            required.extend(["model_orchestration", "evaluation_pipeline"])
        required.append("mission_governance")

    current = set()
    for org in payload.get("current_organizations") or []:
        current.update(normalize_key(cap) for cap in org.get("capabilities", []))
        current.update(normalize_key(spec) for spec in org.get("specializations", []))

    gaps = []
    for capability in sorted(set(required)):
        present = capability in current
        severity = "none" if present else ("high" if capability in {"security_review", "mission_governance", "resilience_engineering"} else "medium")
        if not present:
            gaps.append(
                {
                    "capability": capability,
                    "severity": severity,
                    "reason": "Required capability is not currently represented by an active organization.",
                    "recommended_organization": f"{capability.replace('_', ' ').title()} Organization",
                    "verification": "governance_review_and_mission_outcome_evidence",
                }
            )
    return gaps


def specialist_for_capability(capability: str) -> dict[str, Any]:
    label = capability.replace("_", " ").title()
    reviewer = "Reviewer" in label or "Review" in label
    return {
        "specialist_id": "specialist_" + stable_hash({"capability": capability})[:12],
        "role": f"{label} {'Specialist' if not reviewer else 'Reviewer'}",
        "capability": capability,
        "authority": "review_only" if reviewer else "propose_and_execute_within_approved_scope",
        "cannot": ["approve_own_critical_work", "access_production_secrets", "bypass_policy"],
        "reason": f"Created because the civilization needs {capability} for this objective.",
    }


def propose_organization(payload: dict[str, Any]) -> dict[str, Any]:
    gaps = detect_capability_gaps(payload)
    selected_capabilities = [gap["capability"] for gap in gaps] or [normalize_key(item) for item in payload.get("required_capabilities", [])]
    if not selected_capabilities:
        selected_capabilities = ["mission_governance"]
    specialists = [specialist_for_capability(capability) for capability in selected_capabilities[:8]]
    domain = normalize_key(payload.get("domain", "software_engineering"))
    organization_name = f"{domain.replace('_', ' ').title()} Evolution Organization"
    budget_limit = payload.get("budget_limit")
    estimated_cost = round(35 + len(specialists) * 18 + len(gaps) * 12, 2)
    status = "needs_governance_review"
    if budget_limit is not None and estimated_cost > float(budget_limit):
        status = "blocked_by_budget"
    proposal_id = "org_proposal_" + stable_hash({"goal": payload["goal"], "capabilities": selected_capabilities})[:16]
    return {
        "proposal_id": proposal_id,
        "status": status,
        "goal": payload["goal"],
        "capability_gaps": gaps,
        "proposed_organization": {
            "organization_id": "org_" + stable_hash({"name": organization_name, "goal": payload["goal"]})[:12],
            "name": organization_name,
            "mission": payload["goal"],
            "domain": domain,
            "capabilities": selected_capabilities,
            "lineage": ["civilization_root"],
            "policy_controlled": True,
        },
        "specialists": specialists,
        "governance_review": {
            "required": True,
            "approvers": ["human_executive", "governance_organization"],
            "checks": ["capability_overlap", "authority_boundaries", "budget", "data_access"],
            "ai_approval_counts_as_human": False,
        },
        "estimated_resources": {
            "estimated_cost": estimated_cost,
            "ai_specialists": len(specialists),
            "reviewers_required": max(1, len([item for item in specialists if item["authority"] == "review_only"])),
            "budget_limit": budget_limit,
        },
        "events": ["ORGANIZATION_PROPOSED"],
    }


def simulate_civilization(payload: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([payload.get("scenario", ""), payload.get("evolution_type", ""), " ".join(payload.get("constraints") or [])]).lower()
    constitutional_risk = any(term in text for term in ("bypass approval", "without human", "ignore policy", "disable audit", "production secrets"))
    affected_domains = payload.get("affected_domains") or ["software_engineering"]
    affected_orgs = payload.get("affected_organizations") or ["engineering", "governance"]
    evidence_count = len(payload.get("evidence_ids") or [])
    impact = min(0.96, 0.48 + len(affected_domains) * 0.05 + evidence_count * 0.06)
    risk = 0.78 if constitutional_risk else min(0.7, 0.25 + len(affected_orgs) * 0.04 - evidence_count * 0.03)
    status = "blocked" if constitutional_risk else ("needs_review" if risk >= 0.55 else "ready_for_governance_review")
    recommendation = "do_not_approve_until_constitutional_violation_is_removed" if constitutional_risk else "proceed_to_governance_review_with_evidence"
    return {
        "simulation_id": "civ_sim_" + stable_hash({"scenario": payload["scenario"], "domains": affected_domains})[:16],
        "status": status,
        "scenario": payload["scenario"],
        "predicted_impact": {
            "innovation_rate_delta": round(impact * 0.18, 3),
            "learning_velocity_delta": round(impact * 0.14, 3),
            "automation_coverage_delta": round(impact * 0.11, 3),
            "confidence": round(min(0.92, 0.5 + evidence_count * 0.08), 3),
        },
        "risk_analysis": {
            "overall_risk": round(risk, 3),
            "constitutional_risk": constitutional_risk,
            "resource_risk": "medium" if len(affected_orgs) > 4 else "low",
            "knowledge_leakage_risk": "medium" if "external" in text or "federat" in text else "low",
            "blocked_reasons": ["constitutional_violation"] if constitutional_risk else [],
        },
        "resource_plan": {
            "affected_organizations": affected_orgs,
            "affected_domains": affected_domains,
            "requires_simulation": True,
            "requires_incremental_rollout": risk >= 0.45,
        },
        "governance_review": {
            "required": True,
            "human_approval_required": True,
            "required_approvals": ["human_executive", "governance_organization"],
            "verification_required_before_promotion": True,
        },
        "recommendation": recommendation,
        "events": ["CIVILIZATION_SIMULATED"],
    }


def evolve_civilization(payload: dict[str, Any]) -> dict[str, Any]:
    simulation = simulate_civilization(
        {
            "scenario": payload["objective"],
            "evolution_type": payload.get("evolution_type", "capability"),
            "affected_organizations": payload.get("affected_organizations") or [],
            "constraints": payload.get("constraints") or [],
            "evidence_ids": payload.get("evidence_ids") or [],
        }
    )
    evidence_count = len(payload.get("evidence_ids") or [])
    has_human = bool(payload.get("human_approval_id"))
    blocked = list(simulation["risk_analysis"]["blocked_reasons"])
    required_approvals = ["governance_organization"]
    if payload.get("evolution_type") in {"strategic_expansion", "constitution_update", "organization_creation"}:
        required_approvals.append("human_executive")
    if "human_executive" in required_approvals and not has_human:
        blocked.append("human_approval_required")
    if evidence_count == 0:
        blocked.append("evidence_required")
    stage = "proposal" if blocked else ("verification" if evidence_count < 3 else "promotion")
    status = "blocked" if blocked else ("verification_required" if stage == "verification" else "ready_for_promotion")
    return {
        "evolution_id": "civ_evo_" + stable_hash({"objective": payload["objective"], "target": payload.get("target_state")})[:16],
        "status": status,
        "objective": payload["objective"],
        "evolution_type": normalize_key(payload.get("evolution_type", "capability")),
        "target_state": payload.get("target_state", "improved_operational_state"),
        "stage": stage,
        "required_approvals": sorted(set(required_approvals)),
        "verification_plan": [
            "capture_baseline_metrics",
            "execute_limited_pilot",
            "collect_evidence",
            "independent_review",
            "promote_only_after_successful_verification",
        ],
        "promotion_ready": status == "ready_for_promotion",
        "blocked_reasons": sorted(set(blocked)),
        "events": ["CAPABILITY_PROMOTED" if status == "ready_for_promotion" else "ECOSYSTEM_HEALTH_UPDATED"],
    }


def build_state(memories: list[dict[str, Any]], tenant_id: str | None = None) -> dict[str, Any]:
    organizations = {item["organization_id"]: item for item in DEFAULT_ORGANIZATIONS}
    latest_events: list[str] = []
    active_evolutions = 0
    blocked_evolutions = 0
    for item in memories:
        content = item.get("content") or {}
        if isinstance(content, dict):
            latest_events.extend(content.get("events", []))
            if content.get("proposed_organization"):
                org = content["proposed_organization"]
                organizations[org["organization_id"]] = {**org, "health": "pending_governance"}
            if content.get("evolution_id"):
                active_evolutions += 1
                if content.get("status") == "blocked":
                    blocked_evolutions += 1
    status = "needs_governance_attention" if blocked_evolutions else "evolving"
    return {
        "civilization_id": civilization_id_for(tenant_id),
        "vision": "A governed AI engineering civilization that learns, coordinates, verifies, and evolves with human authority.",
        "status": status,
        "organizations": list(organizations.values()),
        "ecosystem": ECOSYSTEM_ACTORS,
        "knowledge_layers": KNOWLEDGE_LAYERS,
        "evolution_state": {
            "active_evolutions": active_evolutions,
            "blocked_evolutions": blocked_evolutions,
            "pipeline": ["observation", "learning", "opportunity_detection", "proposal", "simulation", "approval", "implementation", "verification", "promotion"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "resilience": {
            "organization_redundancy": len(organizations) >= 3,
            "federation_ready": True,
            "recovery_model": "event_replay_and_memory_reconstruction",
            "sustainability_policy": "optimize_cost_knowledge_reuse_and_operational_health",
        },
        "latest_events": latest_events[:20],
    }


def metrics(memories: list[dict[str, Any]]) -> dict[str, Any]:
    events: list[str] = []
    content_types = []
    for item in memories:
        content_types.append(item.get("content_type", ""))
        content = item.get("content") or {}
        if isinstance(content, dict):
            events.extend(content.get("events", []))
    event_count = len(events)
    research_count = sum(1 for value in content_types if "research" in value)
    org_proposals = events.count("ORGANIZATION_PROPOSED")
    promotions = events.count("CAPABILITY_PROMOTED")
    simulations = events.count("CIVILIZATION_SIMULATED")
    governance_signals = sum(1 for event in events if "APPROVED" in event or "REVIEW" in event or "GOVERNANCE" in event)
    mission_success = 0.82 + min(0.12, promotions * 0.02)
    governance_health = 0.72 + min(0.2, governance_signals * 0.015)
    operational_resilience = 0.76 + min(0.18, simulations * 0.025)
    status = "healthy" if governance_health >= 0.76 and operational_resilience >= 0.78 else "needs_attention"
    return {
        "innovation_rate": round(min(1.0, (research_count + promotions) / 20), 3),
        "learning_velocity": round(min(1.0, event_count / 50), 3),
        "mission_success": round(min(0.98, mission_success), 3),
        "knowledge_growth": len(memories),
        "automation_coverage": round(min(0.95, 0.45 + promotions * 0.04 + org_proposals * 0.02), 3),
        "customer_value": round(min(0.94, 0.62 + promotions * 0.03), 3),
        "sustainability": round(min(0.95, 0.7 + max(0, len(memories) - 2) * 0.01), 3),
        "governance_health": round(min(0.98, governance_health), 3),
        "research_output": research_count,
        "operational_resilience": round(min(0.98, operational_resilience), 3),
        "status": status,
    }

