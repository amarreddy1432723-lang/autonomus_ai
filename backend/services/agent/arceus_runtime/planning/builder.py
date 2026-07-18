from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .contracts import OrganizationProposal, PlannedMember, PlannedTask
from .registry import SPECIALIST_REGISTRY


CAPABILITY_ROLE_HINTS = {
    "requirement": "product_analyst",
    "architecture": "solution_architect",
    "api": "backend_engineer",
    "backend": "backend_engineer",
    "fastapi": "backend_engineer",
    "python": "backend_engineer",
    "postgres": "backend_engineer",
    "database": "backend_engineer",
    "migration": "backend_engineer",
    "react": "frontend_engineer",
    "nextjs": "frontend_engineer",
    "frontend": "frontend_engineer",
    "ui": "frontend_engineer",
    "accessibility": "frontend_engineer",
    "test": "qa_reviewer",
    "verification": "qa_reviewer",
    "evidence": "qa_reviewer",
    "security": "security_reviewer",
    "auth": "security_reviewer",
    "secret": "security_reviewer",
    "dependency": "security_reviewer",
    "docker": "devops_reviewer",
    "cloud": "devops_reviewer",
    "observability": "devops_reviewer",
    "release": "devops_reviewer",
}


def choose_roles(
    required_capabilities: list[str],
    risk_level: str,
    *,
    strategy: str = "balanced",
    performance_history: dict[str, dict[str, float]] | None = None,
) -> tuple[list[PlannedMember], list[str]]:
    role_keys = {"mission_lead", "product_analyst", "solution_architect", "qa_reviewer", "human_approver"}
    capability_gaps: list[str] = []
    for capability in required_capabilities:
        matched = False
        for key, value in CAPABILITY_ROLE_HINTS.items():
            if key in capability:
                role_keys.add(value)
                matched = True
        if not matched:
            capability_gaps.append(capability)
    if strategy != "lean" and (
        risk_level in {"high", "critical"} or any("auth" in item or "security" in item for item in required_capabilities)
    ):
        role_keys.add("security_reviewer")
    if strategy == "assurance":
        role_keys.update({"security_reviewer", "devops_reviewer"})
    if any(item in required_capabilities for item in ("cloud_deployment", "docker_configuration", "observability", "release_management")):
        role_keys.add("devops_reviewer")

    ordered_roles = [
        "mission_lead",
        "product_analyst",
        "solution_architect",
        "backend_engineer",
        "frontend_engineer",
        "devops_reviewer",
        "qa_reviewer",
        "security_reviewer",
        "human_approver",
    ]
    members: list[PlannedMember] = []
    for role_key in ordered_roles:
        if role_key not in role_keys:
            continue
        registry_item = SPECIALIST_REGISTRY[role_key]
        can_implement = role_key.endswith("_engineer")
        can_review = role_key.endswith("_reviewer") or role_key == "solution_architect"
        can_approve = role_key == "human_approver"
        members.append(
            PlannedMember(
                role_key=role_key,
                specialist_key=role_key,
                display_name=registry_item["display_name"],
                specialist_type=registry_item["type"],
                assigned_capabilities=tuple(capability for capability in registry_item["capabilities"] if capability in required_capabilities)
                or tuple(registry_item["capabilities"][:1]),
                responsibility=_responsibility_for_role(role_key),
                authority=registry_item["authority"],
                can_implement=can_implement,
                can_review=can_review,
                can_approve=can_approve,
                score=_specialist_score(role_key, required_capabilities, performance_history or {}),
                score_reason=_score_reason(role_key, required_capabilities, performance_history or {}),
            )
        )
    return members, capability_gaps


def build_organization_proposals(
    requirements: list[str],
    required_capabilities: list[str],
    risk_level: str,
    *,
    performance_history: dict[str, dict[str, float]] | None = None,
) -> list[OrganizationProposal]:
    proposals: list[OrganizationProposal] = []
    for strategy, name, rationale in (
        ("lean", "Lean MVP Team", "Smallest team that can build the mission with required human approval."),
        ("balanced", "Balanced Engineering Team", "Recommended blend of implementation speed, review independence, and cost control."),
        ("assurance", "Assurance Review Team", "Extra review coverage for sensitive, high-risk, or production-facing missions."),
    ):
        members, gaps = choose_roles(required_capabilities, risk_level, strategy=strategy, performance_history=performance_history)
        tasks = plan_tasks(requirements, required_capabilities, risk_level, strategy=strategy)
        validation = validate_plan(members, tasks, requirements)
        metrics = plan_metrics(members, tasks, validation, gaps)
        metrics["strategy"] = strategy
        metrics["recommendation_score"] = _proposal_score(strategy, risk_level, metrics)
        proposals.append(
            OrganizationProposal(
                proposal_key=strategy,
                name=name,
                rationale=rationale,
                members=tuple(members),
                tasks=tuple(tasks),
                capability_gaps=tuple(gaps),
                metrics=metrics,
            )
        )
    return sorted(proposals, key=lambda item: item.metrics.get("recommendation_score", 0), reverse=True)


