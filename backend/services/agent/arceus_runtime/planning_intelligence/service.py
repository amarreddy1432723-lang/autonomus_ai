from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from ..compiler.intent_classifier import CAPABILITY_HINTS, INTENT_KEYWORDS
from ..compiler.utils import stable_hash
from ..planning.builder import build_organization_proposals
from .api_schemas import (
    GoalNode,
    PlanTask,
    PlanningBudget,
    PlanningDecisionResponse,
    PlanningIntelligenceRequest,
    ReplanRequest,
    ReplanResponse,
    StrategyOption,
)


RISK_TERMS = {
    "critical": ("production", "payment", "billing", "security", "auth", "delete", "migration", "secret", "deploy"),
    "high": ("database", "permission", "admin", "webhook", "oauth", "external api", "rollback"),
    "medium": ("refactor", "performance", "cache", "worker", "queue", "integration"),
}


def interpret_goal(payload: PlanningIntelligenceRequest) -> dict[str, Any]:
    objective = payload.normalized_objective or payload.objective.strip()
    intent = classify_objective(objective)
    risk_level = infer_risk_level(objective, payload.constraints, payload.repository_intelligence)
    capabilities = list(intent["required_capabilities"])
    if risk_level in {"high", "critical"} and "secure_code_review" not in capabilities:
        capabilities.append("secure_code_review")
    if not payload.success_criteria:
        success = [
            {
                "id": "sc_functional",
                "description": "Requested behavior is implemented within approved scope.",
                "verification_method": "diff_review",
            },
            {
                "id": "sc_quality",
                "description": "Relevant build, test, or smoke checks pass.",
                "verification_method": "build_verification",
            },
        ]
    else:
        success = [item.model_dump(mode="json") for item in payload.success_criteria]
    return {
        "objective": objective,
        "intent_type": intent["intent_type"],
        "requirements": intent["requirements"],
        "required_capabilities": capabilities,
        "risk_level": risk_level,
        "success_criteria": success,
        "unknowns": infer_unknowns(objective, payload.constraints),
    }


def classify_objective(objective: str) -> dict[str, Any]:
    text = objective.casefold()
    matches: list[tuple[str, int]] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score:
            matches.append((intent, score))
    matches.sort(key=lambda item: (-item[1], item[0]))
    primary = matches[0][0] if matches else "feature_development"
    secondary = [intent for intent, _score in matches[1:4]]
    capabilities = sorted({capability for intent in [primary, *secondary] for capability in CAPABILITY_HINTS.get(intent, ())})
    if not capabilities:
        capabilities = ["requirement_analysis", "acceptance_criteria_definition", "build_verification"]
    return {
        "intent_type": primary,
        "requirements": requirement_candidates(objective, primary),
        "required_capabilities": capabilities,
    }


def requirement_candidates(objective: str, intent_type: str) -> list[str]:
    fragments = [part.strip(" .") for part in re.split(r"\band\b|,|;", objective) if part.strip(" .")]
    if fragments:
        return [fragment[:220] for fragment in fragments[:6]]
    return [f"Complete {intent_type.replace('_', ' ')} safely."]


def infer_risk_level(objective: str, constraints: list[Any], repository_intelligence: dict[str, Any]) -> str:
    text = " ".join([objective.lower(), " ".join(getattr(item, "rule", str(item)).lower() for item in constraints), str(repository_intelligence).lower()])
    if any(term in text for term in RISK_TERMS["critical"]):
        return "critical"
    if any(term in text for term in RISK_TERMS["high"]):
        return "high"
    if any(term in text for term in RISK_TERMS["medium"]):
        return "medium"
    return "low"


def infer_unknowns(objective: str, constraints: list[Any]) -> list[dict[str, Any]]:
    text = objective.lower()
    unknowns: list[dict[str, Any]] = []
    if "?" in objective or any(term in text for term in ("maybe", "not sure", "unclear")):
        unknowns.append({"question": "What exact outcome should be optimized?", "risk_if_unanswered": "The plan may optimize for the wrong target."})
    if "deploy" in text and not any("environment" in item.rule.lower() for item in constraints):
        unknowns.append({"question": "Which environment is in scope?", "risk_if_unanswered": "Deployment authority and rollback plan may be incomplete."})
    if "database" in text and not any("schema" in item.rule.lower() for item in constraints):
        unknowns.append({"question": "Are schema changes allowed?", "risk_if_unanswered": "The plan may include data changes that require review."})
    return unknowns


