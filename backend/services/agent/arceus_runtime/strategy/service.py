from __future__ import annotations

from typing import Any


DIMENSION_METRICS = {
    "financial": {
        "revenue_growth": 1.0,
        "gross_margin": 1.0,
        "runway_health": 1.0,
        "budget_efficiency": 1.0,
    },
    "operational": {
        "availability": 1.0,
        "incident_free_rate": 1.0,
        "deployment_success_rate": 1.0,
        "cycle_reliability": 1.0,
    },
    "engineering": {
        "test_pass_rate": 1.0,
        "delivery_predictability": 1.0,
        "code_review_quality": 1.0,
        "technical_debt_control": 1.0,
    },
    "customer": {
        "activation_rate": 1.0,
        "retention_health": 1.0,
        "satisfaction": 1.0,
        "support_quality": 1.0,
    },
    "security": {
        "security_score": 1.0,
        "secrets_hygiene": 1.0,
        "vulnerability_control": 1.0,
        "compliance_readiness": 1.0,
    },
}

HIGH_IMPACT_DECISION_TYPES = {
    "funding",
    "pricing",
    "production_deployment",
    "security_policy",
    "data_residency",
    "compliance",
    "layoff",
    "hiring",
    "vendor_lock_in",
    "architecture_migration",
}


def clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _dimension_score(metrics: dict[str, float], keys: dict[str, float]) -> float:
    values = [clamp_ratio(metrics[key]) * weight for key, weight in keys.items() if key in metrics]
    total_weight = sum(weight for key, weight in keys.items() if key in metrics)
    if not values or total_weight <= 0:
        return 0.72
    return round(sum(values) / total_weight, 4)


def calculate_enterprise_health(metrics: dict[str, float], runtime_summary: dict[str, Any]) -> dict[str, Any]:
    dimensions = {name: _dimension_score(metrics, keys) for name, keys in DIMENSION_METRICS.items()}
    task_statuses = runtime_summary.get("task_statuses") or {}
    approval_statuses = runtime_summary.get("approval_statuses") or {}
    stale_events = int(runtime_summary.get("stale_processing_outbox", 0) or 0)
    failed_tasks = int(task_statuses.get("failed", 0) or 0)
    blocked_tasks = int(task_statuses.get("blocked", 0) or 0)
    pending_approvals = int(approval_statuses.get("pending", 0) or 0) + int(approval_statuses.get("requested", 0) or 0)
    penalties = min(0.28, failed_tasks * 0.03 + blocked_tasks * 0.02 + pending_approvals * 0.01 + stale_events * 0.04)
    score = round(max(0.0, (sum(dimensions.values()) / len(dimensions)) - penalties) * 100, 2)
    risks: list[dict[str, Any]] = []
    for name, value in dimensions.items():
        if value < 0.65:
            risks.append({"risk_key": f"{name}_health_low", "severity": "high", "evidence": {"score": value}})
        elif value < 0.78:
            risks.append({"risk_key": f"{name}_health_watch", "severity": "medium", "evidence": {"score": value}})
    if failed_tasks:
        risks.append({"risk_key": "failed_work_items", "severity": "high", "evidence": {"failed_tasks": failed_tasks}})
    if blocked_tasks:
        risks.append({"risk_key": "blocked_execution", "severity": "medium", "evidence": {"blocked_tasks": blocked_tasks}})
    if stale_events:
        risks.append({"risk_key": "stale_event_processing", "severity": "high", "evidence": {"stale_processing_outbox": stale_events}})
    status = "excellent" if score >= 90 else "healthy" if score >= 80 else "watch" if score >= 65 else "at_risk"
    recommendations = recommendations_for_health(dimensions, risks)
    return {
        "enterprise_health": score,
        "status": status,
        "health_dimensions": {key: round(value * 100, 2) for key, value in dimensions.items()},
        "risks": risks,
        "recommendations": recommendations,
    }