def plan_tasks(requirements: list[str], required_capabilities: list[str], risk_level: str, *, strategy: str = "balanced") -> list[PlannedTask]:
    tasks: list[PlannedTask] = [
        PlannedTask(
            task_key="analysis.repository",
            title="Analyze repository and mission boundaries",
            description="Inspect repository scope, mission requirements, constraints, and expected evidence before implementation planning.",
            category="Analysis",
            owner_role_key="product_analyst",
            required_capabilities=("requirement_analysis",),
            outputs=("repository_findings", "requirement_map"),
            acceptance_criteria=("Repository scope is identified.", "Every requirement has an owner candidate."),
            verification_methods=("product_review",),
            estimated_hours=1.0,
            estimated_cost_usd=0.25,
            estimated_tokens=4000,
        ),
        PlannedTask(
            task_key="design.architecture",
            title="Confirm architecture and implementation strategy",
            description="Choose the safest implementation strategy and document trade-offs.",
            category="Design",
            owner_role_key="solution_architect",
            required_capabilities=("system_architecture", "architecture_tradeoff_analysis"),
            dependencies=("analysis.repository",),
            outputs=("architecture_decision",),
            acceptance_criteria=("Implementation boundaries are explicit.", "Rejected alternatives are recorded."),
            verification_methods=("architecture_review",),
            estimated_hours=1.5,
            estimated_cost_usd=0.5,
            estimated_tokens=7000,
        ),
    ]
    if any(_backend_capability(item) for item in required_capabilities):
        tasks.append(
            PlannedTask(
                task_key="implementation.backend",
                title="Implement backend changes",
                description="Implement approved backend/API/data changes inside the scoped repository boundaries.",
                category="Implementation",
                owner_role_key="backend_engineer",
                required_capabilities=tuple(item for item in required_capabilities if _backend_capability(item)) or ("api_design",),
                dependencies=("design.architecture",),
                outputs=("backend_diff", "backend_tests"),
                acceptance_criteria=("Backend behavior matches acceptance criteria.", "Backend tests or smoke checks are defined."),
                verification_methods=("backend_tests", "build_verification"),
                risk_level=risk_level,
                estimated_hours=3.0,
                estimated_cost_usd=1.2,
                estimated_tokens=14000,
            )
        )
    if any(_frontend_capability(item) for item in required_capabilities):
        tasks.append(
            PlannedTask(
                task_key="implementation.frontend",
                title="Implement frontend changes",
                description="Implement approved UI/workspace changes inside the scoped repository boundaries.",
                category="Implementation",
                owner_role_key="frontend_engineer",
                required_capabilities=tuple(item for item in required_capabilities if _frontend_capability(item)) or ("react_development",),
                dependencies=("design.architecture",),
                outputs=("frontend_diff", "frontend_build"),
                acceptance_criteria=("UI behavior matches acceptance criteria.", "Responsive and accessible states are covered."),
                verification_methods=("frontend_build", "accessibility_review"),
                risk_level=risk_level,
                estimated_hours=3.0,
                estimated_cost_usd=1.2,
                estimated_tokens=14000,
            )
        )
    if len(tasks) == 2:
        tasks.append(
            PlannedTask(
                task_key="implementation.general",
                title="Implement scoped repository change",
                description="Implement the approved change within mission boundaries.",
                category="Implementation",
                owner_role_key="backend_engineer",
                required_capabilities=tuple(required_capabilities[:4]) or ("api_design",),
                dependencies=("design.architecture",),
                outputs=("implementation_diff",),
                acceptance_criteria=("The requested change is visible in the repository diff.",),
                verification_methods=("build_verification",),
                risk_level=risk_level,
                estimated_hours=2.0,
                estimated_cost_usd=0.8,
                estimated_tokens=9000,
            )
        )
    review_dependencies = implementation_keys = tuple(task.task_key for task in tasks if task.category == "Implementation")
    if strategy == "assurance" and implementation_keys:
        tasks.append(
            PlannedTask(
                task_key="review.architecture",
                title="Run architecture assurance review",
                description="Independently verify architectural impact, migration safety, and future maintainability.",
                category="Review",
                owner_role_key="solution_architect",
                required_capabilities=("architecture_tradeoff_analysis",),
                dependencies=implementation_keys,
                outputs=("architecture_assurance_report",),
                acceptance_criteria=("Architecture risks are documented.", "Migration and rollback considerations are explicit."),
                verification_methods=("architecture_review",),
                risk_level="medium",
                estimated_hours=0.75,
                estimated_cost_usd=0.3,
                estimated_tokens=3500,
            )
        )
        review_dependencies = (*implementation_keys, "review.architecture")
    tasks.extend(
        [
            PlannedTask(
                task_key="review.qa",
                title="Run QA review and verification",
                description="Validate implementation evidence and ensure requirements are covered.",
                category="Review",
                owner_role_key="qa_reviewer",
                required_capabilities=("build_verification", "evidence_validation"),
                dependencies=review_dependencies,
                outputs=("qa_report",),
                acceptance_criteria=("Failed checks block completion.", "Evidence references every implementation task."),
                verification_methods=("evidence_review",),
                risk_level="medium",
                estimated_hours=1.0,
                estimated_cost_usd=0.35,
                estimated_tokens=4500,
            ),
            PlannedTask(
                task_key="review.security",
                title="Run independent security review",
                description="Review implementation for authentication, authorization, secrets, dependency, and policy risks.",
                category="Review",
                owner_role_key="security_reviewer",
                required_capabilities=("secure_code_review",),
                dependencies=implementation_keys,
                outputs=("security_report",),
                acceptance_criteria=("Implementers do not approve their own work.", "Unsafe findings block completion."),
                verification_methods=("security_review",),
                risk_level="high" if risk_level in {"high", "critical"} else "medium",
                estimated_hours=1.0,
                estimated_cost_usd=0.35,
                estimated_tokens=4500,
            ),
            PlannedTask(
                task_key="approval.human_plan",
                title="Human approval before execution",
                description="Human owner reviews organization, workflow, risk, effort, and approval gates before implementation begins.",
                category="Approval",
                owner_role_key="human_approver",
                required_capabilities=("acceptance_criteria_definition",),
                dependencies=("review.qa", "review.security"),
                outputs=("approved_plan",),
                acceptance_criteria=("A human vote is required.", "AI approval cannot satisfy quorum."),
                verification_methods=("approval_quorum",),
                risk_level="high",
                estimated_hours=0.25,
                estimated_cost_usd=0.05,
                estimated_tokens=1000,
            ),
        ]
    )
    return tasks


