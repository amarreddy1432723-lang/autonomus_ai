from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .risk_engine import assess_risk
from ..model_registry import choose_model


@dataclass(frozen=True)
class WorkerSpec:
    role: str
    mission: str
    task_type: str
    model_key: str
    provider: str
    model: str
    reviewer_role: str | None
    reason: str
    estimated_cost: str
    estimated_time: str


ROLE_LIBRARY: dict[str, dict[str, Any]] = {
    "engineering_manager": {
        "mission": "Own decomposition, coordination, blockers, and founder decision points.",
        "task_type": "planning",
        "reviewer": "integration_judge",
    },
    "product_architect": {
        "mission": "Challenge product assumptions and turn the goal into requirements and acceptance criteria.",
        "task_type": "architecture",
        "reviewer": "engineering_manager",
    },
    "frontend_engineer": {
        "mission": "Implement user-facing UI, interaction states, accessibility, and visual polish.",
        "task_type": "design",
        "reviewer": "qa_engineer",
    },
    "backend_engineer": {
        "mission": "Implement APIs, persistence, service contracts, and backend safety.",
        "task_type": "code_generation",
        "reviewer": "security_engineer",
    },
    "ai_systems_engineer": {
        "mission": "Design task orchestration, model routing, context building, and worker contracts.",
        "task_type": "architecture",
        "reviewer": "engineering_manager",
    },
    "database_engineer": {
        "mission": "Design schema, migrations, rollback, indexing, and data integrity.",
        "task_type": "architecture",
        "reviewer": "security_engineer",
    },
    "desktop_engineer": {
        "mission": "Implement Electron local trust, terminal, filesystem, installer, and update paths.",
        "task_type": "code_generation",
        "reviewer": "qa_engineer",
    },
    "devops_engineer": {
        "mission": "Own Railway, Docker, CI, release gates, deployment, monitoring, and rollback.",
        "task_type": "planning",
        "reviewer": "release_manager",
    },
    "qa_engineer": {
        "mission": "Create evidence, checks, test strategy, acceptance coverage, and regression proof.",
        "task_type": "code_review",
        "reviewer": "integration_judge",
    },
    "security_engineer": {
        "mission": "Review auth, secrets, paths, permissions, destructive actions, and deployment risk.",
        "task_type": "code_review",
        "reviewer": "founder_reviewer",
    },
    "documentation_writer": {
        "mission": "Prepare concise docs, release notes, implementation notes, and user guidance.",
        "task_type": "chat",
        "reviewer": "release_manager",
    },
    "performance_engineer": {
        "mission": "Check latency, memory, bundle size, query cost, and operational efficiency.",
        "task_type": "debugging",
        "reviewer": "qa_engineer",
    },
    "release_manager": {
        "mission": "Package the release candidate, verify gates, summarize risk, and prepare rollback.",
        "task_type": "planning",
        "reviewer": "founder_reviewer",
    },
    "integration_judge": {
        "mission": "Resolve disagreements and decide whether the combined work is safe to present.",
        "task_type": "code_review",
        "reviewer": "founder_reviewer",
    },
}


def _roles_for_text(text: str, task_type: str, risk_level: str) -> list[str]:
    lowered = text.lower()
    roles = ["engineering_manager", "product_architect", "qa_engineer", "integration_judge"]
    if task_type in {"build", "fix"} or any(word in lowered for word in ("api", "backend", "endpoint", "fastapi")):
        roles.append("backend_engineer")
    if any(word in lowered for word in ("ui", "ux", "page", "button", "frontend", "react", "next")):
        roles.append("frontend_engineer")
    if any(word in lowered for word in ("model", "agent", "worker", "orchestration", "context", "intelligence")):
        roles.append("ai_systems_engineer")
    if any(word in lowered for word in ("database", "schema", "migration", "postgres", "redis")):
        roles.append("database_engineer")
    if any(word in lowered for word in ("desktop", "electron", "terminal", "installer", "folder")):
        roles.append("desktop_engineer")
    if any(word in lowered for word in ("deploy", "railway", "docker", "ci", "release", "sentry", "grafana")):
        roles.extend(["devops_engineer", "release_manager"])
    if any(word in lowered for word in ("auth", "security", "secret", "billing", "stripe", "permission")) or risk_level in {"high", "critical"}:
        roles.append("security_engineer")
    if any(word in lowered for word in ("performance", "latency", "slow", "memory", "optimize")):
        roles.append("performance_engineer")
    if any(word in lowered for word in ("docs", "documentation", "runbook", "readme", "guide")):
        roles.append("documentation_writer")
    return list(dict.fromkeys(roles))


def build_worker_specs(goal_text: str, preference: str = "balanced") -> list[WorkerSpec]:
    assessment = assess_risk(goal_text)
    roles = _roles_for_text(goal_text, assessment.task_type, assessment.risk_level)
    specs: list[WorkerSpec] = []
    for role in roles:
        profile = ROLE_LIBRARY[role]
        task_type = str(profile["task_type"])
        if preference == "private_local" and task_type in {"code_generation", "debugging", "code_review"}:
            choice = choose_model(task_type="local_code")
            model_key = choice.model_key
        elif preference == "fastest":
            choice = choose_model(task_type="chat")
            model_key = choice.model_key
        elif preference == "maximum_quality" and task_type in {"chat", "design"}:
            choice = choose_model(task_type="planning")
            model_key = choice.model_key
        else:
            choice = choose_model(task_type=task_type)
            model_key = choice.model_key

        specs.append(
            WorkerSpec(
                role=role,
                mission=str(profile["mission"]),
                task_type=task_type,
                model_key=model_key,
                provider=choice.provider,
                model=choice.model,
                reviewer_role=profile.get("reviewer"),
                reason=_reason_for(role, task_type, preference, assessment.risk_level),
                estimated_cost=_cost_band(preference, assessment.risk_level),
                estimated_time=_time_band(role, assessment.risk_level),
            )
        )
    return specs


def _reason_for(role: str, task_type: str, preference: str, risk_level: str) -> str:
    if preference == "private_local":
        return "Private/local preference is active; code-sensitive workers prefer local-capable routing where possible."
    if risk_level in {"high", "critical"}:
        return f"{role.replace('_', ' ').title()} needs stronger reasoning because this task is {risk_level} risk."
    return f"Selected for {task_type.replace('_', ' ')} based on task requirements and balanced routing."


def _cost_band(preference: str, risk_level: str) -> str:
    if preference == "lowest_cost":
        return "low"
    if preference == "maximum_quality" or risk_level in {"high", "critical"}:
        return "medium-high"
    if preference == "private_local":
        return "local/free where available"
    return "balanced"


def _time_band(role: str, risk_level: str) -> str:
    if role in {"engineering_manager", "integration_judge"}:
        return "1-3 min"
    if risk_level in {"high", "critical"}:
        return "6-12 min"
    return "3-7 min"
