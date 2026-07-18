from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ..compiler.utils import stable_hash


DEFAULT_SIGNALS = [
    {
        "signal_type": "customer",
        "source": "feedback",
        "theme": "sso",
        "summary": "Enterprise customers repeatedly ask for Azure AD SSO.",
        "count": 100,
        "severity": 5,
        "revenue_usd": 125_000,
        "customer_segment": "enterprise",
    },
    {
        "signal_type": "engineering",
        "source": "runtime",
        "theme": "preview_reliability",
        "summary": "Preview verification failures slow release confidence.",
        "count": 18,
        "severity": 4,
        "revenue_usd": 0,
        "customer_segment": "developers",
    },
    {
        "signal_type": "market",
        "source": "competitive_intelligence",
        "theme": "local_models",
        "summary": "Developer platforms are adding local/private model execution.",
        "count": 12,
        "severity": 3,
        "revenue_usd": 42_000,
        "customer_segment": "security_sensitive_teams",
    },
]


def _opportunity_id(theme: str, framework: str) -> str:
    return "opp_" + stable_hash({"theme": theme, "framework": framework}).replace("sha256:", "")[:18]


def _score_group(signals: list[dict[str, Any]], *, framework: str = "rice") -> dict[str, float]:
    total_count = sum(int(signal.get("count", 1)) for signal in signals)
    max_severity = max(float(signal.get("severity", 3)) for signal in signals)
    revenue = sum(float(signal.get("revenue_usd", 0)) for signal in signals)
    business_impact = min(100.0, revenue / 2_000 + max_severity * 12)
    customer_demand = min(100.0, total_count * 1.5 + max_severity * 8)
    strategic_alignment = 90.0 if any(signal.get("customer_segment") == "enterprise" for signal in signals) else 72.0
    engineering_effort = max(12.0, 62.0 - max_severity * 6)
    risk = min(100.0, 20.0 + max_severity * 9)
    revenue_potential = min(100.0, revenue / 1_500)
    urgency = min(100.0, total_count + max_severity * 10)

    if framework == "ice":
        priority = (business_impact + customer_demand + strategic_alignment) / 3
    elif framework == "wsjf":
        priority = (business_impact + urgency + revenue_potential) / max(engineering_effort / 10, 1)
    elif framework == "value_effort":
        priority = (business_impact + customer_demand + revenue_potential) - engineering_effort
    elif framework == "moscow":
        priority = 95.0 if max_severity >= 5 or total_count >= 50 else 65.0
    else:
        reach = min(100.0, total_count)
        impact = business_impact / 20
        confidence = strategic_alignment / 100
        effort = max(engineering_effort / 20, 1)
        priority = (reach * impact * confidence) / effort

    return {
        "priority_score": round(max(0.0, min(priority, 100.0)), 2),
        "business_impact": round(business_impact, 2),
        "customer_demand": round(customer_demand, 2),
        "strategic_alignment": round(strategic_alignment, 2),
        "engineering_effort": round(engineering_effort, 2),
        "risk": round(risk, 2),
        "revenue_potential": round(revenue_potential, 2),
        "urgency": round(urgency, 2),
    }


def discover_opportunities(signals: list[dict[str, Any]] | None = None, *, framework: str = "rice") -> list[dict[str, Any]]:
    signals = signals or DEFAULT_SIGNALS
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[str(signal.get("theme", "general")).strip().lower()].append(signal)

    opportunities = []
    for theme, rows in grouped.items():
        scores = _score_group(rows, framework=framework)
        title = theme.replace("_", " ").title()
        horizon = "now" if scores["priority_score"] >= 75 else "next" if scores["priority_score"] >= 50 else "later"
        opportunities.append(
            {
                "opportunity_id": _opportunity_id(theme, framework),
                "title": title,
                "theme": theme,
                "framework": framework,
                "horizon": horizon,
                "evidence": [f"{row.get('source')}:{row.get('count', 1)}" for row in rows],
                "recommended_action": "generate_prd" if scores["priority_score"] >= 60 else "collect_more_evidence",
                **scores,
            }
        )
    opportunities.sort(key=lambda item: (-item["priority_score"], item["title"]))
    return opportunities


