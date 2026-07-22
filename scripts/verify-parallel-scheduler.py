from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

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


def _create_task(db, tenant_id, mission_id, key: str, task_type: str, input_contract: dict) -> ArceusTask:
    task = ArceusTask(
        tenant_id=tenant_id,
        mission_id=mission_id,
        task_key=key,
        title=key.replace("_", " ").title(),
        task_type=task_type,
        status="ready",
        input_contract=input_contract,
        output_contract={},
        acceptance_criteria=[],
    )
    db.add(task)
    db.flush()
    return task


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_id = uuid.uuid4().hex[:12]
    correlation_id = uuid.uuid4()
    checks: list[dict] = []
    with SessionLocal() as db:
        tenant = ArceusTenant(name=f"Scheduler Proof {run_id}", slug=f"scheduler-proof-{run_id}", status="active", plan_key="pro")
        user = ArceusUser(external_identity_id=f"scheduler-proof-{run_id}", email=f"scheduler-{run_id}@example.test", display_name="Scheduler Proof")
        db.add_all([tenant, user])
        db.flush()
        project = ArceusProject(tenant_id=tenant.id, name="Parallel Scheduler Proof", slug=f"parallel-scheduler-{run_id}", created_by=user.id)
        db.add(project)
        db.flush()
        repository = ArceusProjectRepository(
            tenant_id=tenant.id,
            project_id=project.id,
            provider="local",
            repository_url=f"file:///scheduler-proof/{run_id}",
            default_branch="main",
            status="active",
        )
        db.add(repository)
        db.flush()
        mission = ArceusMission(
            tenant_id=tenant.id,
            project_id=project.id,
            created_by=user.id,
            title="Parallel scheduler proof",
            objective="Verify durable parallel scheduling, path reservations, capacity, and idempotency.",
            status="running",
            metadata_json={"scheduler_limits": {"total": 4, "read_only": 2, "write_sensitive": 2}},
        )
        db.add(mission)
        db.flush()
        read_a = _create_task(db, tenant.id, mission.id, "read_repo_a", "analysis", {"repository_id": str(repository.id)})
        read_b = _create_task(db, tenant.id, mission.id, "read_repo_b", "analysis", {"repository_id": str(repository.id)})
        read_c = _create_task(db, tenant.id, mission.id, "read_repo_c", "analysis", {"repository_id": str(repository.id)})
        write_a = _create_task(
            db,
            tenant.id,
            mission.id,
            "write_summary_a",
            "implementation",
            {"repository_id": str(repository.id), "write_paths": ["PROJECT_SUMMARY.md"], "required_capabilities": {"filesystem_write": True}},
        )
        write_b = _create_task(
            db,
            tenant.id,
            mission.id,
            "write_summary_b",
            "implementation",
            {"repository_id": str(repository.id), "write_paths": ["./PROJECT_SUMMARY.md"], "required_capabilities": {"filesystem_write": True}},
        )
        db.commit()

        first = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=correlation_id, max_assignments=5)
        db.commit()
        assigned_keys = {assignment.task_key for assignment in first.assignments}
        waiting_by_key = {waiting.task_key: waiting.reason for waiting in first.waiting}
        checks.append(_ok("Multiple independent tasks assigned", len(first.assignments) == 3, f"assigned={sorted(assigned_keys)}"))
        read_wait_count = sum(1 for key, reason in waiting_by_key.items() if key.startswith("read_repo_") and reason == "capacity")
        checks.append(_ok("Read-only capacity enforced", read_wait_count == 1, f"waiting={waiting_by_key}"))
        conflicted_write_key = write_a.task_key if waiting_by_key.get(write_a.task_key) == "path_conflict" else write_b.task_key
        checks.append(_ok("Conflicting write waits", waiting_by_key.get(conflicted_write_key) == "path_conflict", f"waiting={waiting_by_key}"))
        checks.append(_ok("Write path reserved", "PROJECT_SUMMARY.md" in first.path_reservations, json.dumps(first.path_reservations, sort_keys=True)))
        checks.append(_ok("Workers persisted", db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant.id, ArceusAgentRuntimeWorker.current_mission_id == mission.id).count() >= 6, "bootstrap workers available"))
        checks.append(_ok("Assignments persisted", db.query(ArceusMissionTaskAssignment).filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.mission_id == mission.id, ArceusMissionTaskAssignment.status == "assigned").count() == 3, "three assigned records"))
        checks.append(_ok("Reservations persisted", db.query(ArceusMissionPathReservation).filter(ArceusMissionPathReservation.tenant_id == tenant.id, ArceusMissionPathReservation.mission_id == mission.id, ArceusMissionPathReservation.status == "active").count() == 1, "one active reservation"))

        second = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=uuid.uuid4(), max_assignments=5)
        db.commit()
        assignment_count_after_duplicate = db.query(ArceusMissionTaskAssignment).filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.mission_id == mission.id).count()
        checks.append(_ok("Duplicate schedule creates no duplicate assignments", len(second.assignments) == 0 and assignment_count_after_duplicate == 3, f"new={len(second.assignments)} total={assignment_count_after_duplicate}"))

        assigned_write_task_id = write_a.id if write_a.task_key in assigned_keys else write_b.id
        waiting_write_task_key = write_b.task_key if assigned_write_task_id == write_a.id else write_a.task_key
        write_assignment = (
            db.query(ArceusMissionTaskAssignment)
            .filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.task_id == assigned_write_task_id, ArceusMissionTaskAssignment.status == "assigned")
            .first()
        )
        if write_assignment:
            write_assignment.status = "released"
            write_assignment.released_at = write_assignment.released_at or write_assignment.assigned_at
            completed_write_task = db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant.id, ArceusTask.id == write_assignment.task_id).first()
            if completed_write_task:
                completed_write_task.status = "completed"
            worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant.id, ArceusAgentRuntimeWorker.id == write_assignment.worker_id).first()
            if worker:
                worker.status = "idle"
                worker.current_task_id = None
            for reservation in db.query(ArceusMissionPathReservation).filter(ArceusMissionPathReservation.tenant_id == tenant.id, ArceusMissionPathReservation.assignment_id == write_assignment.id, ArceusMissionPathReservation.status == "active").all():
                reservation.status = "released"
        db.commit()
        third = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=uuid.uuid4(), max_assignments=5)
        db.commit()
        checks.append(_ok("Released reservation unlocks waiting write", any(assignment.task_key == waiting_write_task_key for assignment in third.assignments), f"assigned={[(item.task_key, item.reserved_paths) for item in third.assignments]}"))

        for assignment in db.query(ArceusMissionTaskAssignment).filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.mission_id == mission.id, ArceusMissionTaskAssignment.status.in_(["assigned", "accepted", "running"])).all():
            assignment.status = "released"
            worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant.id, ArceusAgentRuntimeWorker.id == assignment.worker_id).first()
            if worker:
                worker.status = "idle"
                worker.current_task_id = None
        for reservation in db.query(ArceusMissionPathReservation).filter(ArceusMissionPathReservation.tenant_id == tenant.id, ArceusMissionPathReservation.mission_id == mission.id, ArceusMissionPathReservation.status == "active").all():
            reservation.status = "released"
        db.commit()
        final_active_reservations = db.query(ArceusMissionPathReservation).filter(ArceusMissionPathReservation.tenant_id == tenant.id, ArceusMissionPathReservation.mission_id == mission.id, ArceusMissionPathReservation.status == "active").count()
        checks.append(_ok("Final reservations released", final_active_reservations == 0, f"active={final_active_reservations}"))

    result = {"ok": all(check["ok"] for check in checks), "checks": checks}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