def build_goal_tree(interpreted: dict[str, Any]) -> list[GoalNode]:
    root_id = "goal.root"
    nodes = [
        GoalNode(
            goal_id=root_id,
            title="Primary Goal",
            description=interpreted["objective"],
            parent_id=None,
            success_criteria_ids=[item["id"] for item in interpreted["success_criteria"]],
            uncertainty=min(0.55, len(interpreted["unknowns"]) * 0.15),
        )
    ]
    stage_titles = [
        ("goal.understand", "Understand scope and constraints", "Clarify boundaries, requirements, and repository context."),
        ("goal.design", "Select implementation strategy", "Choose the safest plan based on risk, cost, speed, and evidence."),
        ("goal.execute", "Execute approved work", "Perform scoped changes with tool and policy controls."),
        ("goal.verify", "Verify evidence", "Collect checks, review findings, and completion evidence."),
    ]
    for goal_id, title, description in stage_titles:
        nodes.append(GoalNode(goal_id=goal_id, title=title, description=description, parent_id=root_id, uncertainty=nodes[0].uncertainty))
    return nodes


def generate_strategy_options(payload: PlanningIntelligenceRequest, interpreted: dict[str, Any]) -> list[StrategyOption]:
    proposals = build_organization_proposals(
        interpreted["requirements"],
        interpreted["required_capabilities"],
        interpreted["risk_level"],
        performance_history=performance_history_from_memory(payload.relevant_memory),
    )
    options: list[StrategyOption] = []
    for proposal in proposals:
        tasks = [
            PlanTask(
                task_key=task.task_key,
                title=task.title,
                category=task.category,
                owner_role_key=task.owner_role_key,
                dependencies=list(task.dependencies),
                risk_level=task.risk_level,
                estimated_hours=task.estimated_hours,
                estimated_cost_usd=task.estimated_cost_usd,
                estimated_tokens=task.estimated_tokens,
                acceptance_criteria=list(task.acceptance_criteria),
                verification_methods=list(task.verification_methods),
            )
            for task in proposal.tasks
        ]
        violations = constraint_violations(payload, tasks)
        simulation = simulate_plan(payload, interpreted, tasks, proposal.proposal_key)
        risk_score = risk_score_for(interpreted["risk_level"], tasks, violations)
        cost_score = budget_score(payload.budget, tasks)
        speed_score = speed_score_for(payload.deadline, tasks)
        confidence = confidence_for(payload, interpreted, simulation, violations)
        decision_score = score_strategy(
            strategy=proposal.proposal_key,
            risk_score=risk_score,
            cost_score=cost_score,
            speed_score=speed_score,
            confidence=confidence,
            autonomy_level=payload.autonomy_level,
            violations=violations,
        )
        options.append(
            StrategyOption(
                strategy_key=proposal.proposal_key,
                name=proposal.name,
                rationale=proposal.rationale,
                tasks=tasks,
                risk_score=risk_score,
                cost_score=cost_score,
                speed_score=speed_score,
                confidence=confidence,
                decision_score=decision_score,
                required_approvals=approval_plan_for(payload, interpreted, tasks),
                constraint_violations=violations,
                simulation=simulation,
            )
        )
    return sorted(options, key=lambda item: item.decision_score, reverse=True)