def default_personas() -> list[dict[str, Any]]:
    return [
        {
            "persona_key": "startup_founder",
            "name": "Startup Founder",
            "goals": ["ship MVP quickly", "reduce hiring cost", "validate market demand"],
            "frustrations": ["unclear technical choices", "slow product iteration", "lack of trusted engineering review"],
            "workflows": ["idea discovery", "blueprint review", "mission approval", "release review"],
            "feature_usage": ["product blueprint", "mission control", "download desktop"],
            "satisfaction_signals": ["time to first useful plan", "confidence in roadmap", "successful PR creation"],
        },
        {
            "persona_key": "enterprise_admin",
            "name": "Enterprise Administrator",
            "goals": ["govern access", "control spend", "audit AI work"],
            "frustrations": ["shadow AI usage", "weak approval trails", "uncontrolled secrets"],
            "workflows": ["SSO setup", "policy review", "usage monitoring", "release governance"],
            "feature_usage": ["admin", "audit", "security policy", "billing"],
            "satisfaction_signals": ["audit completeness", "quota enforcement", "policy explainability"],
        },
        {
            "persona_key": "developer",
            "name": "Developer",
            "goals": ["understand code quickly", "apply safe changes", "verify builds"],
            "frustrations": ["context switching", "unreliable generated code", "manual patch review overload"],
            "workflows": ["open folder", "terminal", "work receipt", "undo changes", "PR"],
            "feature_usage": ["workspace", "terminal", "knowledge search", "diff review"],
            "satisfaction_signals": ["terminal latency", "rollback success", "test evidence"],
        },
    ]


def generate_requirement(payload: dict[str, Any]) -> dict[str, Any]:
    signals = payload.get("signals") or DEFAULT_SIGNALS[:1]
    framework = payload.get("framework", "rice")
    opportunity = discover_opportunities(signals, framework=framework)[0]
    title = payload["title"]
    objectives = payload.get("objectives") or [
        f"Solve the validated {opportunity['theme'].replace('_', ' ')} problem.",
        "Create measurable customer and business impact.",
        "Link implementation work to verifiable engineering evidence.",
    ]
    metrics = [
        "feature adoption",
        "customer satisfaction",
        "activation or retention impact",
        "verified release quality",
    ]
    stakeholders = payload.get("stakeholders") or ["Product Manager", "Engineering Lead", "Customer Success", "Business Reviewer"]
    dependencies = payload.get("dependencies") or ["approved architecture", "engineering capacity", "verification plan"]
    risks = payload.get("risks") or ["scope creep", "integration complexity", "unclear success measurement"]
    requirement_id = "prd_" + stable_hash({"title": title, "opportunity": opportunity["opportunity_id"]}).replace("sha256:", "")[:18]
    return {
        "requirement_id": requirement_id,
        "title": title,
        "business_problem": payload["business_problem"],
        "user_problem": payload["user_problem"],
        "objectives": objectives,
        "user_stories": [
            f"As a customer, I want {title.lower()} so that my workflow improves.",
            f"As an administrator, I want controls and auditability for {title.lower()}.",
            f"As an engineering reviewer, I want evidence that {title.lower()} is safe to release.",
        ],
        "success_metrics": metrics,
        "stakeholders": stakeholders,
        "dependencies": dependencies,
        "risks": risks,
        "acceptance_criteria": [
            "Customer problem and business objective are explicitly linked.",
            "Success metrics have measurable before/after values.",
            "Engineering mission includes verification evidence and rollback.",
            "Business-critical launch risks have assigned owners.",
        ],
        "priority": opportunity,
        "mission_seed": {
            "mission_type": "product_requirement_implementation",
            "objective": f"Implement PRD: {title}",
            "required_capabilities": ["requirement_analysis", "roadmap_planning", "system_architecture", "build_verification"],
            "approval_gates": ["product_scope", "architecture_review", "release_readiness"],
        },
        "generated_at": datetime.now(timezone.utc),
    }


