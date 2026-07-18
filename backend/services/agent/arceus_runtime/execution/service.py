from __future__ import annotations

from uuid import UUID

from services.shared.arceus_core_models import ArceusTask

from ..application.errors import RuntimeStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .gateways import DeterministicModelGateway, DeterministicToolGateway, GatewayResult, ModelGateway, TaskContextPackage, ToolGateway, VerificationEngine


class RuntimeSchedulerService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def schedule(self, *, tenant_id: UUID, mission_id: UUID, limit: int = 25) -> dict:
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        if mission.status != "running":
            raise RuntimeStateConflict("Scheduler can only run active missions.", details={"mission_status": mission.status})
        expired_leases = self.uow.runtime_execution.expire_stale_leases(tenant_id=tenant_id)
        ready_tasks = self.uow.tasks.prioritized_ready_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=limit)
        all_tasks = self.uow.tasks.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=250)
        completed_count = len([task for task in all_tasks if task.status == "completed"])
        if all_tasks and completed_count == len(all_tasks):
            mission.status = "completed"
            mission.version_number = int(mission.version_number) + 1
        return {
            "mission": mission,
            "ready_tasks": ready_tasks,
            "total_count": len(all_tasks),
            "completed_count": completed_count,
            "expired_leases": expired_leases,
        }