def recommendations_for_health(dimensions: dict[str, float], risks: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    for name, value in dimensions.items():
        if value < 0.78:
            recommendations.append(f"Open an executive review on {name} health with evidence-backed corrective actions.")
    if any(item["risk_key"] == "failed_work_items" for item in risks):
        recommendations.append("Block strategic completion until failed tasks have independent verification.")
    if any(item["risk_key"] == "stale_event_processing" for item in risks):
        recommendations.append("Run runtime recovery and validate event replay before new high-impact work.")
    return recommendations or ["Continue current execution cadence and watch leading indicators."]


def build_key_results(*, title: str, desired_outcomes: list[str], kpis: dict[str, float], horizon: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, target in sorted(kpis.items()):
        rows.append(
            {
                "key": key,
                "title": f"Reach {key.replace('_', ' ')} target for {title}",
                "target": float(target),
                "current": 0.0,
                "unit": "ratio" if 0 <= float(target) <= 1 else "value",
                "horizon": horizon,
                "verification": "metric_observation_required",
            }
        )
    for index, outcome in enumerate(desired_outcomes[:6], start=1):
        rows.append(
            {
                "key": f"outcome_{index}",
                "title": outcome,
                "target": 1.0,
                "current": 0.0,
                "unit": "delivered_outcome",
                "horizon": horizon,
                "verification": "human_review_and_evidence_required",
            }
        )
    if not rows:
        rows.append(
            {
                "key": "verified_business_outcome",
                "title": f"Define and verify measurable outcome for {title}",
                "target": 1.0,
                "current": 0.0,
                "unit": "approved_metric",
                "horizon": horizon,
                "verification": "executive_metric_required",
            }
        )
    return rows


def objective_governance(priority: int, domain: str, evidence_ids: list[Any]) -> list[str]:
    approvals = ["objective_owner"]
    if priority >= 4:
        approvals.append("executive_sponsor")
    if domain.lower() in {"security", "finance", "healthcare", "legal", "compliance"}:
        approvals.append("domain_risk_reviewer")
    if not evidence_ids:
        approvals.append("evidence_required_before_execution")
    return approvals


def build_portfolio_summary(runtime_summary: dict[str, Any]) -> dict[str, Any]:
    mission_statuses = runtime_summary.get("mission_statuses") or {}
    task_statuses = runtime_summary.get("task_statuses") or {}
    active = int(mission_statuses.get("running", 0) or 0) + int(mission_statuses.get("approved", 0) or 0)
    blocked = int(task_statuses.get("blocked", 0) or 0) + int(task_statuses.get("failed", 0) or 0)
    return {
        "active_initiatives": active,
        "blocked_work": blocked,
        "ready_tasks": int(task_statuses.get("ready", 0) or 0),
        "running_tasks": int(task_statuses.get("running", 0) or 0),
        "portfolio_posture": "needs_attention" if blocked else "stable",
    }


def score_portfolio_items(items: list[dict[str, Any]], runtime_summary: dict[str, Any]) -> dict[str, Any]:
    priority_queue = []
    for item in items:
        priority = int(item.get("priority") or 3)
        confidence = float(item.get("confidence") or 0.65)
        has_evidence = bool(item.get("evidence_ids"))
        blocked = item.get("status") in {"blocked", "failed", "at_risk"}
        score = priority * 20 + confidence * 30 + (10 if has_evidence else -10) - (25 if blocked else 0)
        priority_queue.append(
            {
                "id": str(item.get("id")),
                "title": item.get("title"),
                "status": item.get("status", "proposed"),
                "priority_score": round(score, 2),
                "reason": "prioritized_by_business_value_evidence_and_execution_risk",
            }
        )
    priority_queue.sort(key=lambda row: (-row["priority_score"], row["title"] or ""))
    task_statuses = runtime_summary.get("task_statuses") or {}
    dependencies = []
    if int(task_statuses.get("blocked", 0) or 0):
        dependencies.append(
            {
                "dependency": "blocked_tasks",
                "impact": "dependent strategic milestones cannot complete until blockers clear",
                "severity": "medium",
            }
        )
    allocation = {
        "planning": int(task_statuses.get("pending", 0) or 0),
        "execution": int(task_statuses.get("ready", 0) or 0) + int(task_statuses.get("running", 0) or 0),
        "review": int(task_statuses.get("reviewing", 0) or 0) + int(task_statuses.get("verifying", 0) or 0),
        "blocked": int(task_statuses.get("blocked", 0) or 0) + int(task_statuses.get("failed", 0) or 0),
    }
    risks = []
    if allocation["blocked"]:
        risks.append({"risk_key": "portfolio_blockers", "severity": "medium", "evidence": {"blocked": allocation["blocked"]}})
    if allocation["review"] > allocation["execution"] and allocation["review"] > 3:
        risks.append({"risk_key": "review_bottleneck", "severity": "medium", "evidence": allocation})
    return {
        "priority_queue": priority_queue,
        "dependencies": dependencies,
        "resource_allocation": allocation,
        "risks": risks,
    }


def simulate_strategy(payload: dict[str, Any]) -> dict[str, Any]:
    assumptions = {key: clamp_ratio(value) for key, value in (payload.get("assumptions") or {}).items()}
    horizon_months = int(payload.get("horizon_months") or 3)
    investment_delta = float(payload.get("investment_delta") or 0.0)
    evidence_bonus = min(0.18, len(payload.get("evidence_ids") or []) * 0.04)
    assumption_strength = sum(assumptions.values()) / len(assumptions) if assumptions else 0.55
    confidence = round(min(0.94, max(0.35, 0.45 + assumption_strength * 0.28 + evidence_bonus)), 3)
    expected_impacts = {
        "delivery_speed": round(min(1.0, 0.45 + assumptions.get("team_capacity", 0.5) * 0.35 + investment_delta / 100_000), 3),
        "business_value": round(min(1.0, 0.4 + assumptions.get("market_demand", 0.55) * 0.42), 3),
        "risk_reduction": round(min(1.0, 0.35 + assumptions.get("verification_depth", 0.5) * 0.4), 3),
        "cost_pressure": round(min(1.0, 0.25 + max(0.0, investment_delta) / 50_000 + horizon_months / 120), 3),
    }
    risks: list[dict[str, Any]] = []
    if confidence < 0.6:
        risks.append({"risk_key": "low_confidence_forecast", "severity": "medium", "assumption": "insufficient evidence"})
    if expected_impacts["cost_pressure"] > 0.7:
        risks.append({"risk_key": "cost_pressure_high", "severity": "medium", "assumption": "investment_delta"})
    if assumptions.get("security_readiness", 0.7) < 0.55:
        risks.append({"risk_key": "security_readiness_low", "severity": "high", "assumption": "security_readiness"})
    recommendation = "proceed_with_governed_execution" if confidence >= 0.68 and not any(r["severity"] == "high" for r in risks) else "run_more_discovery_before_commitment"
    return {
        "scenario_id": f"sim_{abs(hash((payload.get('scenario_name'), tuple(sorted(assumptions.items()))))) % 10_000_000}",
        "advisory": "Strategy simulations support decisions; they do not replace accountable human approval.",
        "confidence": confidence,
        "expected_impacts": expected_impacts,
        "uncertainty": {
            "level": "low" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "high",
            "drivers": ["assumption_quality", "evidence_depth", "time_horizon"],
        },
        "risks": risks,
        "recommendation": recommendation,
        "assumptions": assumptions,
    }


def evaluate_executive_decision(*, decision_type: str, expected_impact: str, evidence_ids: list[Any], reversible: bool) -> dict[str, Any]:
    normalized_type = decision_type.strip().lower()
    approvals = ["accountable_executive"]
    if expected_impact in {"high", "critical"}:
        approvals.extend(["human_executive_review", "risk_owner"])
    if normalized_type in HIGH_IMPACT_DECISION_TYPES:
        approvals.append("domain_authority")
    if not reversible:
        approvals.append("rollback_or_exit_plan_required")
    if not evidence_ids:
        approvals.append("supporting_evidence_required")
    if expected_impact == "critical":
        approvals.append("board_or_owner_approval")
    if "supporting_evidence_required" in approvals or expected_impact in {"high", "critical"} or not reversible:
        status = "review_required"
        governance_decision = "human_governance_required"
    else:
        status = "recorded"
        governance_decision = "recorded_as_reversible_low_risk_decision"
    return {
        "status": status,
        "governance_decision": governance_decision,
        "required_approvals": sorted(set(approvals)),
    }