def performance_history_from_memory(memories: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    history: dict[str, dict[str, float]] = {}
    for memory in memories:
        role = str(memory.get("role_key") or memory.get("subject") or "")
        if not role:
            continue
        history[role] = {
            "quality": float(memory.get("quality", 0.82)),
            "speed": float(memory.get("speed", 0.75)),
            "cost_efficiency": float(memory.get("cost_efficiency", 0.75)),
        }
    return history


def constraint_violations(payload: PlanningIntelligenceRequest, tasks: list[PlanTask]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    total_hours = sum(task.estimated_hours for task in tasks)
    total_cost = sum(task.estimated_cost_usd for task in tasks)
    total_tokens = sum(task.estimated_tokens for task in tasks)
    if payload.budget:
        if payload.budget.max_engineering_hours is not None and total_hours > payload.budget.max_engineering_hours:
            violations.append({"constraint_id": "budget.hours", "mandatory": True, "reason": "Estimated hours exceed budget."})
        if payload.budget.max_cost_usd is not None and total_cost > payload.budget.max_cost_usd:
            violations.append({"constraint_id": "budget.cost", "mandatory": True, "reason": "Estimated cost exceeds budget."})
        if payload.budget.max_tokens is not None and total_tokens > payload.budget.max_tokens:
            violations.append({"constraint_id": "budget.tokens", "mandatory": True, "reason": "Estimated token usage exceeds budget."})
    for constraint in payload.constraints:
        rule = constraint.rule.lower()
        if "do not modify database" in rule or "no schema" in rule:
            if any("database" in task.title.lower() or "migration" in " ".join(task.verification_methods).lower() for task in tasks):
                violations.append({"constraint_id": constraint.id, "mandatory": constraint.mandatory, "reason": "Plan may touch database/schema work."})
        if "production" in rule and "approval" in rule:
            if not any(task.category == "Approval" for task in tasks):
                violations.append({"constraint_id": constraint.id, "mandatory": constraint.mandatory, "reason": "Production-related plan requires approval gate."})
    return violations


def simulate_plan(payload: PlanningIntelligenceRequest, interpreted: dict[str, Any], tasks: list[PlanTask], strategy: str) -> dict[str, Any]:
    total_hours = sum(task.estimated_hours for task in tasks)
    parallel_groups = max(1, len({tuple(task.dependencies) for task in tasks}))
    failure_modes = []
    if interpreted["risk_level"] in {"high", "critical"}:
        failure_modes.append({"mode": "policy_or_security_block", "likelihood": 0.42, "mitigation": "Run independent security review before completion."})
    if any(task.risk_level in {"high", "critical"} for task in tasks):
        failure_modes.append({"mode": "verification_failure", "likelihood": 0.34, "mitigation": "Require failing checks to block dependent tasks."})
    if payload.budget and budget_score(payload.budget, tasks) < 0.5:
        failure_modes.append({"mode": "budget_exhaustion", "likelihood": 0.38, "mitigation": "Use lean plan or reduce scope before execution."})
    predicted_duration_hours = round(total_hours / min(3, parallel_groups), 2)
    completion_probability = round(max(0.1, min(0.98, 0.92 - len(failure_modes) * 0.09 - (0.04 if strategy == "lean" and interpreted["risk_level"] in {"high", "critical"} else 0))), 3)
    return {
        "predicted_duration_hours": predicted_duration_hours,
        "completion_probability": completion_probability,
        "parallel_groups": parallel_groups,
        "failure_modes": failure_modes,
        "stop_conditions": ["mandatory_constraint_violation", "failed_required_verification", "approval_rejected", "budget_exhausted"],
    }


def risk_score_for(risk_level: str, tasks: list[PlanTask], violations: list[dict[str, Any]]) -> float:
    base = {"low": 0.18, "medium": 0.38, "high": 0.62, "critical": 0.78}.get(risk_level, 0.4)
    review_discount = min(0.18, len([task for task in tasks if task.category == "Review"]) * 0.05)
    violation_penalty = min(0.2, len([item for item in violations if item.get("mandatory")]) * 0.08)
    return round(max(0.0, min(1.0, base - review_discount + violation_penalty)), 3)


def budget_score(budget: PlanningBudget | None, tasks: list[PlanTask]) -> float:
    if budget is None:
        return 0.82
    ratios = []
    total_hours = sum(task.estimated_hours for task in tasks)
    total_cost = sum(task.estimated_cost_usd for task in tasks)
    total_tokens = sum(task.estimated_tokens for task in tasks)
    if budget.max_engineering_hours:
        ratios.append(total_hours / budget.max_engineering_hours)
    if budget.max_cost_usd:
        ratios.append(total_cost / budget.max_cost_usd)
    if budget.max_tokens:
        ratios.append(total_tokens / budget.max_tokens)
    if not ratios:
        return 0.82
    worst = max(ratios)
    return round(max(0.0, min(1.0, 1.15 - worst)), 3)


def speed_score_for(deadline: datetime | None, tasks: list[PlanTask]) -> float:
    if deadline is None:
        return 0.78
    remaining_hours = max(0.1, (deadline - datetime.now(timezone.utc)).total_seconds() / 3600)
    estimated_hours = sum(task.estimated_hours for task in tasks)
    return round(max(0.0, min(1.0, remaining_hours / max(1.0, estimated_hours))), 3)


def confidence_for(payload: PlanningIntelligenceRequest, interpreted: dict[str, Any], simulation: dict[str, Any], violations: list[dict[str, Any]]) -> float:
    confidence = 0.72
    confidence += min(0.1, len(payload.success_criteria) * 0.025)
    confidence += min(0.08, len(payload.relevant_memory) * 0.01)
    confidence -= min(0.18, len(interpreted["unknowns"]) * 0.06)
    confidence -= min(0.2, len([item for item in violations if item.get("mandatory")]) * 0.08)
    confidence += (float(simulation.get("completion_probability", 0.7)) - 0.7) * 0.25
    return round(max(0.05, min(0.98, confidence)), 3)


def score_strategy(*, strategy: str, risk_score: float, cost_score: float, speed_score: float, confidence: float, autonomy_level: str, violations: list[dict[str, Any]]) -> float:
    score = (confidence * 0.36) + ((1 - risk_score) * 0.28) + (cost_score * 0.18) + (speed_score * 0.12)
    if strategy == "balanced":
        score += 0.04
    if strategy == "assurance" and autonomy_level in {"bounded_autonomous", "autonomous"}:
        score += 0.03
    if any(item.get("mandatory") for item in violations):
        score -= 0.25
    return round(max(0.0, min(1.0, score)), 3)


def approval_plan_for(payload: PlanningIntelligenceRequest, interpreted: dict[str, Any], tasks: list[PlanTask]) -> list[str]:
    approvals = set()
    if payload.autonomy_level in {"assistive", "supervised"}:
        approvals.add("human_plan_approval")
    if interpreted["risk_level"] in {"high", "critical"}:
        approvals.update({"security_review", "risk_owner_approval"})
    if any(constraint.type == "approval" for constraint in payload.constraints):
        approvals.add("constraint_owner_approval")
    if any("deploy" in task.title.lower() or "production" in task.title.lower() for task in tasks):
        approvals.add("production_operator_approval")
    return sorted(approvals)


def next_best_action(option: StrategyOption) -> dict[str, Any]:
    if option.constraint_violations:
        mandatory = [item for item in option.constraint_violations if item.get("mandatory")]
        if mandatory:
            return {"action": "revise_constraints_or_scope", "reason": mandatory[0]["reason"], "blocking": True}
    if option.required_approvals:
        return {"action": "request_approval", "approval": option.required_approvals[0], "blocking": True}
    first_task = next((task for task in option.tasks if not task.dependencies), option.tasks[0] if option.tasks else None)
    return {"action": "start_task", "task_key": first_task.task_key if first_task else None, "blocking": False}


def build_planning_decision(payload: PlanningIntelligenceRequest) -> PlanningDecisionResponse:
    interpreted = interpret_goal(payload)
    goal_tree = build_goal_tree(interpreted)
    alternatives = generate_strategy_options(payload, interpreted)
    recommended = alternatives[0]
    plan_id = "plan_" + stable_hash({"objective": payload.objective, "alternatives": [item.model_dump(mode="json") for item in alternatives]}).replace("sha256:", "")[:24]
    uncertainty = {
        "unknowns": interpreted["unknowns"],
        "level": round(sum(item.uncertainty for item in goal_tree) / max(1, len(goal_tree)), 3),
        "explicit": bool(interpreted["unknowns"]),
    }
    approval_plan = [{"approval_key": item, "required": True, "reason": "Required by risk/autonomy/constraint policy."} for item in recommended.required_approvals]
    return PlanningDecisionResponse(
        plan_id=plan_id,
        objective=payload.objective,
        interpreted_goal=interpreted["objective"],
        goal_tree=goal_tree,
        recommended_strategy_key=recommended.strategy_key,
        alternatives=alternatives,
        next_best_action=next_best_action(recommended),
        approval_plan=approval_plan,
        uncertainty=uncertainty,
        events=["GOAL_INTERPRETED", "ALTERNATIVES_GENERATED", "PLAN_SIMULATED", "STRATEGY_SELECTED"],
    )


def validate_planning_response(plan: PlanningDecisionResponse) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not plan.goal_tree:
        errors.append("Plan has no goal tree.")
    if not plan.alternatives:
        errors.append("Plan has no alternatives.")
    for option in plan.alternatives:
        if not option.tasks:
            errors.append(f"Strategy {option.strategy_key} has no tasks.")
        for task in option.tasks:
            if not task.acceptance_criteria:
                errors.append(f"Task {task.task_key} has no acceptance criteria.")
            if not task.verification_methods:
                errors.append(f"Task {task.task_key} has no verification method.")
    if plan.uncertainty.get("level", 0) > 0.4:
        warnings.append("Plan has high uncertainty and should run discovery before execution.")
    if plan.next_best_action.get("blocking"):
        warnings.append("Next best action is blocked by approval or constraints.")
    return not errors, errors, warnings


def replan_from_evidence(payload: ReplanRequest) -> ReplanResponse:
    reasons: list[str] = []
    adjustments: list[str] = []
    if payload.failed_task_keys:
        reasons.append("One or more tasks failed.")
        adjustments.append("Insert diagnosis and verification tasks before retrying failed work.")
    if payload.budget_change:
        reasons.append("Budget changed.")
        adjustments.append("Re-score alternatives with updated budget limits.")
    if payload.new_evidence.get("policy_blocked"):
        reasons.append("A policy gate blocked execution.")
        adjustments.append("Add approval or reduce scope to avoid blocked action.")
    if payload.user_feedback:
        reasons.append("User feedback changed plan assumptions.")
        adjustments.append("Regenerate goal tree and strategy scoring from feedback.")
    should = bool(reasons)
    return ReplanResponse(should_replan=should, reasons=reasons or ["No replanning trigger detected."], recommended_adjustments=adjustments, replacement_plan=None)
