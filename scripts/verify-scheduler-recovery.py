from __future__ import annotations

import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.agent.task_runtime.dispatcher import utc_now  # noqa: E402
from services.agent.task_runtime.scheduler import schedule_ready_tasks  # noqa: E402
from services.shared.arceus_core_models import (  # noqa: E402
    ArceusAgentRuntimeWorker,
    ArceusMission,
    ArceusMissionPathReservation,
    ArceusMissionTaskAssignment,
    ArceusProject,
    ArceusProjectRepository,
    ArceusTask,
    ArceusTenant,
    ArceusUser,
)
from services.shared.database import Base, SessionLocal, engine  # noqa: E402


def _ok(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_id = uuid.uuid4().hex[:12]
    correlation_id = uuid.uuid4()
    checks: list[dict] = []

    with SessionLocal() as db:
        tenant = ArceusTenant(name=f"Scheduler Recovery {run_id}", slug=f"scheduler-recovery-{run_id}", status="active", plan_key="pro")
        user = ArceusUser(external_identity_id=f"scheduler-recovery-{run_id}", email=f"scheduler-recovery-{run_id}@example.test", display_name="Scheduler Recovery")
        db.add_all([tenant, user])
        db.flush()

        project = ArceusProject(tenant_id=tenant.id, name="Scheduler Recovery Proof", slug=f"scheduler-recovery-{run_id}", created_by=user.id)
        db.add(project)
        db.flush()
        repository = ArceusProjectRepository(
            tenant_id=tenant.id,
            project_id=project.id,
            provider="local",
            repository_url=f"file:///scheduler-recovery/{run_id}",
            default_branch="main",
            status="active",
        )
        db.add(repository)
        db.flush()

        mission = ArceusMission(
            tenant_id=tenant.id,
            project_id=project.id,
            created_by=user.id,
            title="Scheduler recovery proof",
            objective="Verify accepted assignment crash recovery, path release, and task requeue.",
            status="running",
            metadata_json={"scheduler_limits": {"total": 1, "write_sensitive": 1}},
        )
        db.add(mission)
        db.flush()

        task = ArceusTask(
            tenant_id=tenant.id,
            mission_id=mission.id,
            task_key="write_recovery_summary",
            title="Write recovery summary",
            task_type="implementation",
            status="ready",
            input_contract={"repository_id": str(repository.id), "write_paths": ["RECOVERY.md"], "required_capabilities": {"filesystem_write": True}},
            output_contract={},
            acceptance_criteria=[],
        )
        db.add(task)
        db.commit()

        first = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=correlation_id, max_assignments=1)
        db.commit()
        checks.append(_ok("Initial write assigned", len(first.assignments) == 1 and first.assignments[0].task_key == task.task_key, f"assignments={[(item.task_key, item.execution_class) for item in first.assignments]}"))

        assignment = (
            db.query(ArceusMissionTaskAssignment)
            .filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.task_id == task.id, ArceusMissionTaskAssignment.status == "assigned")
            .first()
        )
        if assignment is None:
            checks.append(_ok("Accepted assignment prepared", False, "missing assignment"))
        else:
            worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant.id, ArceusAgentRuntimeWorker.id == assignment.worker_id).first()
            now = utc_now()
            assignment.status = "accepted"
            assignment.started_at = now - timedelta(minutes=5)
            assignment.lease_expires_at = now - timedelta(seconds=1)
            assignment.last_heartbeat_at = now - timedelta(minutes=5)
            assignment.version_number = int(assignment.version_number or 1) + 1
            task.status = "running"
            task.version_number = int(task.version_number or 1) + 1
            if worker is not None:
                worker.status = "busy"
                worker.current_task_id = task.id
                worker.last_heartbeat_at = now - timedelta(minutes=5)
                worker.version_number = int(worker.version_number or 1) + 1
            db.commit()
            checks.append(_ok("Accepted assignment prepared", True, f"assignment={assignment.id}"))

        recovery = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=uuid.uuid4(), max_assignments=0)
        db.commit()

        expired_assignment = (
            db.query(ArceusMissionTaskAssignment)
            .filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.task_id == task.id, ArceusMissionTaskAssignment.status == "expired")
            .first()
        )
        db.refresh(task)
        active_reservations = (
            db.query(ArceusMissionPathReservation)
            .filter(ArceusMissionPathReservation.tenant_id == tenant.id, ArceusMissionPathReservation.mission_id == mission.id, ArceusMissionPathReservation.status == "active")
            .count()
        )
        active_assignments = (
            db.query(ArceusMissionTaskAssignment)
            .filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.mission_id == mission.id, ArceusMissionTaskAssignment.status.in_(["assigned", "accepted", "running"]))
            .count()
        )
        busy_workers = (
            db.query(ArceusAgentRuntimeWorker)
            .filter(ArceusAgentRuntimeWorker.tenant_id == tenant.id, ArceusAgentRuntimeWorker.current_mission_id == mission.id, ArceusAgentRuntimeWorker.status != "idle")
            .count()
        )
        checks.append(_ok("Expired accepted assignment recovered", expired_assignment is not None, f"expired_assignment={expired_assignment.id if expired_assignment else None}"))
        checks.append(_ok("Running task requeued", task.status == "ready", f"task_status={task.status}"))
        checks.append(_ok("Path reservation released on recovery", active_reservations == 0, f"active_reservations={active_reservations}"))
        checks.append(_ok("Worker freed on recovery", busy_workers == 0, f"busy_workers={busy_workers}"))
        checks.append(_ok("No active assignments after recovery-only pass", active_assignments == 0 and not recovery.assignments, f"active={active_assignments}; scheduled={len(recovery.assignments)}"))

        rescheduled = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=uuid.uuid4(), max_assignments=1)
        db.commit()
        checks.append(_ok("Recovered task can be rescheduled", any(item.task_key == task.task_key for item in rescheduled.assignments), f"assignments={[(item.task_key, item.execution_class) for item in rescheduled.assignments]}"))

    result = {"ok": all(check["ok"] for check in checks), "checks": checks}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
