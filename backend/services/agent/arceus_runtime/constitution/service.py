from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..verification.service import stable_hash


CONSTITUTION_KEY = "arceus.engineering.constitution"
CONSTITUTION_VERSION = 1
CONSTITUTION_HIERARCHY = [
    "human_instructions",
    "enterprise_policies",
    "mission_requirements",
    "arceus_constitution",
    "specialist_principles",
    "task_objectives",
    "execution",
]


@dataclass(frozen=True)
class ConstitutionalRule:
    rule_id: str
    name: str
    description: str
    category: str
    priority: int
    applies_to: tuple[str, ...]
    enforcement_level: str
    version: int = CONSTITUTION_VERSION


RULES: tuple[ConstitutionalRule, ...] = (
    ConstitutionalRule("intent_first", "User Intent First", "Optimize for the actual engineering objective, not superficial task completion.", "quality", 100, ("decision", "task", "plan"), "required"),
    ConstitutionalRule("evidence_before_confidence", "Evidence Before Confidence", "Operational claims require evidence before high confidence or completion.", "transparency", 95, ("decision", "completion", "review"), "mandatory"),
    ConstitutionalRule("safety_before_speed", "Safety Before Speed", "Unsafe work cannot be accelerated or hidden behind productivity claims.", "safety", 100, ("tool", "deployment", "security"), "absolute"),
    ConstitutionalRule("verification_before_completion", "Verification Before Completion", "No task or mission is complete until independently verified.", "quality", 90, ("completion", "task"), "mandatory"),
    ConstitutionalRule("transparent_reasoning", "Transparency", "Recommendations must include why, evidence, risks, alternatives, and required approvals.", "transparency", 80, ("decision", "proposal"), "required"),
    ConstitutionalRule("least_necessary_action", "Least Necessary Action", "Make the minimum repository change needed to satisfy the mission.", "maintainability", 75, ("implementation", "tool"), "preferred"),
    ConstitutionalRule("human_authority", "Human Authority", "Production, finance, legal, governance, and irreversible actions require human authority.", "human_governance", 100, ("approval", "deployment", "finance"), "absolute"),
    ConstitutionalRule("governed_learning", "Continuous Learning Under Governance", "Learning can be promoted only after evidence, verification, and approval.", "learning", 90, ("learning", "evolution"), "mandatory"),
)


STANDARDS: tuple[dict[str, Any], ...] = (
    {"standard_key": "authentication.v3", "name": "Authentication Standard", "version": 3, "category": "security", "summary": "Authentication changes require session-bound identity, negative authorization tests, secret references, and audit evidence.", "required_evidence": ["security_review", "authorization_test", "audit_event"]},
    {"standard_key": "logging.v2", "name": "Logging Standard", "version": 2, "category": "observability", "summary": "Structured logs must include service, correlation ID, action, status, duration, and redaction guarantees.", "required_evidence": ["log_schema_review", "redaction_check"]},
    {"standard_key": "api.v5", "name": "API Standard", "version": 5, "category": "architecture", "summary": "API changes require typed contracts, error taxonomy, idempotency for mutations, and backward compatibility notes.", "required_evidence": ["contract_review", "compatibility_check"]},
    {"standard_key": "testing.v4", "name": "Testing Standard", "version": 4, "category": "quality", "summary": "Material changes require deterministic tests, verification evidence, and failed-test blockers before completion.", "required_evidence": ["test_run", "quality_gate"]},
    {"standard_key": "accessibility.v3", "name": "Accessibility Standard", "version": 3, "category": "frontend", "summary": "User-facing UI must support keyboard navigation, visible focus, sufficient contrast, and reduced-motion friendliness.", "required_evidence": ["accessibility_review"]},
)


def list_rules() -> list[ConstitutionalRule]:
    return sorted(RULES, key=lambda rule: (-rule.priority, rule.rule_id))


def list_standards() -> list[dict[str, Any]]:
    return list(STANDARDS)


def _rule_payload(rule: ConstitutionalRule, reason: str) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "enforcement_level": rule.enforcement_level,
        "reason": reason,
    }


def _find_rule(rule_id: str) -> ConstitutionalRule:
    for rule in RULES:
        if rule.rule_id == rule_id:
            return rule
    raise KeyError(rule_id)


