from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import ArceusApproval, ArceusArtifact, ArceusEvidence, ArceusEvent, ArceusTask, ArceusTaskDependency

from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..context_engine.api_schemas import ContextBuildRequest, ModelContextProfile
from ..context_engine.service import build_context_package
from ..execution.service import RuntimeTaskExecutor
from .api_schemas import (
    MissionRuntimeReportResponse,
    MissionRuntimeSnapshotResponse,
    RuntimeBudgetSummary,
    RuntimeEventSummary,
    RuntimePlanValidationResponse,
    RuntimeTaskSpec,
    TaskContextBuildResponse,
    TaskRuntimeSummary,
)


COMPLETED_WEIGHT = 1.0
STATUS_WEIGHTS = {
    "completed": COMPLETED_WEIGHT,
    "verifying": 0.85,
    "reviewing": 0.75,
    "running": 0.5,
    "ready": 0.15,
    "pending": 0.0,
    "blocked": 0.0,
    "failed": 0.0,
    "cancelled": 0.0,
}


@dataclass(frozen=True)
class _DagNode:
    key: str
    seconds: int
    dependencies: tuple[str, ...]


def _estimate_seconds_from_contract(task: ArceusTask | RuntimeTaskSpec) -> int:
    if isinstance(task, RuntimeTaskSpec):
        return task.estimated_seconds
    contracts: list[dict[str, Any]] = [task.output_contract or {}, task.input_contract or {}]
    for contract in contracts:
        estimates = contract.get("estimates") or {}
        if "seconds" in estimates:
            return max(1, int(estimates["seconds"] or 1))
        if "minutes" in estimates:
            return max(1, int(float(estimates["minutes"] or 1) * 60))
        if "hours" in estimates:
            return max(1, int(float(estimates["hours"] or 1) * 3_600))
    return 300


def validate_task_dag(tasks: list[RuntimeTaskSpec]) -> RuntimePlanValidationResponse:
    errors: list[str] = []
    by_key: dict[str, RuntimeTaskSpec] = {}
    duplicates: set[str] = set()
    for task in tasks:
        if task.task_key in by_key:
            duplicates.add(task.task_key)
        by_key[task.task_key] = task
    for key in sorted(duplicates):
        errors.append(f"Duplicate task key: {key}")

    nodes = {
        task.task_key: _DagNode(
            key=task.task_key,
            seconds=task.estimated_seconds,
            dependencies=tuple(dict.fromkeys(task.dependencies)),
        )
        for task in tasks
    }
    edge_count = 0
    children: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {key: 0 for key in nodes}
    for node in nodes.values():
        for dependency in node.dependencies:
            edge_count += 1
            if dependency == node.key:
                errors.append(f"Task {node.key} cannot depend on itself.")
                continue
            if dependency not in nodes:
                errors.append(f"Task {node.key} depends on missing task {dependency}.")
                continue
            children[dependency].append(node.key)
            indegree[node.key] += 1

    queue = deque(sorted(key for key, value in indegree.items() if value == 0))
    order: list[str] = []
    while queue:
        key = queue.popleft()
        order.append(key)
        for child in sorted(children.get(key, [])):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(nodes):
        cyclic = sorted(key for key, value in indegree.items() if value > 0)
        errors.append("Cycle detected in task graph: " + ", ".join(cyclic))

    critical_path, critical_seconds = _critical_path(nodes, order) if not errors else ([], 0)
    ready_task_keys = [task.task_key for task in tasks if not task.dependencies and task.status in {"pending", "ready"}]
    return RuntimePlanValidationResponse(
        valid=not errors,
        errors=errors,
        topological_order=order if not errors else [],
        critical_path=critical_path,
        critical_path_seconds=critical_seconds,
        ready_task_keys=ready_task_keys,
        task_count=len(tasks),
        edge_count=edge_count,
    )


