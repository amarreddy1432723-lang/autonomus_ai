from uuid import UUID, uuid4

import pytest

from services.shared.database import Base, SessionLocal, engine, verify_default_user
from services.shared.models import AgentInstance, EvidenceRecord, ExecutionPlan, IntelligenceTask, TaskRequirement


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("ALLOW_DEMO_USER", "true")
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    verify_default_user(session)
    try:
        yield session
    finally:
        session.rollback()
        tasks = session.query(IntelligenceTask).filter(IntelligenceTask.title.like("intelligence-control-plane-test%")).all()
        task_ids = [task.id for task in tasks]
        if task_ids:
            session.query(IntelligenceTask).filter(IntelligenceTask.id.in_(task_ids)).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_intelligence_task_lifecycle_records_plan_evidence_and_timeline(db):
    from services.agent.intelligence.schemas import ApprovalRequest, EvidenceCreate, IntelligenceTaskCreate, WorkerAssignmentRequest
    from services.agent.intelligence_routes import (
        add_intelligence_evidence,
        analyze_intelligence_task,
        assign_intelligence_workers,
        approve_intelligence_plan,
        create_intelligence_task,
        get_intelligence_timeline,
        get_task_workflow,
        mark_intelligence_task_ready,
        plan_intelligence_task,
    )

    unique = uuid4()
    created = create_intelligence_task(
        IntelligenceTaskCreate(
            title=f"intelligence-control-plane-test {unique}",
            raw_request="Analyze the workspace, plan the safe implementation, verify with tests, and prepare founder approval before deploy.",
        ),
        user_id=USER_ID,
        db=db,
    )
    task_id = UUID(created["task"]["id"])

    analyzed = analyze_intelligence_task(task_id, user_id=USER_ID, db=db)
    assert analyzed["task"]["status"] == "analyzed"
    assert analyzed["task"]["requirements"]
    assert analyzed["task"]["risk_level"] in {"medium", "high", "critical"}

    planned = plan_intelligence_task(task_id, user_id=USER_ID, db=db)
    assert planned["task"]["status"] == "planned"
    assert planned["task"]["plans"][0]["steps"]

    approved = approve_intelligence_plan(task_id, ApprovalRequest(notes="Approved for controlled execution."), user_id=USER_ID, db=db)
    assert approved["task"]["status"] == "plan_approved"
    assert approved["task"]["plans"][0]["status"] == "approved"
    assert approved["task"]["founder_approvals"]
    assert approved["task"]["workflow"]["current_phase"]["key"] == "ai_workforce"

    workers = assign_intelligence_workers(task_id, WorkerAssignmentRequest(preference="balanced"), user_id=USER_ID, db=db)
    roles = {item["role"] for item in workers["agents"]}
    assert workers["execution_enabled"] is False
    assert "engineering_manager" in roles
    assert "qa_engineer" in roles
    assert workers["task"]["metadata"]["worker_assignment_count"] == len(workers["agents"])
    assert all(item["model_name"] for item in workers["agents"])

    evidence = add_intelligence_evidence(
        task_id,
        EvidenceCreate(evidence_type="inspection", title="Files inspected", summary="No model execution happened in phase 1."),
        user_id=USER_ID,
        db=db,
    )
    assert evidence["evidence_id"]
    assert evidence["task"]["evidence"][0]["title"] == "Files inspected"

    handoff = mark_intelligence_task_ready(task_id, user_id=USER_ID, db=db)
    assert handoff["task"]["status"] == "ready_for_execution"
    assert handoff["execution_enabled"] is False
    workflow = get_task_workflow(task_id, user_id=USER_ID, db=db)
    assert workflow["workflow"]["current_phase"]["key"] == "context_building"
    assert len(workflow["agents"]) == len(workers["agents"])

    timeline = get_intelligence_timeline(task_id, user_id=USER_ID, db=db)
    event_types = [item["event_type"] for item in timeline["timeline"]]
    assert "intelligence.task.created" in event_types
    assert "intelligence.task.analyzed" in event_types
    assert "intelligence.task.planned" in event_types
    assert "intelligence.plan.approved" in event_types
    assert "intelligence.workforce.assigned" in event_types
    assert "intelligence.evidence.added" in event_types
    assert "intelligence.task.execution_ready" in event_types

    assert db.query(TaskRequirement).filter(TaskRequirement.task_id == task_id).count() >= 1
    assert db.query(ExecutionPlan).filter(ExecutionPlan.task_id == task_id).count() == 1
    assert db.query(AgentInstance).filter(AgentInstance.task_id == task_id).count() == len(workers["agents"])
    assert db.query(EvidenceRecord).filter(EvidenceRecord.task_id == task_id).count() == 1