def build_roadmap(opportunities: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    opportunities = opportunities or discover_opportunities()
    items = []
    for index, opportunity in enumerate(opportunities, start=1):
        release = "1.1" if opportunity["horizon"] == "now" else "1.2" if opportunity["horizon"] == "next" else "2.0"
        items.append(
            {
                "roadmap_item_id": "road_" + stable_hash(opportunity["opportunity_id"]).replace("sha256:", "")[:18],
                "title": opportunity["title"],
                "horizon": opportunity["horizon"],
                "priority_score": opportunity["priority_score"],
                "linked_opportunity_id": opportunity["opportunity_id"],
                "dependencies": ["product_requirement", "architecture_review"] if index == 1 else ["customer_validation"],
                "release_candidate": f"release-{release}",
                "engineering_mission": {
                    "objective": f"Deliver {opportunity['title']}",
                    "priority": index,
                    "source": "product_roadmap",
                },
            }
        )
    return items


def create_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    risky_rollout = float(payload.get("rollout", 0.1)) > 0.5
    return {
        "experiment_id": "exp_" + stable_hash(payload).replace("sha256:", "")[:18],
        "hypothesis": payload["hypothesis"],
        "variants": payload["variants"],
        "metrics": payload["metrics"],
        "success_threshold": payload["success_threshold"],
        "rollout": payload.get("rollout", 0.1),
        "duration_days": payload.get("duration_days", 14),
        "owner": payload["owner"],
        "status": "approval_required" if risky_rollout else "ready",
        "governance": {
            "requires_business_review": risky_rollout,
            "requires_privacy_review": any("personal" in metric.lower() or "user" in metric.lower() for metric in payload["metrics"]),
            "safe_rollout_limit": 0.5,
        },
        "created_at": datetime.now(timezone.utc),
    }


def planned_releases() -> list[dict[str, Any]]:
    return [
        {
            "release_id": "rel_1_1",
            "name": "Release 1.1",
            "status": "planning",
            "features": ["Azure AD SSO", "Preview reliability"],
            "verification_status": "pending",
            "business_readiness": "needs_prd_approval",
            "documentation_readiness": "draft_required",
            "support_readiness": "playbook_required",
            "rollback_strategy": "feature flags plus previous installer/channel rollback",
            "communication_plan": "enterprise beta announcement and admin migration guide",
        }
    ]


def product_metrics() -> dict[str, float]:
    mrr = 4200.0
    return {
        "mrr": mrr,
        "arr": mrr * 12,
        "churn": 0.035,
        "retention": 0.91,
        "activation": 0.68,
        "conversion": 0.12,
        "engagement": 0.74,
        "feature_adoption": 0.57,
        "customer_satisfaction": 4.4,
        "engineering_velocity": 0.82,
        "deployment_frequency": 2.0,
    }


def product_dashboard() -> dict[str, Any]:
    opportunities = discover_opportunities()
    metrics = product_metrics()
    recommendations = ["generate_prd_for_top_opportunity", "validate_enterprise_sso_scope", "prepare_release_1_1_readiness_review"]
    if metrics["churn"] > 0.03:
        recommendations.append("investigate_enterprise_churn_drivers")
    return {
        "generated_at": datetime.now(timezone.utc),
        "opportunities": opportunities,
        "roadmap": build_roadmap(opportunities),
        "personas": default_personas(),
        "releases": planned_releases(),
        "metrics": metrics,
        "product_health": "healthy" if metrics["retention"] >= 0.9 else "needs_attention",
        "recommendations": recommendations,
    }
