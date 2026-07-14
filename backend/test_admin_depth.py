from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import AgentJob, AuditLog, CodeSession


ADMIN_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("NEXUS_ADMIN_USER_IDS", str(ADMIN_ID))
    session = SessionLocal()
    verify_default_user(session)
    session.query(AgentJob).filter(AgentJob.prompt.like("admin-depth-test%")).delete()
    session.query(CodeSession).filter(CodeSession.title.like("admin-depth-test%")).delete()
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.query(AgentJob).filter(AgentJob.prompt.like("admin-depth-test%")).delete()
        session.query(CodeSession).filter(CodeSession.title.like("admin-depth-test%")).delete()
        session.commit()
        session.close()


def test_admin_can_retry_failed_background_job(db):
    from services.agent.routes_admin import retry_admin_job

    code_session = CodeSession(
        user_id=ADMIN_ID,
        title="admin-depth-test session",
        file_ids=[],
        status="active",
    )
    db.add(code_session)
    db.commit()
    db.refresh(code_session)

    job = AgentJob(
        user_id=ADMIN_ID,
        code_session_id=code_session.id,
        mode="background_code",
        prompt="admin-depth-test retry",
        status="failed",
        metadata_json={"retry_count": 0},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = retry_admin_job(job.id, user_id=ADMIN_ID, db=db)
    db.refresh(job)

    assert result["previous_status"] == "failed"
    assert result["job"]["status"] == "retrying"
    assert job.status == "retrying"
    assert (job.metadata_json or {}).get("retry_count") == 1
    assert db.query(AuditLog).filter(AuditLog.event_type == "admin.job.retry", AuditLog.entity_id == job.id).count() == 1


def test_admin_jobs_include_action_and_stale_metadata(db):
    from services.agent.routes_admin import get_admin_jobs

    stale_session = CodeSession(
        user_id=ADMIN_ID,
        title="admin-depth-test stale session",
        file_ids=[],
        status="active",
    )
    db.add(stale_session)
    db.commit()
    db.refresh(stale_session)

    stale_job = AgentJob(
        user_id=ADMIN_ID,
        code_session_id=stale_session.id,
        mode="background_code",
        prompt="admin-depth-test stale prompt",
        status="running",
        approval_state="approved",
        logs=[{"message": "still running"}],
        metadata_json={"retry_count": 2, "worker_id": "worker-a"},
    )
    failed_job = AgentJob(
        user_id=ADMIN_ID,
        code_session_id=stale_session.id,
        mode="background_code",
        prompt="admin-depth-test failed prompt",
        status="failed",
        result={"error": "model provider failed"},
    )
    db.add_all([stale_job, failed_job])
    db.commit()
    stale_job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=12)
    db.commit()

    result = get_admin_jobs(limit=100, user_id=ADMIN_ID, db=db)
    jobs = {item["id"]: item for item in result["jobs"]}

    assert result["summary"]["stale"] >= 1
    assert jobs[str(stale_job.id)]["stale"] is True
    assert jobs[str(stale_job.id)]["can_kill"] is True
    assert jobs[str(stale_job.id)]["retry_count"] == 2
    assert jobs[str(failed_job.id)]["can_retry"] is True
    assert jobs[str(failed_job.id)]["last_error"] == "model provider failed"


def test_admin_audit_detail_returns_full_context(db):
    from services.agent.routes_admin import get_admin_audit_log_detail

    audit = AuditLog(
        user_id=ADMIN_ID,
        event_type=f"admin.depth.audit.{uuid4()}",
        entity_type="agent_job",
        actor_type="admin",
        actor_id=str(ADMIN_ID),
        action="Inspect admin detail",
        old_value={"status": "failed"},
        new_value={"status": "retrying"},
        metadata_json={"reason": "test"},
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    result = get_admin_audit_log_detail(audit.id, user_id=ADMIN_ID, db=db)
    detail = result["audit_log"]

    assert detail["id"] == audit.id
    assert detail["event_type"].startswith("admin.depth.audit.")
    assert detail["actor_type"] == "admin"
    assert detail["old_value"] == {"status": "failed"}
    assert detail["new_value"] == {"status": "retrying"}
    assert detail["metadata"] == {"reason": "test"}


def test_admin_audit_log_filters_include_actor_entity_and_dates(db):
    from services.agent.routes_admin import get_admin_audit_logs

    unique = uuid4()
    target = AuditLog(
        user_id=ADMIN_ID,
        event_type=f"admin.depth.filter.{unique}",
        entity_type="agent_job",
        entity_id=unique,
        actor_type="admin",
        actor_id=str(ADMIN_ID),
        action="Filtered admin event",
        metadata_json={"match": True},
        occurred_at=datetime.now(timezone.utc),
    )
    other = AuditLog(
        user_id=ADMIN_ID,
        event_type=f"admin.depth.filter.other.{unique}",
        entity_type="code_session",
        actor_type="agent",
        actor_id="worker",
        action="Other admin event",
        metadata_json={"match": False},
        occurred_at=datetime.now(timezone.utc),
    )
    db.add_all([target, other])
    db.commit()

    result = get_admin_audit_logs(
        event_type=target.event_type,
        entity_type="agent_job",
        entity_id=unique,
        actor_type="admin",
        date_from=datetime.now(timezone.utc) - timedelta(minutes=5),
        limit=100,
        user_id=ADMIN_ID,
        db=db,
    )

    assert result["filters"]["entity_id"] == str(unique)
    assert result["filters"]["actor_type"] == "admin"
    assert [item["id"] for item in result["audit_logs"]] == [target.id]