def _critical_path(nodes: dict[str, _DagNode], order: list[str]) -> tuple[list[str], int]:
    if not nodes:
        return [], 0
    best_duration: dict[str, int] = {}
    predecessor: dict[str, str | None] = {}
    for key in order:
        node = nodes[key]
        if not node.dependencies:
            best_duration[key] = node.seconds
            predecessor[key] = None
            continue
        parent = max(node.dependencies, key=lambda dep: best_duration.get(dep, 0))
        best_duration[key] = best_duration.get(parent, 0) + node.seconds
        predecessor[key] = parent
    end = max(best_duration, key=best_duration.get)
    path: list[str] = []
    cursor: str | None = end
    while cursor is not None:
        path.append(cursor)
        cursor = predecessor.get(cursor)
    path.reverse()
    return path, int(best_duration[end])


def weighted_progress(tasks: list[ArceusTask | RuntimeTaskSpec]) -> float:
    if not tasks:
        return 0.0
    total = 0.0
    completed = 0.0
    for task in tasks:
        weight = float(_estimate_seconds_from_contract(task))
        total += weight
        completed += weight * STATUS_WEIGHTS.get(str(task.status), 0.0)
    return round((completed / total) * 100, 2) if total else 0.0


class MissionRuntimeService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def snapshot(self, *, tenant_id: UUID, mission_id: UUID) -> MissionRuntimeSnapshotResponse:
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        tasks = self.uow.tasks.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=250)
        dependencies_by_task = self._dependency_keys_by_task(tenant_id=tenant_id, tasks=tasks)
        task_specs = [self._task_to_spec(task, dependencies_by_task.get(task.id, [])) for task in tasks]
        validation = validate_task_dag(task_specs) if task_specs else RuntimePlanValidationResponse(valid=True)
        counts: dict[str, int] = defaultdict(int)
        for task in tasks:
            counts[task.status] += 1
        events = self._latest_events(tenant_id=tenant_id, mission_id=mission_id, limit=12)
        pending_approvals = len(self.uow.approvals.list(tenant_id=tenant_id, mission_id=mission_id, status="pending", limit=100))
        evidence_count = len(self.uow.evidence.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=100))
        artifact_count = len(self.uow.artifacts.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=100))
        return MissionRuntimeSnapshotResponse(
            mission_id=mission.id,
            mission_status=mission.status,
            mission_version=int(mission.version_number or 1),
            objective=mission.objective,
            progress_percent=weighted_progress(tasks),
            task_counts=dict(counts),
            ready_tasks=self._task_summaries(tenant_id=tenant_id, tasks=[task for task in tasks if task.status == "ready"], dependencies_by_task=dependencies_by_task),
            running_tasks=self._task_summaries(tenant_id=tenant_id, tasks=[task for task in tasks if task.status == "running"], dependencies_by_task=dependencies_by_task),
            blocked_tasks=self._task_summaries(tenant_id=tenant_id, tasks=[task for task in tasks if task.status == "blocked"], dependencies_by_task=dependencies_by_task),
            failed_tasks=self._task_summaries(tenant_id=tenant_id, tasks=[task for task in tasks if task.status == "failed"], dependencies_by_task=dependencies_by_task),
            critical_path=validation.critical_path,
            critical_path_seconds=validation.critical_path_seconds,
            pending_approvals=pending_approvals,
            evidence_count=evidence_count,
            artifact_count=artifact_count,
            budget=self._budget_summary(mission),
            latest_events=events,
            generated_at=datetime.now(timezone.utc),
        )

    def report(self, *, tenant_id: UUID, mission_id: UUID) -> MissionRuntimeReportResponse:
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        tasks = self.uow.tasks.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=250)
        approvals = self.uow.approvals.list(tenant_id=tenant_id, mission_id=mission_id, status="pending", limit=100)
        evidence = self.uow.evidence.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=100)
        artifacts = self.uow.artifacts.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=100)
        completed = [task.task_key for task in tasks if task.status == "completed"]
        failed = [task.task_key for task in tasks if task.status == "failed"]
        blocked = [task.task_key for task in tasks if task.status == "blocked"]
        warnings = self._report_warnings(mission_status=mission.status, tasks=tasks, approvals=approvals, evidence=evidence)
        return MissionRuntimeReportResponse(
            mission_id=mission.id,
            mission_status=mission.status,
            objective=mission.objective,
            progress_percent=weighted_progress(tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            blocked_tasks=blocked,
            outstanding_approvals=[f"{approval.approval_type}:{approval.subject_type}" for approval in approvals],
            evidence_count=len(evidence),
            artifact_count=len(artifacts),
            warnings=warnings,
            remaining_risks=self._remaining_risks(tasks=tasks, approvals=approvals),
            next_actions=self._next_actions(mission_status=mission.status, tasks=tasks, approvals=approvals),
            generated_at=datetime.now(timezone.utc),
        )

    def run_next(self, *, tenant_id: UUID, mission_id: UUID, worker_id: str, ttl_seconds: int) -> dict[str, Any]:
        result = RuntimeTaskExecutor(self.uow).run_next(
            tenant_id=tenant_id,
            mission_id=mission_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
        )
        self.uow.commit()
        return result

    def build_task_context(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        model: ModelContextProfile,
        root_path: str | None,
        repository_id: str | None,
        force_rebuild: bool,
    ) -> TaskContextBuildResponse:
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=task_id)
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=task.mission_id)
        dependencies = self.uow.tasks.dependencies(tenant_id=tenant_id, task_id=task_id)
        dependency_summaries = []
        for dependency in dependencies:
            dependency_task = self.uow.tasks.get(tenant_id=tenant_id, task_id=dependency.depends_on_task_id)
            dependency_summaries.append(f"{dependency_task.task_key}: {dependency_task.title} ({dependency_task.status})")
        checkpoints = self.uow.runtime_execution.checkpoints_for_task(tenant_id=tenant_id, task_id=task_id, limit=5)
        latest_events = self._latest_events(tenant_id=tenant_id, mission_id=mission.id, limit=8)
        prompt = "\n".join(
            [
                mission.objective,
                "",
                f"Task {task.task_key}: {task.title}",
                f"Task type: {task.task_type}; status: {task.status}",
                "Input contract: " + str(task.input_contract or {}),
                "Output contract: " + str(task.output_contract or {}),
                "Acceptance criteria: " + "; ".join(task.acceptance_criteria or []),
                "Dependencies: " + ("; ".join(dependency_summaries) if dependency_summaries else "none"),
            ]
        )
        package, intent, cache_hit = build_context_package(
            ContextBuildRequest(
                mission_id=str(mission.id),
                prompt=prompt,
                repository_id=repository_id,
                root_path=root_path,
                model=model,
                conversation=[f"{event.event_type}: {event.payload}" for event in latest_events],
                memories=[f"Mission status: {mission.status}", f"Mission risk: {mission.risk_level}"],
                execution_state=[str(checkpoint.execution_state or checkpoint.outputs or {}) for checkpoint in checkpoints],
                force_rebuild=force_rebuild,
            )
        )
        return TaskContextBuildResponse(task_id=task.id, task_key=task.task_key, intent=intent, package=package, cache_hit=cache_hit)

    def _dependency_keys_by_task(self, *, tenant_id: UUID, tasks: list[ArceusTask]) -> dict[UUID, list[str]]:
        task_by_id = {task.id: task for task in tasks}
        dependency_rows = (
            self.uow.db.query(ArceusTaskDependency)
            .filter(ArceusTaskDependency.tenant_id == tenant_id, ArceusTaskDependency.task_id.in_([task.id for task in tasks]))
            .all()
            if tasks
            else []
        )
        dependencies: dict[UUID, list[str]] = defaultdict(list)
        for row in dependency_rows:
            dependency = task_by_id.get(row.depends_on_task_id)
            if dependency is not None:
                dependencies[row.task_id].append(dependency.task_key)
        return dependencies

    def _task_to_spec(self, task: ArceusTask, dependencies: list[str]) -> RuntimeTaskSpec:
        output_contract = task.output_contract or {}
        input_contract = task.input_contract or {}
        estimates = output_contract.get("estimates") or input_contract.get("estimates") or {}
        seconds = _estimate_seconds_from_contract(task)
        return RuntimeTaskSpec(
            task_key=task.task_key,
            title=task.title,
            task_type=task.task_type,
            dependencies=dependencies,
            status=task.status,
            estimated_seconds=seconds,
            priority=int(output_contract.get("priority") or input_contract.get("priority") or 50),
            risk_level=str(output_contract.get("risk_level") or input_contract.get("risk_level") or "medium"),
            acceptance_criteria=list(task.acceptance_criteria or []),
            metadata={"estimates": estimates},
        )

    def _task_summaries(self, *, tenant_id: UUID, tasks: list[ArceusTask], dependencies_by_task: dict[UUID, list[str]]) -> list[TaskRuntimeSummary]:
        return [
            TaskRuntimeSummary(
                id=task.id,
                task_key=task.task_key,
                title=task.title,
                task_type=task.task_type,
                status=task.status,
                owner_member_id=task.owner_member_id,
                priority_score=self.uow.tasks.priority_score(task),
                dependencies=dependencies_by_task.get(task.id, []),
                estimated_seconds=_estimate_seconds_from_contract(task),
                progress_weight=float(_estimate_seconds_from_contract(task)),
                failure_reason=task.failure_reason,
            )
            for task in tasks
        ]

    def _latest_events(self, *, tenant_id: UUID, mission_id: UUID, limit: int) -> list[RuntimeEventSummary]:
        rows = (
            self.uow.db.query(ArceusEvent)
            .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_id == mission_id)
            .order_by(ArceusEvent.created_at.desc(), ArceusEvent.id.desc())
            .limit(min(limit, 100))
            .all()
        )
        return [
            RuntimeEventSummary(
                id=row.id,
                event_type=row.event_type,
                aggregate_type=row.aggregate_type,
                aggregate_version=int(row.aggregate_version or 1),
                actor_type=row.actor_type,
                actor_id=row.actor_id,
                payload=row.payload or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

    def _budget_summary(self, mission) -> RuntimeBudgetSummary:
        maximum = _decimal_to_float(mission.maximum_budget_amount)
        actual = _decimal_to_float(mission.actual_cost_amount) or 0.0
        consumed = round((actual / maximum) * 100, 2) if maximum and maximum > 0 else None
        return RuntimeBudgetSummary(
            maximum_budget_amount=maximum,
            actual_cost_amount=actual,
            budget_currency=mission.budget_currency or "USD",
            consumed_percent=consumed,
        )

    def _report_warnings(self, *, mission_status: str, tasks: list[ArceusTask], approvals: list[ArceusApproval], evidence: list[ArceusEvidence]) -> list[str]:
        warnings: list[str] = []
        if mission_status in {"failed", "blocked"}:
            warnings.append(f"Mission is currently {mission_status}.")
        if any(task.status == "failed" for task in tasks):
            warnings.append("One or more tasks failed and dependent work may be blocked.")
        if approvals:
            warnings.append("Human approval is required before the runtime can proceed.")
        if tasks and not evidence and all(task.status != "completed" for task in tasks):
            warnings.append("No verification evidence has been collected yet.")
        return warnings

    def _remaining_risks(self, *, tasks: list[ArceusTask], approvals: list[ArceusApproval]) -> list[str]:
        risks: list[str] = []
        for task in tasks:
            risk_level = str((task.output_contract or {}).get("risk_level") or (task.input_contract or {}).get("risk_level") or "")
            if task.status not in {"completed", "cancelled"} and risk_level in {"high", "critical"}:
                risks.append(f"{task.task_key}: {risk_level} risk still open")
        for approval in approvals:
            if approval.risk_level in {"high", "critical"}:
                risks.append(f"{approval.approval_type}: {approval.risk_level} approval pending")
        return risks[:20]

    def _next_actions(self, *, mission_status: str, tasks: list[ArceusTask], approvals: list[ArceusApproval]) -> list[str]:
        if approvals:
            return ["Review pending approvals before continuing execution."]
        if mission_status == "ready":
            return ["Start the mission runtime."]
        if mission_status == "running" and any(task.status == "ready" for task in tasks):
            return ["Run the next ready task."]
        if any(task.status == "failed" for task in tasks):
            return ["Inspect failed tasks, then retry or replan."]
        if tasks and all(task.status == "completed" for task in tasks):
            return ["Generate the final mission report and request completion approval."]
        return ["Continue mission planning or wait for runtime events."]


def _decimal_to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)
