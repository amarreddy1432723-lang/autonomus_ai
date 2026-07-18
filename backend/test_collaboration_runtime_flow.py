from services.agent.collaboration_runtime import (
    CollaborationRuntime,
    Decision,
    DecisionAlternative,
    MessageEnvelope,
    MessageRecipient,
    Mission,
    ReviewResult,
)


def test_runtime_executes_foundation_flow_and_emits_events():
    runtime = CollaborationRuntime(Mission(title="Build auth", description="Build secure OAuth authentication for a software product"))

    runtime.extract_goals()
    domains = runtime.classify_domains()
    organization = runtime.build_organization()
    tasks = runtime.orchestrate_tasks()
    runtime.approve_mission()

    assert "software_engineering" in domains
    assert organization.status == "active"
    assert len(tasks) == 3
    assert runtime.mission.status == "approved"
    assert [event["event_type"] for event in runtime.timeline()] == [
        "mission_created",
        "mission_updated",
        "mission_updated",
        "organization_created",
        "task_created",
        "task_created",
        "task_created",
        "approval_recorded",
    ]


def test_structured_message_is_published_to_event_stream():
    runtime = CollaborationRuntime(Mission(title="Build auth", description="Build auth"))
    runtime.extract_goals()
    organization = runtime.build_organization()
    sender = organization.agents[3]
    receiver = organization.agents[2]

    message = MessageEnvelope(
        mission_id=runtime.mission.mission_id,
        organization_id=organization.organization_id,
        from_agent_id=sender.agent_id,
        to=MessageRecipient(type="agent", ids=[receiver.agent_id]),
        message_type="finding",
        topic="Authentication Review",
        summary="Refresh token rotation is required.",
        content={"recommendation": "Rotate refresh tokens on every use."},
        evidence=[{"kind": "code_review", "summary": "Refresh token reuse observed."}],
        confidence=0.97,
        priority="high",
        requires_response=True,
    )

    runtime.publish_message(message)

    assert runtime.messages[0].topic == "Authentication Review"
    assert runtime.timeline()[-1]["event_type"] == "message_published"


def test_review_council_approves_after_threshold():
    runtime = CollaborationRuntime(Mission(title="Choose architecture", description="Choose app architecture"))
    runtime.extract_goals()
    organization = runtime.build_organization()
    architect = next(agent for agent in organization.agents if agent.role == "solution_architect")
    security = next(agent for agent in organization.agents if agent.role == "security_reviewer")
    qa = next(agent for agent in organization.agents if agent.role == "qa_reviewer")

    decision = Decision(
        mission_id=runtime.mission.mission_id,
        title="Use modular monolith",
        problem="Need fast MVP with clean module boundaries.",
        decision_type="architecture",
        proposed_by=architect.agent_id,
        alternatives=[
            DecisionAlternative(name="Modular monolith", advantages=["Fast delivery"], disadvantages=["Limited independent scaling"]),
            DecisionAlternative(name="Microservices", advantages=["Independent scaling"], disadvantages=["Higher ops cost"]),
        ],
        selected_option="Modular monolith",
        confidence=0.91,
    )

    runtime.run_review(
        decision,
        [
            ReviewResult(reviewer=security.agent_id, verdict="approve", findings=["No blocking security issue."]),
            ReviewResult(reviewer=qa.agent_id, verdict="approve_with_conditions", recommendations=["Add integration tests."]),
        ],
    )

    assert decision.status == "approved"
    assert runtime.timeline()[-1]["event_type"] == "review_recorded"


def test_runtime_requires_evidence_for_task_completion_and_report():
    runtime = CollaborationRuntime(Mission(title="Build auth", description="Build auth"))
    runtime.extract_goals()
    runtime.build_organization()
    tasks = runtime.orchestrate_tasks()

    task = tasks[0]
    runtime.transition_task(task.task_id, "in_progress")
    runtime.transition_task(task.task_id, "review")
    runtime.transition_task(task.task_id, "approved")
    runtime.transition_task(task.task_id, "completed", evidence={"kind": "review", "status": "passed"})

    verification = runtime.verify_mission()
    report = runtime.create_mission_report()

    assert verification["completed_tasks"] == 1
    assert verification["evidence_count"] == 1
    assert report["completed_tasks"][0]["task_id"] == task.task_id


def test_learning_engine_records_global_reusable_lesson():
    runtime = CollaborationRuntime(Mission(title="Build auth", description="Build auth"))
    lesson = runtime.record_lesson("OAuth lesson", {"text": "Rotate refresh tokens."}, tags=["auth", "security"])

    assert lesson.memory_level == "global"
    assert runtime.timeline()[-1]["event_type"] == "lesson_recorded"
