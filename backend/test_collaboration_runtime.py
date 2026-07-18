from services.agent.collaboration_runtime import (
    Mission,
    WorkspaceArtifact,
    SharedWorkspace,
    Task,
    Authority,
    build_generation_one_organization,
    decompose_mission_to_tasks,
    approval_policy_for_risk,
)


def test_mission_requires_objectives_and_success_criteria_before_execution():
    mission = Mission(title="Build product", description="Create a product")
    assert mission.can_enter_execution() is False

    mission.objectives.append("Ship MVP")
    mission.success_criteria.append("User can complete core flow")
    mission.status = "approved"

    assert mission.can_enter_execution() is True


def test_generation_one_organization_has_five_specialists_and_reviewers():
    mission = Mission(title="Build app", description="Build a software app")
    organization = build_generation_one_organization(mission)

    roles = {agent.role for agent in organization.agents}

    assert len(organization.agents) == 5
    assert {"product_analyst", "solution_architect", "implementation_engineer", "security_reviewer", "qa_reviewer"} == roles
    assert organization.approval_policy["independent_approvals"] == 2
    assert organization.communication_policy["message_envelope_required"] is True


def test_decomposition_creates_evidence_oriented_tasks():
    mission = Mission(title="Repair auth", description="Fix auth")
    organization = build_generation_one_organization(mission)
    tasks = decompose_mission_to_tasks(mission, organization)

    assert len(tasks) == 3
    assert all(task.acceptance_criteria for task in tasks)
    assert any(task.approval_required for task in tasks)


def test_task_cannot_complete_without_evidence():
    mission = Mission(title="Build product", description="Create a product")
    task = Task(
        mission_id=mission.mission_id,
        title="Run checks",
        description="Run verification",
        task_type="testing",
        assigned_agent_id="agent-1",
        status="approved",
    )

    assert task.can_complete() is False
    task.evidence.append({"kind": "test_output", "status": "passed"})
    assert task.can_complete() is True


def test_context_selection_filters_private_artifacts_without_authority():
    mission = Mission(title="Build product", description="Create a product")
    public_artifact = WorkspaceArtifact(kind="requirement", title="Public requirement", content="A", relevance_tags=["testing"])
    private_artifact = WorkspaceArtifact(kind="secret", title="Private note", content="B", confidentiality="private", relevance_tags=["testing"])
    workspace = SharedWorkspace(mission=mission, artifacts=[public_artifact, private_artifact])

    task = Task(
        mission_id=mission.mission_id,
        title="Testing task",
        description="Test",
        task_type="testing",
        assigned_agent_id="agent-1",
    )
    context = workspace.select_context(task=task, authority=Authority(can_approve=False))

    titles = [item["title"] for item in context["related_artifacts"]]
    assert "Public requirement" in titles
    assert "Private note" not in titles


def test_high_risk_policy_requires_human_approval():
    policy = approval_policy_for_risk("high")
    assert policy["human_approval"] is True
    assert "production_deployment" in policy["always_require_human_approval"]