def evaluate_constitution(
    *,
    action_type: str,
    objective: str,
    evidence_ids: list[Any],
    constraints: list[str],
    alternatives: list[str],
    selected_alternative: str | None,
    risks: list[str],
    confidence: float,
    requires_human_authority: bool = False,
    irreversible: bool = False,
    learning_change: bool = False,
    repository_change_count: int = 0,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    satisfied: list[str] = []

    if not objective.strip():
        blockers.append(_rule_payload(_find_rule("intent_first"), "Objective is empty."))
    else:
        satisfied.append("intent_first")

    if confidence >= 0.75 and not evidence_ids:
        blockers.append(_rule_payload(_find_rule("evidence_before_confidence"), "High confidence requires supporting evidence."))
    elif evidence_ids:
        satisfied.append("evidence_before_confidence")

    unsafe = any("unsafe" in item.lower() or "bypass" in item.lower() for item in risks + constraints)
    if unsafe:
        blockers.append(_rule_payload(_find_rule("safety_before_speed"), "Unsafe or policy-bypassing constraint detected."))
    else:
        satisfied.append("safety_before_speed")

    if action_type in {"completion", "mission_complete", "task_complete"} and not evidence_ids:
        blockers.append(_rule_payload(_find_rule("verification_before_completion"), "Completion requires independent verification evidence."))
    elif action_type in {"completion", "mission_complete", "task_complete"}:
        satisfied.append("verification_before_completion")

    if action_type in {"decision", "proposal", "architecture"} and (not alternatives or not selected_alternative):
        warnings.append(_rule_payload(_find_rule("transparent_reasoning"), "Decision should include alternatives and a selected option."))
    else:
        satisfied.append("transparent_reasoning")

    if repository_change_count > 20:
        warnings.append(_rule_payload(_find_rule("least_necessary_action"), "Large repository change should be split or justified."))
    else:
        satisfied.append("least_necessary_action")

    if requires_human_authority or irreversible:
        blockers.append(_rule_payload(_find_rule("human_authority"), "Human authority is required for irreversible or governance-sensitive action."))
    else:
        satisfied.append("human_authority")

    if learning_change and not evidence_ids:
        blockers.append(_rule_payload(_find_rule("governed_learning"), "Learning changes require evidence before proposal."))
    elif learning_change:
        warnings.append(_rule_payload(_find_rule("governed_learning"), "Learning change must be reviewed before promotion."))
    else:
        satisfied.append("governed_learning")

    decision = "deny" if any(item["enforcement_level"] == "absolute" for item in blockers) else "needs_revision" if blockers else "pass"
    reasoning_summary = {
        "objective": objective,
        "evidence_ids": [str(item) for item in evidence_ids],
        "constraints": constraints,
        "alternatives": alternatives,
        "selected_alternative": selected_alternative,
        "risks": risks,
        "confidence": confidence,
        "constitutional_checks": satisfied + [item["rule_id"] for item in blockers] + [item["rule_id"] for item in warnings],
        "summary_hash": stable_hash(
            {
                "objective": objective,
                "evidence_ids": [str(item) for item in evidence_ids],
                "constraints": constraints,
                "alternatives": alternatives,
                "selected_alternative": selected_alternative,
                "risks": risks,
                "confidence": confidence,
                "action_type": action_type,
            }
        ),
    }
    return {
        "decision": decision,
        "blockers": blockers,
        "warnings": warnings,
        "satisfied_rules": sorted(set(satisfied)),
        "reasoning_summary": reasoning_summary,
        "checked_at": datetime.now(timezone.utc),
    }


def evaluate_fitness(summary: dict[str, Any]) -> dict[str, Any]:
    task_statuses = summary.get("task_statuses") or {}
    approval_statuses = summary.get("approval_statuses") or {}
    outbox_statuses = summary.get("outbox_statuses") or {}
    bottlenecks: list[str] = []
    recommendations: list[str] = []
    score = 100.0
    if int(task_statuses.get("failed", 0)) > 0:
        score -= 20
        bottlenecks.append("failed_tasks")
        recommendations.append("run_deviation_analysis")
    if int(task_statuses.get("blocked", 0)) > 0:
        score -= 10
        bottlenecks.append("blocked_tasks")
        recommendations.append("resolve_dependency_or_policy_blockers")
    if int(approval_statuses.get("pending", 0)) > 0:
        score -= 5
        bottlenecks.append("pending_approvals")
        recommendations.append("improve_review_turnaround")
    if int(outbox_statuses.get("dead_letter", 0)) > 0:
        score -= 30
        bottlenecks.append("dead_letter_events")
        recommendations.append("repair_event_delivery")
    score = max(score, 0.0)
    status = "healthy" if score >= 90 else "degraded" if score >= 70 else "needs_attention"
    return {
        "fitness_score": score,
        "status": status,
        "metrics": {
            "task_statuses": task_statuses,
            "approval_statuses": approval_statuses,
            "outbox_statuses": outbox_statuses,
        },
        "bottlenecks": bottlenecks,
        "recommendations": recommendations,
    }


def evaluate_lesson_promotion(*, evidence_ids: list[Any], proposed_scope: str) -> dict[str, Any]:
    if not evidence_ids:
        return {
            "status": "provisional",
            "promotion_allowed": False,
            "reason": "Lessons require evidence before promotion.",
            "required_approvals": ["mission_lead", "human_reviewer"],
        }
    approvals = ["mission_lead", "human_reviewer"]
    if proposed_scope == "organization":
        approvals.append("organization_owner")
    return {
        "status": "review_required",
        "promotion_allowed": proposed_scope == "mission",
        "reason": "Evidence is present; promotion requires governed review.",
        "required_approvals": approvals,
    }


def evaluate_evolution_change(*, changes: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    forbidden = []
    for key in ("relax_security_rules", "remove_human_approvals", "change_constitution", "modify_enterprise_policy"):
        if changes.get(key):
            forbidden.append(key)
    if forbidden:
        return {
            "status": "blocked",
            "accepted": False,
            "reason": "Evolution cannot weaken constitution, enterprise policy, security, or human authority.",
            "simulation_required": True,
            "blocked_changes": forbidden,
            "required_approvals": ["security_reviewer", "organization_owner"],
        }
    return {
        "status": "simulated" if dry_run else "review_required",
        "accepted": bool(dry_run),
        "reason": "Evolution proposal can proceed only through simulation and approval.",
        "simulation_required": True,
        "blocked_changes": [],
        "required_approvals": ["mission_lead", "organization_owner"],
    }