class RuntimeTaskExecutor:
    def __init__(
        self,
        uow: SqlAlchemyUnitOfWork,
        *,
        model_gateway: ModelGateway | None = None,
        tool_gateway: ToolGateway | None = None,
        verification_engine: VerificationEngine | None = None,
    ) -> None:
        self.uow = uow
        self.model_gateway = model_gateway or DeterministicModelGateway()
        self.tool_gateway = tool_gateway or DeterministicToolGateway()
        self.verification_engine = verification_engine or VerificationEngine()

    def run_next(self, *, tenant_id: UUID, mission_id: UUID, worker_id: str, ttl_seconds: int = 120):
        scheduled = RuntimeSchedulerService(self.uow).schedule(tenant_id=tenant_id, mission_id=mission_id, limit=1)
        if not scheduled["ready_tasks"]:
            return {"status": "idle", "expired_leases": scheduled["expired_leases"]}
        task = scheduled["ready_tasks"][0]
        worker = RuntimeWorkerService(self.uow)
        task, mission, lease = worker.acquire(tenant_id=tenant_id, task_id=task.id, worker_id=worker_id, ttl_seconds=ttl_seconds)
        attempt = self.uow.tasks.create_attempt(task, worker_id=worker_id)
        context = self.compile_context(tenant_id=tenant_id, task=task)
        try:
            worker.heartbeat(
                tenant_id=tenant_id,
                lease_id=lease.id,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
                progress_percent=35,
                checkpoint={"attempt_id": str(attempt.id), "task_key": task.task_key},
                current_operation="executing_task",
            )
            result = self._execute_context(context)
            verified = self.verification_engine.verify(context, result)
            if verified.status == "succeeded":
                task, mission, lease, checkpoint = worker.complete(
                    tenant_id=tenant_id,
                    lease_id=lease.id,
                    worker_id=worker_id,
                    outputs={**verified.outputs, "evidence": verified.evidence, "attempt_id": str(attempt.id)},
                    progress_percent=100,
                )
                self.uow.tasks.finish_attempt(attempt, status="succeeded", result=verified.outputs)
                self._unblock_dependents(tenant_id=tenant_id, completed_task=task)
                return {"status": "completed", "task_id": str(task.id), "checkpoint_id": str(checkpoint.id), "attempt_id": str(attempt.id)}
            return self._handle_failure(
                worker=worker,
                tenant_id=tenant_id,
                lease_id=lease.id,
                worker_id=worker_id,
                task=task,
                attempt=attempt,
                result=verified,
            )
        except Exception as exc:
            result = GatewayResult(status="failed", error=str(exc), retryable=True)
            return self._handle_failure(
                worker=worker,
                tenant_id=tenant_id,
                lease_id=lease.id,
                worker_id=worker_id,
                task=task,
                attempt=attempt,
                result=result,
            )

    def compile_context(self, *, tenant_id: UUID, task: ArceusTask) -> TaskContextPackage:
        dependencies = self.uow.tasks.dependencies(tenant_id=tenant_id, task_id=task.id)
        dependency_keys: list[str] = []
        for dependency in dependencies:
            dependency_task = self.uow.tasks.get(tenant_id=tenant_id, task_id=dependency.depends_on_task_id)
            dependency_keys.append(dependency_task.task_key)
        checkpoints = self.uow.runtime_execution.checkpoints_for_task(tenant_id=tenant_id, task_id=task.id, limit=1)
        return TaskContextPackage(
            task_id=str(task.id),
            task_key=task.task_key,
            title=task.title,
            task_type=task.task_type,
            input_contract=task.input_contract or {},
            output_contract=task.output_contract or {},
            acceptance_criteria=tuple(task.acceptance_criteria or ()),
            dependencies=tuple(dependency_keys),
            previous_checkpoint=(checkpoints[0].execution_state if checkpoints else None),
        )

    def _execute_context(self, context: TaskContextPackage) -> GatewayResult:
        if context.task_type in {"implementation", "verification"}:
            tool_result = self.tool_gateway.run(context)
            if tool_result.status != "succeeded":
                return tool_result
            model_result = self.model_gateway.run(context)
            return GatewayResult(
                status=model_result.status,
                outputs={**tool_result.outputs, **model_result.outputs},
                evidence=[*tool_result.evidence, *model_result.evidence],
                error=model_result.error,
                retryable=model_result.retryable,
            )
        return self.model_gateway.run(context)

    def _handle_failure(self, *, worker: RuntimeWorkerService, tenant_id: UUID, lease_id: UUID, worker_id: str, task: ArceusTask, attempt, result: GatewayResult):
        _task, _mission, _lease, checkpoint = worker.fail(
            tenant_id=tenant_id,
            lease_id=lease_id,
            worker_id=worker_id,
            error=result.error or "Task execution failed.",
            retryable=result.retryable,
        )
        self.uow.tasks.finish_attempt(
            attempt,
            status="failed",
            error={"message": result.error or "Task execution failed.", "retryable": result.retryable},
        )
        self._apply_retry_policy(task=task, retryable=result.retryable)
        if task.status == "failed":
            self._block_dependents(tenant_id=tenant_id, failed_task=task)
        return {"status": "failed", "task_id": str(task.id), "checkpoint_id": str(checkpoint.id), "attempt_id": str(attempt.id), "retryable": result.retryable}

    def _apply_retry_policy(self, *, task: ArceusTask, retryable: bool) -> None:
        attempts = self.uow.tasks.attempts(tenant_id=task.tenant_id, task_id=task.id)
        max_attempts = int(((task.output_contract or {}).get("retry_policy") or {}).get("max_attempts", 3))
        if retryable and len(attempts) < max_attempts:
            task.status = "ready"
            task.failure_reason = None
            task.completed_at = None
            task.output_contract = {
                **(task.output_contract or {}),
                "retry": {"attempts": len(attempts), "max_attempts": max_attempts, "backoff_seconds": self._backoff_seconds(len(attempts))},
            }
            task.version_number = int(task.version_number or 1) + 1

    def _block_dependents(self, *, tenant_id: UUID, failed_task: ArceusTask) -> None:
        from services.shared.arceus_core_models import ArceusTaskDependency

        dependencies = self.uow.db.query(ArceusTaskDependency).filter(
            ArceusTaskDependency.tenant_id == tenant_id,
            ArceusTaskDependency.depends_on_task_id == failed_task.id,
        ).all()
        for dependency in dependencies:
            dependent = self.uow.tasks.get(tenant_id=tenant_id, task_id=dependency.task_id)
            if dependent.status in {"pending", "ready"}:
                dependent.status = "blocked"
                dependent.failure_reason = f"Blocked because dependency {failed_task.task_key} failed verification."
                dependent.version_number = int(dependent.version_number or 1) + 1

    def _unblock_dependents(self, *, tenant_id: UUID, completed_task: ArceusTask) -> None:
        from services.shared.arceus_core_models import ArceusTaskDependency

        dependencies = self.uow.db.query(ArceusTaskDependency).filter(
            ArceusTaskDependency.tenant_id == tenant_id,
            ArceusTaskDependency.depends_on_task_id == completed_task.id,
        ).all()
        for dependency in dependencies:
            dependent = self.uow.tasks.get(tenant_id=tenant_id, task_id=dependency.task_id)
            if dependent.status in {"pending", "blocked"} and self.uow.tasks.dependencies_satisfied(tenant_id=tenant_id, task_id=dependent.id):
                dependent.status = "ready"
                dependent.failure_reason = None
                dependent.version_number = int(dependent.version_number or 1) + 1

    def _backoff_seconds(self, attempt_count: int) -> int:
        return min(60, max(5, 5 * (2 ** max(0, attempt_count - 1))))