def validate_plan(members: list[PlannedMember], tasks: list[PlannedTask], requirements: list[str]) -> dict[str, Any]:
    role_by_key = {member.role_key: member for member in members}
    task_by_key = {task.task_key: task for task in tasks}
    errors: list[str] = []
    for task in tasks:
        if task.owner_role_key not in role_by_key:
            errors.append(f"Task {task.task_key} has no valid owner.")
        if not task.acceptance_criteria:
            errors.append(f"Task {task.task_key} has no acceptance criteria.")
        if not task.verification_methods:
            errors.append(f"Task {task.task_key} has no verification method.")
        for dependency in task.dependencies:
            if dependency not in task_by_key:
                errors.append(f"Task {task.task_key} depends on unknown task {dependency}.")
    for task in tasks:
        owner = role_by_key.get(task.owner_role_key)
        if task.category == "Review" and owner and owner.can_implement and owner.can_review:
            errors.append(f"Review task {task.task_key} violates separation of duties.")
    graph = defaultdict(list)
    indegree = {task.task_key: 0 for task in tasks}
    for task in tasks:
        for dependency in task.dependencies:
            graph[dependency].append(task.task_key)
            indegree[task.task_key] += 1
    queue = deque([key for key, value in indegree.items() if value == 0])
    visited: list[str] = []
    while queue:
        key = queue.popleft()
        visited.append(key)
        for child in graph[key]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(visited) != len(tasks):
        errors.append("Workflow graph contains a cycle.")
    return {
        "valid": not errors,
        "errors": errors,
        "requirement_coverage": {f"requirement_{index}": [task.task_key for task in tasks if task.category == "Implementation"] for index, _ in enumerate(requirements, start=1)},
        "critical_path": _critical_path(tasks),
        "parallelization_ratio": round(max(1, len([task for task in tasks if task.category == "Implementation"])) / max(1, len(tasks)), 2),
    }


