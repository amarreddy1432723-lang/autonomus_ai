import os
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from services.agent.arceus_runtime.application.idempotency import calculate_request_hash
from services.agent.arceus_runtime.application.unit_of_work import SqlAlchemyUnitOfWork
from services.agent.arceus_runtime.planning.builder import build_organization_proposals, choose_roles, plan_tasks, validate_plan
from services.agent.arceus_runtime.planning.contracts import PlanMissionCommand
from services.agent.arceus_runtime.planning.service import PlanMissionService
from services.shared.arceus_core_models import (
    ArceusApproval,
    ArceusArtifact,
    ArceusArtifactVersion,
    ArceusAuditEvent,
    ArceusEvent,
    ArceusIdempotencyRecord,
    ArceusMission,
    ArceusMissionOrganization,
    ArceusMissionRequiredCapability,
    ArceusMissionVersion,
    ArceusOrganizationMember,
    ArceusOutboxMessage,
    ArceusProject,
    ArceusTask,
    ArceusTaskDependency,
    ArceusTenant,
    ArceusUser,
    ArceusWorkflowDefinition,
    ArceusWorkflowEdge,
    ArceusWorkflowNode,
)
from services.shared.database import SessionLocal


def test_organization_builder_assigns_independent_reviewers_for_auth_mission() -> None:
    members, gaps = choose_roles(
        [
            "authentication_review",
            "authorization_review",
            "fastapi_development",
            "react_development",
            "integration_testing",
        ],
        "high",
    )
    roles = {member.role_key: member for member in members}

    assert gaps == []
    assert "backend_engineer" in roles
    assert "frontend_engineer" in roles
    assert "qa_reviewer" in roles
    assert "security_reviewer" in roles
    assert roles["backend_engineer"].can_implement is True
    assert roles["backend_engineer"].can_review is False
    assert roles["security_reviewer"].can_review is True
    assert roles["security_reviewer"].can_implement is False
    assert roles["human_approver"].can_approve is True


def test_organization_builder_flags_unmatched_capability_gap() -> None:
    members, gaps = choose_roles(["quantum_telemetry"], "medium")

    assert "quantum_telemetry" in gaps
    assert any(member.role_key == "human_approver" for member in members)


def test_workflow_planner_generates_acyclic_covered_tasks() -> None:
    requirements = ["Support Google login.", "Show login status in the desktop shell."]
    capabilities = ["authentication_review", "fastapi_development", "react_development", "integration_testing"]
    members, _gaps = choose_roles(capabilities, "high")
    tasks = plan_tasks(requirements, capabilities, "high")
    validation = validate_plan(members, tasks, requirements)

    assert validation["valid"] is True
    assert validation["critical_path"][0] == "analysis.repository"
    assert validation["critical_path"][-1] == "approval.human_plan"
    assert all(validation["requirement_coverage"].values())
    assert any(task.task_key == "review.qa" for task in tasks)
    assert any(task.task_key == "review.security" for task in tasks)
    assert sum(task.estimated_cost_usd for task in tasks) > 0
    assert sum(task.estimated_tokens for task in tasks) > 0


def test_workflow_validation_rejects_missing_owner() -> None:
    members, _gaps = choose_roles(["requirement_analysis"], "medium")
    tasks = plan_tasks(["Write docs."], ["requirement_analysis"], "medium")
    broken = [task for task in tasks if task.task_key != "approval.human_plan"]
    approval = next(task for task in tasks if task.task_key == "approval.human_plan")
    broken.append(
        type(approval)(
            **{
                **approval.__dict__,
                "owner_role_key": "missing_owner",
            }
        )
    )

    validation = validate_plan(members, broken, ["Write docs."])

    assert validation["valid"] is False
    assert any("no valid owner" in error for error in validation["errors"])


def test_organization_builder_generates_ranked_proposal_variants() -> None:
    requirements = ["Protect admin APIs.", "Show authenticated account state."]
    capabilities = ["authentication_review", "authorization_review", "fastapi_development", "react_development"]

    proposals = build_organization_proposals(requirements, capabilities, "high")

    assert [proposal.proposal_key for proposal in proposals]
    assert {proposal.proposal_key for proposal in proposals} == {"lean", "balanced", "assurance"}
    assert proposals[0].metrics["recommendation_score"] >= proposals[-1].metrics["recommendation_score"]
    assert all(proposal.members for proposal in proposals)
    assert all(proposal.tasks for proposal in proposals)


