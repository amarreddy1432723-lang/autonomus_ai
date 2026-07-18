import pytest

from services.agent.os_kernel.artifacts import Evidence, MissionArtifact
from services.agent.os_kernel.decisions import DecisionOption, DecisionReview, MissionDecision
from services.agent.os_kernel.gateways import ModelExecutionMetric, ToolDefinition, ToolExecution
from services.agent.os_kernel.messages import MessageBus, SpecialistMessage
from services.agent.os_kernel.missions import OSMission
from services.agent.os_kernel.specialists import generation_one_specialists
from services.agent.os_kernel.tasks import MissionTask, TaskReview


def test_generation_one_specialists_are_capability_profiles_not_models():
    specialists = generation_one_specialists()
    roles = {profile.role for profile in specialists}

    assert roles == {"product_analyst", "solution_architect", "implementation_engineer", "security_reviewer", "qa_reviewer"}
    assert all("model" not in profile.to_dict() for profile in specialists)
    implementation = next(profile for profile in specialists if profile.role == "implementation_engineer")
    assert implementation.authority["can_approve_own_work"] is False


def test_extended_mission_lifecycle_matches_generation_one_review_flow():
    mission = OSMission("tenant", "user", "Mission", "Add safe feature")

    for state in [
        "DISCOVERY",
        "REQUIREMENTS_REVIEW",
        "PLANNING",
        "PLAN_REVIEW",
        "AWAITING_APPROVAL",
        "READY",
        "EXECUTING",
        "REVIEWING",
        "VERIFYING",
        "AWAITING_FINAL_APPROVAL",
        "COMPLETED",
    ]:
        mission.transition(state)

    assert mission.state == "COMPLETED"


def test_task_completion_requires_submission_review_evidence_and_verification():
    task = MissionTask(
        tenant_id="tenant",
        project_id="project",
        mission_id="mission",
        title="Implement feature",
        description="Modify approved file",
        task_type="implementation",
        owner_id="implementation-agent",
        reviewer_ids=["security-agent", "qa-agent"],
        required_evidence=["diff-evidence", "test-evidence"],
        risk_level="medium",
        status="ASSIGNED",
    )

    task.transition("IN_PROGRESS")
    task.submit(["diff-evidence", "test-evidence"])
    task.transition("UNDER_REVIEW")

    with pytest.raises(ValueError):
        task.add_review(TaskReview("implementation-agent", "implementation_engineer", "approved"))

    task.add_review(TaskReview("security-agent", "security_reviewer", "approved"))
    assert task.status == "UNDER_REVIEW"

    task.add_review(TaskReview("qa-agent", "qa_reviewer", "approved"))
    assert task.status == "APPROVED"

    with pytest.raises(ValueError):
        task.complete()

    task.verification_passed = True
    task.complete()
    assert task.status == "COMPLETED"


def test_message_bus_blocks_duplicates_and_message_loops():
    bus = MessageBus(per_sender_limit=10, loop_threshold=2)
    base = {
        "tenant_id": "tenant",
        "project_id": "project",
        "mission_id": "mission",
        "organization_id": "org",
        "sender_id": "architect",
        "recipient_type": "agent",
        "recipient_ids": ["security"],
        "message_type": "request",
        "topic": "Review plan",
        "summary": "Please review architecture plan",
        "correlation_id": "thread-1",
    }

    first = bus.send(SpecialistMessage(**base))
    assert first.status == "delivered"

    with pytest.raises(ValueError):
        bus.send(SpecialistMessage(**base))

    bus.send(SpecialistMessage(**{**base, "summary": "Second unique message"}))
    with pytest.raises(ValueError):
        bus.send(SpecialistMessage(**{**base, "summary": "Third message loops"}))


def test_architecture_decision_preserves_options_and_requires_human_approval():
    decision = MissionDecision(
        tenant_id="tenant",
        project_id="project",
        mission_id="mission",
        problem="Choose architecture",
        decision_type="architecture",
        proposed_by="architect",
        options=[
            DecisionOption("Modular monolith", advantages=["Fast"], disadvantages=["Limited independent scaling"]),
            DecisionOption("Microservices", advantages=["Scale"], disadvantages=["Operational cost"]),
        ],
        proposed_option="Modular monolith",
    )

    assert decision.human_approval_required is True
    decision.add_review(DecisionReview("security", "security_reviewer", "approve"))
    assert decision.status == "UNDER_REVIEW"

    with pytest.raises(ValueError):
        decision.finalize("Modular monolith")

    decision.approve_human("founder")
    decision.finalize("Modular monolith")

    assert decision.status == "APPROVED"
    assert decision.final_selection == "Modular monolith"
    assert len(decision.options) == 2


def test_artifact_hash_and_trust_progression_are_enforced():
    artifact = MissionArtifact(
        tenant_id="tenant",
        mission_id="mission",
        artifact_type="code_patch",
        creator_id="implementation",
        content={"diff": "+hello"},
    )
    evidence = Evidence(
        tenant_id="tenant",
        mission_id="mission",
        evidence_type="code_diff",
        summary="Patch diff captured",
        source="git diff",
        artifact_id=artifact.artifact_id,
        verified=True,
    )

    assert len(artifact.hash) == 64
    artifact.promote_trust("PEER_REVIEWED")
    artifact.promote_trust("TOOL_VERIFIED")
    assert artifact.verification_status == "verified"
    assert evidence.verified is True

    with pytest.raises(ValueError):
        artifact.promote_trust("UNVERIFIED")


def test_tool_execution_lifecycle_and_model_metrics_contract():
    definition = ToolDefinition(
        name="Git diff",
        category="git_diff",
        input_schema={"path": "string"},
        output_schema={"diff": "string"},
        permission_requirements=["repo_read"],
        risk_level="low",
    )
    execution = ToolExecution("tenant", "mission", definition.tool_id, "implementation", {"path": "."})

    for state in ["POLICY_CHECKED", "APPROVED", "EXECUTING", "SUCCEEDED"]:
        execution.transition(state)

    metric = ModelExecutionMetric(
        tenant_id="tenant",
        mission_id="mission",
        provider="openai",
        model="reasoning-model",
        role="solution_architect",
        task_type="architecture",
        tokens=1000,
        cost=0.1,
        latency_ms=1200,
        outcome="success",
        validation_result="schema_valid",
    )

    assert execution.state == "SUCCEEDED"
    assert metric.to_dict()["validation_result"] == "schema_valid"