def plan_metrics(members: list[PlannedMember], tasks: list[PlannedTask], validation: dict[str, Any], capability_gaps: list[str]) -> dict[str, Any]:
    review_tasks = [task for task in tasks if task.category == "Review"]
    implementation_tasks = [task for task in tasks if task.category == "Implementation"]
    total_effort = round(sum(task.estimated_hours for task in tasks), 2)
    total_cost = round(sum(task.estimated_cost_usd for task in tasks), 4)
    total_tokens = sum(task.estimated_tokens for task in tasks)
    average_specialist_score = round(sum(member.score for member in members) / max(1, len(members)), 3)
    return {
        "tasks_generated": len(tasks),
        "organization_size": len(members),
        "capability_gaps": len(capability_gaps),
        "critical_path_duration": len(validation["critical_path"]),
        "estimated_engineering_hours": total_effort,
        "estimated_cost_usd": total_cost,
        "estimated_tokens": total_tokens,
        "average_specialist_score": average_specialist_score,
        "review_coverage": round(len(review_tasks) / max(1, len(implementation_tasks)), 2),
        "parallelization_ratio": validation["parallelization_ratio"],
    }


def _responsibility_for_role(role_key: str) -> str:
    return {
        "mission_lead": "Coordinate the temporary engineering organization and maintain mission alignment.",
        "product_analyst": "Map requirements, risks, and acceptance criteria.",
        "solution_architect": "Define implementation strategy and architecture trade-offs.",
        "backend_engineer": "Own scoped backend/API/data implementation tasks.",
        "frontend_engineer": "Own scoped frontend/UI implementation tasks.",
        "devops_reviewer": "Review deployment, observability, and release safety.",
        "qa_reviewer": "Independently validate tests, checks, and evidence.",
        "security_reviewer": "Independently review security and policy risk.",
        "human_approver": "Govern the plan and provide required human approval.",
    }[role_key]


def _backend_capability(capability: str) -> bool:
    return any(token in capability for token in ("backend", "api", "fastapi", "python", "postgres", "database", "migration", "auth"))


def _frontend_capability(capability: str) -> bool:
    return any(token in capability for token in ("frontend", "react", "nextjs", "ui", "accessibility"))


def _specialist_score(role_key: str, required_capabilities: list[str], performance_history: dict[str, dict[str, float]]) -> float:
    history = performance_history.get(role_key, {})
    registry_item = SPECIALIST_REGISTRY[role_key]
    coverage = len(set(registry_item["capabilities"]).intersection(required_capabilities)) / max(1, len(required_capabilities))
    quality = float(history.get("quality", 0.82))
    speed = float(history.get("speed", 0.75))
    cost_efficiency = float(history.get("cost_efficiency", 0.75))
    score = (quality * 0.5) + (speed * 0.2) + (cost_efficiency * 0.15) + (coverage * 0.15)
    return round(min(1.0, max(0.0, score)), 3)


def _score_reason(role_key: str, required_capabilities: list[str], performance_history: dict[str, dict[str, float]]) -> str:
    if role_key in performance_history:
        return "Ranked using historical quality, speed, cost efficiency, and capability coverage."
    covered = sorted(set(SPECIALIST_REGISTRY[role_key]["capabilities"]).intersection(required_capabilities))
    if covered:
        return f"Selected for direct capability match: {', '.join(covered[:3])}."
    return "Selected to satisfy coordination, review, approval, or separation-of-duties policy."


def _proposal_score(strategy: str, risk_level: str, metrics: dict[str, Any]) -> float:
    score = 0.72
    score += min(0.15, float(metrics.get("average_specialist_score", 0.75)) * 0.15)
    score += min(0.08, float(metrics.get("review_coverage", 0.0)) * 0.04)
    score -= min(0.08, int(metrics.get("capability_gaps", 0)) * 0.03)
    if strategy == "balanced":
        score += 0.07
    if strategy == "assurance" and risk_level in {"high", "critical"}:
        score += 0.06
    if strategy == "lean" and risk_level in {"high", "critical"}:
        score -= 0.08
    return round(min(1.0, max(0.0, score)), 3)


def _critical_path(tasks: list[PlannedTask]) -> tuple[str, ...]:
    by_key = {task.task_key: task for task in tasks}
    memo: dict[str, tuple[str, ...]] = {}

    def path_to(key: str) -> tuple[str, ...]:
        if key in memo:
            return memo[key]
        task = by_key[key]
        if not task.dependencies:
            memo[key] = (key,)
        else:
            memo[key] = max(((*path_to(dep), key) for dep in task.dependencies if dep in by_key), key=len, default=(key,))
        return memo[key]

    return max((path_to(task.task_key) for task in tasks), key=len, default=())
