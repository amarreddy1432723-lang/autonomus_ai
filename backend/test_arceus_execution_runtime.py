import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.agent.arceus_runtime.execution.api_schemas import AcquireLeaseRequest, HeartbeatRequest
from services.agent.arceus_runtime.execution.routes import _checkpoint_response, _lease_response
from services.agent.arceus_runtime.execution.service import RuntimeSchedulerService, RuntimeTaskExecutor
from services.agent.arceus_runtime.workers.outbox import calculate_backoff_seconds


def test_runtime_lease_response_exposes_heartbeat_and_expiry() -> None:
    now = datetime.now(timezone.utc)
    lease = SimpleNamespace(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        worker_id="worker-1",
        lease_token="lease_abc",
        status="active",
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=120),
        version_number=3,
    )

    response = _lease_response(lease)

    assert response.worker_id == "worker-1"
    assert response.status == "active"
    assert response.heartbeat_at == now
    assert response.expires_at > response.heartbeat_at


def test_runtime_checkpoint_response_is_structured_for_replay() -> None:
    checkpoint = SimpleNamespace(
        id=uuid.uuid4(),
        mission_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        worker_lease_id=uuid.uuid4(),
        checkpoint_key="heartbeat:1",
        workflow_version=8,
        execution_state={"phase": "running", "current_operation": "writing tests"},
        outputs={"files": ["backend/test_runtime.py"]},
        progress_percent=45,
        created_by_worker_id="qa-worker",
        created_at=datetime.now(timezone.utc),
        version_number=1,
    )

    response = _checkpoint_response(checkpoint)

    assert response.execution_state["phase"] == "running"
    assert response.outputs["files"] == ["backend/test_runtime.py"]
    assert response.progress_percent == 45


def test_runtime_requests_enforce_worker_and_ttl_bounds() -> None:
    with pytest.raises(ValidationError):
        AcquireLeaseRequest(worker_id="x", ttl_seconds=120)
    with pytest.raises(ValidationError):
        AcquireLeaseRequest(worker_id="worker-1", ttl_seconds=5)
    with pytest.raises(ValidationError):
        HeartbeatRequest(worker_id="worker-1", progress_percent=101)


def test_runtime_retry_backoff_matches_bounded_policy() -> None:
    assert calculate_backoff_seconds(1) == 5
    assert calculate_backoff_seconds(2) == 10
    assert calculate_backoff_seconds(3) == 20
    assert calculate_backoff_seconds(10) == 60


class _FakeTaskStore:
    def __init__(self, tasks, dependencies=None) -> None:
        self.tasks = {task.id: task for task in tasks}
        self.dependency_rows = dependencies or []
        self.attempt_rows = {}

    def prioritized_ready_for_mission(self, *, tenant_id, mission_id, limit=50):
        ready = [
            task
            for task in self.tasks.values()
            if task.tenant_id == tenant_id
            and task.mission_id == mission_id
            and task.status == "ready"
            and self.dependencies_satisfied(tenant_id=tenant_id, task_id=task.id)
        ]
        return sorted(ready, key=lambda task: task.priority, reverse=True)[:limit]

    def ready_for_mission(self, *, tenant_id, mission_id, limit=50):
        return self.prioritized_ready_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=limit)

    def list_for_mission(self, *, tenant_id, mission_id, limit=250, status=None, owner_member_id=None):
        return [task for task in self.tasks.values() if task.tenant_id == tenant_id and task.mission_id == mission_id and (status is None or task.status == status)]

    def get(self, *, tenant_id, task_id):
        return self.tasks[task_id]

    def dependencies(self, *, tenant_id, task_id):
        return [row for row in self.dependency_rows if row.task_id == task_id]

    def dependencies_satisfied(self, *, tenant_id, task_id):
        deps = self.dependencies(tenant_id=tenant_id, task_id=task_id)
        return all(self.tasks[row.depends_on_task_id].status == "completed" for row in deps)

    def attempts(self, *, tenant_id, task_id):
        return list(reversed(self.attempt_rows.get(task_id, [])))

    def create_attempt(self, task, *, worker_id):
        attempt = SimpleNamespace(id=uuid.uuid4(), task_id=task.id, attempt_number=len(self.attempt_rows.get(task.id, [])) + 1, status="running")
        self.attempt_rows.setdefault(task.id, []).append(attempt)
        return attempt

    def finish_attempt(self, attempt, *, status, result=None, error=None):
        attempt.status = status
        attempt.result = result or {}
        attempt.error = error or {}


