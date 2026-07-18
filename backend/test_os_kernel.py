import pytest

from services.agent.os_kernel.capabilities import default_software_engineering_registry
from services.agent.os_kernel.context_compiler import ContextCompiler, ContextRequest
from services.agent.os_kernel.events import Actor, AppendOnlyEventStore, EventMetadata, JsonlEventStore, KernelEvent
from services.agent.os_kernel.missions import MissionService, OSMission
from services.agent.os_kernel.policies import AuthorityContext, evaluate_tool_policy
from services.agent.os_kernel.resources import ResourceBudget
from services.agent.os_kernel.runtime import ArceusOSRuntime
from services.agent.os_kernel.scheduler import MissionScheduler, SchedulerPolicy
from services.agent.os_kernel.workflows import WorkflowRun, WorkflowStep
from services.agent.os_kernel.world_model import KnowledgeItem, WorldModel


def test_event_store_is_append_only_and_replayable():
    store = AppendOnlyEventStore()
    mission_id = "mission-1"
    store.append(
        KernelEvent(
            event_type="MISSION_CREATED",
            aggregate_type="mission",
            aggregate_id=mission_id,
            mission_id=mission_id,
            actor=Actor("human", "user-1"),
            payload={"title": "Build product"},
            metadata=EventMetadata(correlation_id=mission_id, idempotency_key="mission-1:create"),
        )
    )

    replay = store.replay("mission", mission_id)

    assert replay[0]["event_type"] == "MISSION_CREATED"
    assert replay[0]["payload"]["title"] == "Build product"
    with pytest.raises(ValueError):
        store.append(
            KernelEvent(
                event_type="MISSION_CREATED",
                aggregate_type="mission",
                aggregate_id=mission_id,
                actor=Actor("human", "user-1"),
                metadata=EventMetadata(correlation_id=mission_id, idempotency_key="mission-1:create"),
            )
        )


def test_jsonl_event_store_survives_restart_and_keeps_idempotency_index(tmp_path):
    path = tmp_path / "events.jsonl"
    store = JsonlEventStore(path)
    mission_id = "mission-durable"
    store.append(
        KernelEvent(
            event_type="MISSION_CREATED",
            aggregate_type="mission",
            aggregate_id=mission_id,
            mission_id=mission_id,
            actor=Actor("human", "user-1"),
            payload={"title": "Durable mission"},
            metadata=EventMetadata(correlation_id=mission_id, idempotency_key="durable:create"),
        )
    )

    restored = JsonlEventStore(path)

    assert restored.replay("mission", mission_id)[0]["payload"]["title"] == "Durable mission"
    with pytest.raises(ValueError):
        restored.append(
            KernelEvent(
                event_type="MISSION_CREATED",
                aggregate_type="mission",
                aggregate_id=mission_id,
                actor=Actor("human", "user-1"),
                metadata=EventMetadata(correlation_id=mission_id, idempotency_key="durable:create"),
            )
        )


def test_runtime_rebuilds_mission_projection_from_event_log(tmp_path):
    path = tmp_path / "runtime-events.jsonl"
    runtime = ArceusOSRuntime(JsonlEventStore(path))
    mission = OSMission("tenant", "founder", "Restart-safe mission", "Build durable mission runtime")

    runtime.submit_software_mission(mission, Actor("human", "founder"))
    runtime.missions.transition(mission.mission_id, "DISCOVERY", Actor("system", "kernel"))
    runtime.missions.transition(mission.mission_id, "PLANNING", Actor("system", "kernel"))
    runtime.missions.transition(mission.mission_id, "READY", Actor("human", "founder"))
    runtime.form_engineering_organization(mission.mission_id, Actor("system", "kernel"))

    restored = ArceusOSRuntime(JsonlEventStore(path))

    assert restored.missions.missions[mission.mission_id].state == "READY"
    assert restored.missions.missions[mission.mission_id].title == "Restart-safe mission"
    assert restored.organizations[mission.mission_id].specialists == [
        "Engineering Manager",
        "Architect",
        "Implementation Engineer",
        "Security Reviewer",
        "QA Reviewer",
    ]


def test_mission_state_machine_validates_transitions_and_pause():
    service = MissionService(AppendOnlyEventStore())
    mission = OSMission("tenant-1", "user-1", "Build auth", "Build secure auth")
    service.intake(mission, Actor("human", "user-1"))

    service.transition(mission.mission_id, "DISCOVERY", Actor("system", "kernel"))
    service.transition(mission.mission_id, "PLANNING", Actor("system", "kernel"))
    service.transition(mission.mission_id, "READY", Actor("human", "user-1"))

    assert mission.state == "READY"
    service.pause_immediately(mission.mission_id, Actor("human", "user-1"))
    assert mission.state == "PAUSED"
    assert mission.paused_by_user is True

    with pytest.raises(ValueError):
        mission.transition("COMPLETED")


def test_scheduler_selects_priority_without_running_everything():
    scheduler = MissionScheduler(SchedulerPolicy(max_concurrent_missions=1))
    low = OSMission("tenant", "user", "Low", "Low", business_priority=0.1, state="READY")
    high = OSMission("tenant", "user", "High", "High", business_priority=0.9, urgency=0.9, state="READY")
    blocked = OSMission("tenant", "user", "Blocked", "Blocked", business_priority=1.0, state="READY", dependencies=["other"])

    selected = scheduler.select_ready([low, high, blocked])

    assert selected == [high]


def test_capability_registry_discovers_available_domain_capabilities():
    registry = default_software_engineering_registry()

    capabilities = registry.discover(domains=["software_engineering"], category="security", risk_at_most="medium")

    assert len(capabilities) == 1
    assert capabilities[0].name == "secure_code_review"