class RuntimeWorkerService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def acquire(self, *, tenant_id: UUID, task_id: UUID, worker_id: str, ttl_seconds: int):
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=task_id)
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=task.mission_id)
        if not self.uow.tasks.dependencies_satisfied(tenant_id=tenant_id, task_id=task.id):
            raise RuntimeStateConflict("Task dependencies are not complete.", details={"task_id": str(task.id)})
        lease = self.uow.runtime_execution.acquire_lease(
            tenant_id=tenant_id,
            mission=mission,
            task=task,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
        )
        self._append_task_event(
            tenant_id=tenant_id,
            task=task,
            event_type="NODE_LEASED",
            actor_id=worker_id,
            payload={"lease_id": str(lease.id), "worker_id": worker_id, "status": task.status},
        )
        return task, mission, lease

    def heartbeat(self, *, tenant_id: UUID, lease_id: UUID, worker_id: str, ttl_seconds: int, progress_percent: int, checkpoint: dict, current_operation: str | None):
        lease = self.uow.runtime_execution.get_lease(tenant_id=tenant_id, lease_id=lease_id)
        self._validate_worker(lease, worker_id)
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=lease.task_id)
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=task.mission_id)
        self.uow.runtime_execution.heartbeat(lease, ttl_seconds=ttl_seconds)
        checkpoint_row = self.uow.runtime_execution.create_checkpoint(
            tenant_id=tenant_id,
            mission_id=mission.id,
            task_id=task.id,
            workflow_id=mission.active_workflow_id,
            lease_id=lease.id,
            checkpoint_key=f"heartbeat:{lease.id}:{lease.version_number}",
            workflow_version=int(mission.version_number),
            worker_id=worker_id,
            execution_state={"phase": "heartbeat", "current_operation": current_operation, **(checkpoint or {})},
            progress_percent=progress_percent,
        )
        self.uow.events.append(
            tenant_id=tenant_id,
            aggregate_type="runtime_checkpoint",
            aggregate_id=checkpoint_row.id,
            aggregate_version=checkpoint_row.version_number,
            event_type="CHECKPOINT_CREATED",
            actor_type="worker",
            actor_id=worker_id,
            payload={
                "task_id": str(task.id),
                "mission_id": str(mission.id),
                "lease_id": str(lease.id),
                "checkpoint_id": str(checkpoint_row.id),
                "progress_percent": progress_percent,
            },
            correlation_id=mission.id,
            idempotency_key=f"CHECKPOINT_CREATED:{checkpoint_row.id}:{worker_id}",
        )
        return task, mission, lease, checkpoint_row

    def complete(self, *, tenant_id: UUID, lease_id: UUID, worker_id: str, outputs: dict, progress_percent: int):
        lease = self.uow.runtime_execution.get_lease(tenant_id=tenant_id, lease_id=lease_id)
        self._validate_worker(lease, worker_id)
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=lease.task_id)
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=task.mission_id)
        checkpoint = self.uow.runtime_execution.create_checkpoint(
            tenant_id=tenant_id,
            mission_id=mission.id,
            task_id=task.id,
            workflow_id=mission.active_workflow_id,
            lease_id=lease.id,
            checkpoint_key=f"complete:{lease.id}",
            workflow_version=int(mission.version_number),
            worker_id=worker_id,
            execution_state={"phase": "completed"},
            outputs=outputs,
            progress_percent=progress_percent,
        )
        self.uow.runtime_execution.complete_task(task=task, lease=lease, outputs=outputs)
        self._append_task_event(
            tenant_id=tenant_id,
            task=task,
            event_type="NODE_COMPLETED",
            actor_id=worker_id,
            payload={"lease_id": str(lease.id), "checkpoint_id": str(checkpoint.id), "status": task.status},
        )
        return task, mission, lease, checkpoint

    def fail(self, *, tenant_id: UUID, lease_id: UUID, worker_id: str, error: str, retryable: bool):
        lease = self.uow.runtime_execution.get_lease(tenant_id=tenant_id, lease_id=lease_id)
        self._validate_worker(lease, worker_id)
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=lease.task_id)
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=task.mission_id)
        checkpoint = self.uow.runtime_execution.create_checkpoint(
            tenant_id=tenant_id,
            mission_id=mission.id,
            task_id=task.id,
            workflow_id=mission.active_workflow_id,
            lease_id=lease.id,
            checkpoint_key=f"failed:{lease.id}",
            workflow_version=int(mission.version_number),
            worker_id=worker_id,
            execution_state={"phase": "failed", "retryable": retryable, "error": error},
            outputs={},
            progress_percent=0,
        )
        self.uow.runtime_execution.fail_task(task=task, lease=lease, error=error)
        self._append_task_event(
            tenant_id=tenant_id,
            task=task,
            event_type="NODE_FAILED",
            actor_id=worker_id,
            payload={"lease_id": str(lease.id), "checkpoint_id": str(checkpoint.id), "retryable": retryable, "error": error},
        )
        return task, mission, lease, checkpoint

    def _validate_worker(self, lease, worker_id: str) -> None:
        if lease.worker_id != worker_id:
            raise RuntimeStateConflict("Lease belongs to a different worker.", details={"worker_id": worker_id})
        if lease.status != "active":
            raise RuntimeStateConflict("Lease is not active.", details={"lease_status": lease.status})

    def _append_task_event(self, *, tenant_id: UUID, task: ArceusTask, event_type: str, actor_id: str, payload: dict) -> None:
        self.uow.events.append(
            tenant_id=tenant_id,
            aggregate_type="task",
            aggregate_id=task.id,
            aggregate_version=task.version_number,
            event_type=event_type,
            actor_type="worker",
            actor_id=actor_id,
            payload={"task_id": str(task.id), "mission_id": str(task.mission_id), **payload},
            correlation_id=task.mission_id,
            idempotency_key=f"{event_type}:{task.id}:{task.version_number}:{actor_id}",
        )