def test_specialist_scoring_uses_historical_quality_speed_and_cost() -> None:
    members, _gaps = choose_roles(
        ["fastapi_development", "api_design"],
        "medium",
        performance_history={"backend_engineer": {"quality": 0.99, "speed": 0.98, "cost_efficiency": 0.97}},
    )
    backend = next(member for member in members if member.role_key == "backend_engineer")

    assert backend.score > 0.9
    assert "historical quality" in backend.score_reason


def test_plan_service_persists_versioned_workflow_with_real_db() -> None:
    if os.getenv("ARCEUS_RUNTIME_DB_TESTS") != "1":
        pytest.skip("Set ARCEUS_RUNTIME_DB_TESTS=1 to run the real Postgres planning workflow test.")

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    mission_version_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.add(ArceusTenant(id=tenant_id, name="Planning Test Tenant", slug=f"planning-test-{tenant_id}", status="active"))
        db.add(
            ArceusUser(
                id=user_id,
                external_identity_id=f"planning-test-{user_id}",
                email=f"planning-test-{user_id}@example.com",
                display_name="Planning Test User",
                status="active",
            )
        )
        db.add(
            ArceusProject(
                id=project_id,
                tenant_id=tenant_id,
                name="Planning Test Project",
                slug=f"planning-test-{project_id}",
                status="active",
                created_by=user_id,
            )
        )
        db.add(
            ArceusMission(
                id=mission_id,
                tenant_id=tenant_id,
                project_id=project_id,
                created_by=user_id,
                title="Planning DB Mission",
                objective="Add authenticated admin readiness.",
                status="compiled",
                risk_level="high",
                version_number=1,
                current_version_id=mission_version_id,
            )
        )
        db.add(
            ArceusMissionVersion(
                id=mission_version_id,
                tenant_id=tenant_id,
                mission_id=mission_id,
                version=1,
                compiled_by=user_id,
                objective_snapshot="Add authenticated admin readiness.",
                mission_contract={
                    "requirements": ["Protect admin APIs.", "Show service readiness."],
                    "required_capabilities": ["fastapi_development", "authentication_review", "build_verification"],
                },
                intent_frame={"primary_intent": "authentication_change"},
                risk_profile={"risk_level": "high"},
                execution_graph={},
                source_hash=f"planning-test-{mission_id}",
            )
        )
        db.commit()

        command = PlanMissionCommand(
            tenant_id=tenant_id,
            mission_id=mission_id,
            expected_version=1,
            actor_id=user_id,
            idempotency_key=f"planning-test-{mission_id}",
            request_hash=calculate_request_hash("mission.plan", {"mission_id": str(mission_id), "expected_version": 1}),
            correlation_id=mission_id,
        )
        result = PlanMissionService(SqlAlchemyUnitOfWork(db)).plan(command)

        workflow = db.query(ArceusWorkflowDefinition).filter(ArceusWorkflowDefinition.id == result.workflow_id).one()
        assert result.status == "awaiting_plan_approval"
        assert workflow.metadata_json["workflow_version"] == 1
        assert workflow.metadata_json["proposal_count"] == 3
        assert workflow.metadata_json["metrics"]["estimated_tokens"] > 0
    except OperationalError as exc:
        pytest.skip(f"Real DB planning workflow test skipped because the configured database is unavailable: {exc}")
    finally:
        db.rollback()
        try:
            db.query(ArceusTaskDependency).filter(ArceusTaskDependency.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusWorkflowEdge).filter(ArceusWorkflowEdge.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusWorkflowNode).filter(ArceusWorkflowNode.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusWorkflowDefinition).filter(ArceusWorkflowDefinition.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusOrganizationMember).filter(ArceusOrganizationMember.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusMissionOrganization).filter(ArceusMissionOrganization.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusMissionRequiredCapability).filter(ArceusMissionRequiredCapability.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusApproval).filter(ArceusApproval.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusArtifactVersion).filter(ArceusArtifactVersion.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusArtifact).filter(ArceusArtifact.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusOutboxMessage).filter(ArceusOutboxMessage.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusEvent).filter(ArceusEvent.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusAuditEvent).filter(ArceusAuditEvent.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusIdempotencyRecord).filter(ArceusIdempotencyRecord.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusMissionVersion).filter(ArceusMissionVersion.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusProject).filter(ArceusProject.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusTenant).filter(ArceusTenant.id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusUser).filter(ArceusUser.id == user_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