def test_workflow_step_idempotency_prevents_duplicate_action_after_restart():
    step = WorkflowStep("Patch", "Implementation Engineer", {}, {}, 60, "mission:patch")
    run = WorkflowRun("mission-1", [step])

    run.execute_step(step.step_id, {"patch": "created"}, {"kind": "diff", "status": "created"})

    restored = WorkflowRun("mission-1", [step], completed_idempotency_keys=set(run.completed_idempotency_keys))
    with pytest.raises(ValueError):
        restored.steps[0].start(restored.completed_idempotency_keys)


def test_high_risk_policy_blocks_author_approving_own_work():
    context = AuthorityContext(
        actor_id="implementation-agent",
        tenant_id="tenant",
        role="engineer",
        environment="production",
        approved=True,
        reviewer_ids=["implementation-agent"],
    )

    decision = evaluate_tool_policy(context, "PRODUCTION_CHANGE", "high", author_id="implementation-agent")

    assert decision.allowed is False
    assert "Author cannot be the only reviewer" in decision.reason


def test_resource_budget_blocks_work_before_exceeding_limits():
    budget = ResourceBudget(token_budget=100, cost_budget=1.0, tool_calls=2, model_calls=2)

    budget.spend(tokens=50, cost=0.4, tool_calls=1, model_calls=1)

    assert budget.summary()["remaining_tokens"] == 50
    with pytest.raises(ValueError):
        budget.spend(tokens=60)


def test_world_model_distinguishes_claims_from_approved_lessons_and_tenants():
    world = WorldModel()
    claim = world.write(
        KnowledgeItem(
            tenant_id="tenant-a",
            kind="CLAIM",
            content="Use Redis for all state",
            source="agent",
            author="agent-1",
            scope="mission",
            verification_status="UNVERIFIED",
        )
    )
    lesson = world.write(
        KnowledgeItem(
            tenant_id="tenant-a",
            kind="FACT",
            content="Use idempotency keys before tool execution",
            source="mission",
            author="qa",
            scope="organization",
            verification_status="APPROVED",
        )
    )
    world.write(
        KnowledgeItem(
            tenant_id="tenant-b",
            kind="FACT",
            content="Private other tenant lesson",
            source="mission",
            author="qa",
            scope="organization",
            verification_status="APPROVED",
        )
    )

    results = world.retrieve(tenant_id="tenant-a", query_terms=["idempotency", "Redis"], scope="organization")

    assert claim.trusted is False
    assert lesson.trusted is True
    assert all(item.tenant_id == "tenant-a" for item in results)
    assert results[0].item_id == lesson.item_id


def test_context_compiler_excludes_secret_memory_without_authority():
    mission = OSMission("tenant", "user", "Build app", "Build software app", success_criteria=["Tests pass"])
    world = WorldModel()
    world.write(
        KnowledgeItem(
            tenant_id="tenant",
            kind="DECISION",
            content="Approved architecture decision for app",
            source="review",
            author="architect",
            scope="mission",
            verification_status="APPROVED",
        )
    )
    world.write(
        KnowledgeItem(
            tenant_id="tenant",
            kind="FACT",
            content="secret production credential",
            source="vault",
            author="system",
            scope="mission",
            verification_status="APPROVED",
            sensitivity="secret",
        )
    )
    compiler = ContextCompiler(world, default_software_engineering_registry())

    context = compiler.compile(
        ContextRequest(
            tenant_id="tenant",
            agent_role="Implementation Engineer",
            task_title="Implement app",
            task_description="Use approved architecture decision",
            mission=mission,
            has_secret_authority=False,
        )
    )

    serialized = str(context)
    assert "Approved architecture decision" in serialized
    assert "secret production credential" not in serialized


def test_runtime_executes_first_real_mvp_loop_and_records_lessons():
    runtime = ArceusOSRuntime()
    actor = Actor("human", "founder")
    mission = OSMission(
        tenant_id="tenant",
        owner_id="founder",
        title="Improve repository",
        objective="Analyze repository and implement a safe software change",
        success_criteria=["Security and QA approve", "Tests pass", "User approves merge"],
    )

    runtime.submit_software_mission(mission, actor)
    runtime.missions.transition(mission.mission_id, "DISCOVERY", Actor("system", "kernel"))
    runtime.missions.transition(mission.mission_id, "PLANNING", Actor("system", "kernel"))
    runtime.missions.transition(mission.mission_id, "READY", actor)
    organization = runtime.form_engineering_organization(mission.mission_id, Actor("system", "kernel"))
    workflow = runtime.create_implementation_workflow(mission.mission_id)

    assert organization.specialists == [
        "Engineering Manager",
        "Architect",
        "Implementation Engineer",
        "Security Reviewer",
        "QA Reviewer",
    ]

    for step in list(workflow.steps):
        evidence = {"kind": "proof", "status": "passed", "lesson": "Approved changes must link to tasks and decisions"}
        runtime.execute_workflow_step(workflow.run_id, step.step_id, {"status": "ok"}, evidence)

    events = runtime.events.by_mission(mission.mission_id)
    lesson_context = runtime.compile_context_for_task(mission.mission_id, "Plan another mission", "Use approved changes")

    assert workflow.state == "COMPLETED"
    assert any(event.event_type == "TASK_COMPLETED" for event in events)
    assert any(event.event_type == "LESSON_RECORDED" for event in events)
    assert "Approved changes must link to tasks and decisions" in str(lesson_context)


def test_failed_tests_prevent_completion_without_pass_evidence():
    step = WorkflowStep("Independent QA review", "QA Reviewer", {}, {}, 60, "mission:qa")
    run = WorkflowRun("mission", [step])

    step.start(run.completed_idempotency_keys)
    with pytest.raises(ValueError):
        step.complete({"tests": "failed"}, {})
