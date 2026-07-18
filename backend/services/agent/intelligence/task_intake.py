from __future__ import annotations

import re
from typing import Any


def normalize_objective(title: str, raw_request: str) -> str:
    text = " ".join((raw_request or title or "").split())
    if not text:
        return title or "Untitled engineering task"
    return text[:500]


def derive_requirements(raw_request: str) -> list[dict[str, Any]]:
    text = " ".join((raw_request or "").split())
    if not text:
        return []
    parts = [part.strip(" .") for part in re.split(r"(?:\n|;|\.\s+|\bthen\b|\band\b)", text) if part.strip(" .")]
    requirements = []
    for part in parts[:8]:
        lowered = part.lower()
        req_type = "functional"
        if any(word in lowered for word in ("test", "verify", "check", "acceptance")):
            req_type = "verification"
        elif any(word in lowered for word in ("safe", "secure", "auth", "permission", "quota")):
            req_type = "safety"
        elif any(word in lowered for word in ("ui", "ux", "button", "page", "screen")):
            req_type = "experience"
        requirements.append(
            {
                "requirement_type": req_type,
                "description": part[:1000],
                "source": "heuristic_intake",
                "confidence": 0.65,
                "requires_confirmation": len(part) < 10,
            }
        )
    return requirements


def default_plan_steps(task_type: str, risk_level: str) -> list[dict[str, Any]]:
    steps = [
        {
            "title": "Confirm scope and affected surface",
            "description": "Identify project, files, systems, and user-visible behavior affected by the request.",
            "assigned_role": "planner",
            "acceptance_criteria": ["Scope is tied to one project and explicit files/systems."],
        },
        {
            "title": "Inspect current implementation",
            "description": "Read relevant code, configuration, tests, logs, and product state before proposing changes.",
            "assigned_role": "code_reviewer",
            "acceptance_criteria": ["Evidence records list inspected files and findings."],
        },
        {
            "title": "Prepare implementation plan",
            "description": "Create a step-by-step plan with risks, commands, and expected proof.",
            "assigned_role": "architect",
            "acceptance_criteria": ["Plan has ordered steps, dependencies, and rollback path."],
        },
    ]
    if task_type in {"build", "fix", "design"}:
        steps.append(
            {
                "title": "Generate reviewable change",
                "description": "Produce the smallest safe change with a work receipt and rollback snapshot.",
                "assigned_role": "implementation_agent",
                "acceptance_criteria": ["Changes are scoped, evidenced, and undoable."],
            }
        )
    if risk_level in {"high", "critical"}:
        steps.append(
            {
                "title": "Founder approval gate",
                "description": "Wait for explicit approval before destructive, production, billing, auth, or deployment action.",
                "assigned_role": "founder_reviewer",
                "acceptance_criteria": ["Approval or rejection is recorded before execution."],
            }
        )
    steps.append(
        {
            "title": "Verify and report proof",
            "description": "Run focused checks, collect evidence, and summarize next actions.",
            "assigned_role": "qa_agent",
            "acceptance_criteria": ["Receipt includes checks, evidence, and remaining risks."],
        }
    )
    return steps
