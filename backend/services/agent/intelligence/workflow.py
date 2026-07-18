from __future__ import annotations

from typing import Any


WORKFLOW_PHASES: list[dict[str, Any]] = [
    {"id": 1, "key": "launch", "title": "Launch", "decision": "Can Arceus restore a safe working state?"},
    {"id": 2, "key": "home", "title": "Home", "decision": "What should the founder continue or start?"},
    {"id": 3, "key": "idea_discovery", "title": "Idea Discovery", "decision": "Are requirements clear enough to plan?"},
    {"id": 4, "key": "product_intelligence", "title": "Product Intelligence", "decision": "Which product assumptions should be challenged?"},
    {"id": 5, "key": "architecture_intelligence", "title": "Architecture Intelligence", "decision": "Which architecture path should be selected?"},
    {"id": 6, "key": "master_blueprint", "title": "Master Blueprint", "decision": "Is the implementation blueprint complete?"},
    {"id": 7, "key": "task_intelligence", "title": "Task Intelligence", "decision": "Can the work be turned into executable tasks?"},
    {"id": 8, "key": "ai_workforce", "title": "AI Workforce Assembly", "decision": "Which specialists are needed?"},
    {"id": 9, "key": "model_intelligence", "title": "Model Intelligence", "decision": "Which model is best for each task?"},
    {"id": 10, "key": "context_building", "title": "Context Building", "decision": "Does each worker have only the right context?"},
    {"id": 11, "key": "parallel_engineering", "title": "Parallel Engineering", "decision": "Can work proceed safely in isolated branches?"},
    {"id": 12, "key": "continuous_intelligence", "title": "Continuous Intelligence", "decision": "Is any task blocked, stale, risky, or wasteful?"},
    {"id": 13, "key": "internal_reviews", "title": "Internal Reviews", "decision": "Do reviewers agree the work is correct and safe?"},
    {"id": 14, "key": "integration", "title": "Integration", "decision": "Can changes be integrated and verified together?"},
    {"id": 15, "key": "founder_approval", "title": "Founder Approval", "decision": "Should this be approved, revised, or rejected?"},
    {"id": 16, "key": "deployment", "title": "Deployment", "decision": "Which rollout path is safe?"},
    {"id": 17, "key": "learning", "title": "Learning", "decision": "What should Arceus learn for the next task?"},
]

STATUS_TO_PHASE_KEY = {
    "created": "idea_discovery",
    "analyzed": "product_intelligence",
    "planned": "architecture_intelligence",
    "plan_approved": "ai_workforce",
    "ready_for_execution": "context_building",
    "paused": "continuous_intelligence",
    "cancelled": "learning",
    "completed": "learning",
    "failed": "continuous_intelligence",
}


def workflow_snapshot(current_key: str | None = None) -> dict[str, Any]:
    current = current_key or "launch"
    current_index = next((index for index, phase in enumerate(WORKFLOW_PHASES) if phase["key"] == current), 0)
    phases = []
    for index, phase in enumerate(WORKFLOW_PHASES):
        if index < current_index:
            state = "completed"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        phases.append({**phase, "state": state})
    return {
        "current_phase": phases[current_index],
        "next_phase": phases[current_index + 1] if current_index + 1 < len(phases) else None,
        "phases": phases,
        "loop": [
            "Observe",
            "Understand",
            "Research",
            "Reason",
            "Challenge Assumptions",
            "Generate Alternatives",
            "Choose Best Strategy",
            "Assign Best Models",
            "Create Specialist Agents",
            "Execute",
            "Verify",
            "Review",
            "Integrate",
            "Test",
            "Deploy",
            "Monitor",
            "Learn",
        ],
    }


def phase_for_task_status(status: str | None) -> str:
    return STATUS_TO_PHASE_KEY.get(status or "created", "idea_discovery")