class _FakeRuntimeExecution:
    def __init__(self) -> None:
        self.leases = {}
        self.checkpoints = {}
        self.expired_count = 0

    def expire_stale_leases(self, *, tenant_id=None):
        return self.expired_count

    def acquire_lease(self, *, tenant_id, mission, task, worker_id, ttl_seconds=120):
        lease = SimpleNamespace(id=uuid.uuid4(), task_id=task.id, worker_id=worker_id, status="active", version_number=1)
        self.leases[lease.id] = lease
        task.status = "running"
        task.version_number += 1
        return lease

    def get_lease(self, *, tenant_id, lease_id):
        return self.leases[lease_id]

    def heartbeat(self, lease, *, ttl_seconds=120):
        lease.version_number += 1

    def create_checkpoint(self, **kwargs):
        checkpoint = SimpleNamespace(id=uuid.uuid4(), version_number=1, **kwargs)
        self.checkpoints.setdefault(kwargs["task_id"], []).append(checkpoint)
        return checkpoint

    def checkpoints_for_task(self, *, tenant_id, task_id, limit=50):
        return list(reversed(self.checkpoints.get(task_id, [])))[:limit]

    def complete_task(self, *, task, lease, outputs=None):
        task.status = "completed"
        task.output_contract = {**(task.output_contract or {}), "runtime_outputs": outputs or {}}
        task.version_number += 1
        lease.status = "released"

    def fail_task(self, *, task, lease, error):
        task.status = "failed"
        task.failure_reason = error
        task.version_number += 1
        lease.status = "released"


class _FakeEvents:
    def __init__(self) -> None:
        self.items = []

    def append(self, **kwargs):
        self.items.append(kwargs)


class _FakeMissions:
    def __init__(self, mission) -> None:
        self.mission = mission

    def get(self, *, tenant_id, mission_id):
        return self.mission


class _FakeQuery:
    def __init__(self, rows) -> None:
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, dependency_rows) -> None:
        self.dependency_rows = dependency_rows

    def query(self, model):
        return _FakeQuery(self.dependency_rows)


class _FakeUow:
    def __init__(self, mission, tasks, dependencies=None) -> None:
        self.missions = _FakeMissions(mission)
        self.tasks = _FakeTaskStore(tasks, dependencies)
        self.runtime_execution = _FakeRuntimeExecution()
        self.events = _FakeEvents()
        self.db = _FakeDb(dependencies or [])


def _task(*, tenant_id, mission_id, key, status="ready", priority=10, task_type="implementation", output_contract=None, input_contract=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        mission_id=mission_id,
        task_key=key,
        title=key,
        task_type=task_type,
        status=status,
        priority=priority,
        input_contract=input_contract or {},
        output_contract=output_contract or {},
        acceptance_criteria=["Evidence exists."],
        version_number=1,
        workflow_node_id=uuid.uuid4(),
        failure_reason=None,
        completed_at=None,
    )


def test_runtime_scheduler_uses_priority_ordering() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    mission = SimpleNamespace(id=mission_id, status="running")
    low = _task(tenant_id=tenant_id, mission_id=mission_id, key="low", priority=1)
    high = _task(tenant_id=tenant_id, mission_id=mission_id, key="high", priority=99)
    uow = _FakeUow(mission, [low, high])

    scheduled = RuntimeSchedulerService(uow).schedule(tenant_id=tenant_id, mission_id=mission_id, limit=2)

    assert [task.task_key for task in scheduled["ready_tasks"]] == ["high", "low"]


def test_runtime_worker_executes_task_and_unblocks_dependents() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    mission = SimpleNamespace(id=mission_id, status="running", active_workflow_id=uuid.uuid4(), version_number=1)
    first = _task(tenant_id=tenant_id, mission_id=mission_id, key="implementation.backend")
    dependent = _task(tenant_id=tenant_id, mission_id=mission_id, key="review.qa", status="pending")
    deps = [SimpleNamespace(task_id=dependent.id, depends_on_task_id=first.id)]
    uow = _FakeUow(mission, [first, dependent], deps)

    result = RuntimeTaskExecutor(uow).run_next(tenant_id=tenant_id, mission_id=mission_id, worker_id="worker-1")

    assert result["status"] == "completed"
    assert first.status == "completed"
    assert dependent.status == "ready"


def test_runtime_worker_blocks_dependents_when_verification_fails() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    mission = SimpleNamespace(id=mission_id, status="running", active_workflow_id=uuid.uuid4(), version_number=1)
    first = _task(
        tenant_id=tenant_id,
        mission_id=mission_id,
        key="implementation.backend",
        output_contract={"force_verification_status": "failed"},
    )
    dependent = _task(tenant_id=tenant_id, mission_id=mission_id, key="review.qa", status="pending")
    deps = [SimpleNamespace(task_id=dependent.id, depends_on_task_id=first.id)]
    uow = _FakeUow(mission, [first, dependent], deps)

    result = RuntimeTaskExecutor(uow).run_next(tenant_id=tenant_id, mission_id=mission_id, worker_id="worker-1")

    assert result["status"] == "failed"
    assert first.status == "failed"
    assert dependent.status == "blocked"


def test_runtime_worker_requeues_retryable_tool_failure_without_blocking_dependents() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    mission = SimpleNamespace(id=mission_id, status="running", active_workflow_id=uuid.uuid4(), version_number=1)
    first = _task(
        tenant_id=tenant_id,
        mission_id=mission_id,
        key="implementation.backend",
        input_contract={"force_tool_status": "failed"},
    )
    dependent = _task(tenant_id=tenant_id, mission_id=mission_id, key="review.qa", status="pending")
    deps = [SimpleNamespace(task_id=dependent.id, depends_on_task_id=first.id)]
    uow = _FakeUow(mission, [first, dependent], deps)

    result = RuntimeTaskExecutor(uow).run_next(tenant_id=tenant_id, mission_id=mission_id, worker_id="worker-1")

    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert first.status == "ready"
    assert dependent.status == "pending"
