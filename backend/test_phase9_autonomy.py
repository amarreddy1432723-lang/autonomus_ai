from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.agent.autonomy import assess_autonomy_decision, run_autonomous_cycle
from services.agent.main import app as agent_app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Approval, Task, TaskExecution, UserProfile


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    profile = session.query(UserProfile).filter(UserProfile.user_id == USER_ID).first()
    profile.autonomy_level = "partner"
    profile.trust_rules = []
    task_ids = [row[0] for row in session.query(Task.id).filter(Task.user_id == USER_ID, Task.title.like("Phase9 test%")).all()]
    if task_ids:
        session.query(TaskExecution).filter(TaskExecution.task_id.in_(task_ids)).delete(synchronize_session=False)
        session.query(Approval).filter(Approval.task_id.in_(task_ids)).delete(synchronize_session=False)
        session.query(Task).filter(Task.id.in_(task_ids)).delete(synchronize_session=False)
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        task_ids = [row[0] for row in session.query(Task.id).filter(Task.user_id == USER_ID, Task.title.like("Phase9 test%")).all()]
        if task_ids:
            session.query(TaskExecution).filter(TaskExecution.task_id.in_(task_ids)).delete(synchronize_session=False)
            session.query(Approval).filter(Approval.task_id.in_(task_ids)).delete(synchronize_session=False)
            session.query(Task).filter(Task.id.in_(task_ids)).delete(synchronize_session=False)
        profile = session.query(UserProfile).filter(UserProfile.user_id == USER_ID).first()
        if profile:
            profile.autonomy_level = "observer"
        session.commit()
        session.close()


def _task(db, title: str, description: str, priority: float = 0.9) -> Task:
    task = Task(
        user_id=USER_ID,
        title=title,
        description=description,
        status="queued",
        priority_score=priority,
        assigned_agent="CodingAgent",
        est_hours_pert=1.0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_assessor_requires_approval_for_hard_trigger(db):
    task = _task(db, "Phase9 test send external email", "Send email external recipient with project update.")

    decision = assess_autonomy_decision(db, USER_ID, task)

    assert decision.requires_approval is True
    assert decision.risk_level == "high"
    assert decision.decision == "approval_required"
    assert "Hard approval trigger" in decision.reasoning


def test_autonomous_cycle_executes_safe_internal_task(db):
    task = _task(db, "Phase9 test store memory", "Update task status and store an internal memory note.")

    result = run_autonomous_cycle(db, USER_ID, max_tasks=1)
    db.refresh(task)

    assert result["executed"] == 1
    assert result["approval_required"] == 0
    assert task.status == "done"
    execution = db.query(TaskExecution).filter(TaskExecution.task_id == task.id).one()
    assert execution.user_id == USER_ID
    assert execution.status == "completed"


def test_autonomous_cycle_requests_approval_for_risky_task(db):
    task = _task(db, "Phase9 test delete production data", "Delete database rows in production.")

    result = run_autonomous_cycle(db, USER_ID, max_tasks=1)
    db.refresh(task)

    assert result["executed"] == 0
    assert result["approval_required"] == 1
    assert task.status == "waiting_approval"
    approval = db.query(Approval).filter(Approval.task_id == task.id).one()
    assert approval.status == "pending"
    assert approval.risk_level == "high"
    assert approval.risk_reasoning


def test_autonomy_dry_run_does_not_mutate_task_or_create_approval(db):
    task = _task(db, "Phase9 test send message", "Send message to another person.")

    result = run_autonomous_cycle(db, USER_ID, max_tasks=1, dry_run=True)
    db.refresh(task)

    assert result["dry_run"] is True
    assert result["results"][0]["action"] == "dry_run_only"
    assert task.status == "queued"
    assert db.query(Approval).filter(Approval.task_id == task.id).count() == 0


def test_autonomy_status_and_level_api(db):
    client = TestClient(agent_app)
    headers = {"x-user-id": str(USER_ID)}

    level_response = client.patch(
        "/api/v1/agents/autonomy/level",
        headers=headers,
        json={"autonomy_level": "assistant"},
    )
    assert level_response.status_code == 200, level_response.text
    assert level_response.json()["autonomy_level"] == "assistant"

    _task(db, "Phase9 test status queued task", "Research a local internal idea.")
    status_response = client.get("/api/v1/agents/autonomy/status", headers=headers)

    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["autonomy_level"] == "assistant"
    assert status["queued_tasks"] >= 1
    assert status["guardrails"]["safe_default"] == "reject_on_timeout"


def test_chat_stream_does_not_expose_internal_intent_classifier():
    client = TestClient(agent_app)
    response = client.post(
        "/api/v1/agents/chat",
        headers={"x-user-id": str(USER_ID)},
        json={
            "user_id": str(USER_ID),
            "session_id": "phase9-chat-stream",
            "messages": [
                {
                    "role": "user",
                    "content": "Give me a short status summary of my personal AI OS roadmap.",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert '{"intent"' not in response.text
    assert '"status": "completed"' in response.text
