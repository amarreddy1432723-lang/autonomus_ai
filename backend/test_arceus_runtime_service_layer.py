import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from services.agent.arceus_runtime.application.idempotency import calculate_request_hash
from services.agent.arceus_runtime.application.errors import TaskStateConflict
from services.agent.arceus_runtime.application.unit_of_work import DecisionRepository, TaskRepository, UsageRepository
from services.agent.arceus_runtime.approvals.service import quorum_satisfied, resolve_approval_if_ready
from services.agent.arceus_runtime.audit.routes import _replay_event_response
from services.agent.arceus_runtime.capabilities.routes import _capability_response
from services.agent.arceus_runtime.events.routes import sse_event, sse_heartbeat
from services.agent.arceus_runtime.gateway.api_schemas import ToolExecutionRequest
from services.agent.arceus_runtime.gateway.routes import _tool_execution_evidence
from services.agent.arceus_runtime.execution_traces.routes import _model_execution_response
from services.agent.arceus_runtime.health.routes import classify_runtime_health
from services.agent.arceus_runtime.missions.api_schemas import CreateMissionRequest
from services.agent.arceus_runtime.missions.domain import transition_mission
from services.agent.arceus_runtime.operations.service import calculate_slo_posture, classify_queue_health, classify_worker_pool, operation_guard
from services.agent.arceus_runtime.organizations.routes import _member_response
from services.agent.arceus_runtime.router import install_arceus_runtime
from services.agent.arceus_runtime.workspaces.service import repository_fingerprint, workspace_slug, workspace_settings
from services.agent.arceus_runtime.workers.outbox import MAX_OUTBOX_ATTEMPTS, calculate_backoff_seconds
from services.shared.arceus_core_models import ArceusAIExecutionLedger, ArceusApproval, ArceusApprovalVote, ArceusCapability, ArceusDecision, ArceusEvent, ArceusMission, ArceusModelExecution, ArceusOrganizationMember, ArceusSpecialistProfile, ArceusTask


def test_runtime_installs_spec_mission_routes() -> None:
    app = FastAPI()
    install_arceus_runtime(app)

    routes = {(route.path, ",".join(sorted(route.methods or []))) for route in app.routes}

    assert ("/api/v1/missions", "POST") in routes
    assert ("/api/v1/missions", "GET") in routes
    assert ("/api/v1/missions/{mission_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/events", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/clarifications", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/clarifications", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/compile", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/plan", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/start", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/pause", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/resume", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/cancel", "POST") in routes
    assert ("/api/v1/events/stream", "GET") in routes
    assert ("/api/v1/approvals", "GET") in routes
    assert ("/api/v1/approvals/{approval_id}", "GET") in routes
    assert ("/api/v1/approvals/{approval_id}/approve", "POST") in routes
    assert ("/api/v1/approvals/{approval_id}/reject", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/artifacts", "GET") in routes
    assert ("/api/v1/artifacts/{artifact_id}", "GET") in routes
    assert ("/api/v1/artifacts/{artifact_id}/versions", "GET") in routes
    assert ("/api/v1/artifact-versions/{version_id}/content", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/evidence", "GET") in routes
    assert ("/api/v1/evidence/{evidence_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/verification-runs", "GET") in routes
    assert ("/api/v1/verification-runs/{verification_run_id}", "GET") in routes
    assert ("/api/v1/verifications", "POST") in routes
    assert ("/api/v1/verifications/{verification_id}", "GET") in routes
    assert ("/api/v1/evidence", "POST") in routes
    assert ("/api/v1/quality-gates/run", "POST") in routes
    assert ("/api/v1/completion/{mission_id}", "GET") in routes
    assert ("/api/v1/completion/approve", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/tasks", "GET") in routes
    assert ("/api/v1/tasks/{task_id}", "GET") in routes
    assert ("/api/v1/tasks/{task_id}/attempts", "GET") in routes
    assert ("/api/v1/tasks/{task_id}/retry", "POST") in routes
    assert ("/api/v1/tasks/{task_id}/skip", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/runtime/schedule", "POST") in routes
    assert ("/api/v1/workflows/{workflow_id}/graph", "GET") in routes
    assert ("/api/v1/tasks/{task_id}/leases", "POST") in routes
    assert ("/api/v1/worker-leases/{lease_id}/heartbeat", "POST") in routes
    assert ("/api/v1/worker-leases/{lease_id}/complete", "POST") in routes
    assert ("/api/v1/worker-leases/{lease_id}/fail", "POST") in routes
    assert ("/api/v1/tasks/{task_id}/checkpoints", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/decisions", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/decisions/current", "GET") in routes
    assert ("/api/v1/decisions/{decision_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/messages", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/messages", "GET") in routes
    assert ("/api/v1/participants/{participant_id}/inbox", "GET") in routes
    assert ("/api/v1/inbox/{item_id}/acknowledge", "POST") in routes
    assert ("/api/v1/missions/{mission_id}/collaboration-decisions", "POST") in routes
    assert ("/api/v1/collaboration-decisions/{decision_id}/resolve", "POST") in routes
    assert ("/api/v1/reviews", "POST") in routes
    assert ("/api/v1/reviews/{review_id}/complete", "POST") in routes
    assert ("/api/v1/memory/proposals", "POST") in routes
    assert ("/api/v1/memory/{memory_id}/approve", "POST") in routes
    assert ("/api/v1/memory/search", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/organization", "GET") in routes
    assert ("/api/v1/organizations/{organization_id}/members", "GET") in routes
    assert ("/api/v1/organization-members/{member_id}", "GET") in routes
    assert ("/api/v1/capabilities", "GET") in routes
    assert ("/api/v1/capabilities/{capability_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/capabilities/required", "GET") in routes
    assert ("/api/v1/specialist-profiles/{specialist_profile_id}/capabilities", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/compiler-runs", "GET") in routes
    assert ("/api/v1/compiler-runs/{compiler_run_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/context-packages", "GET") in routes
    assert ("/api/v1/context-packages/{context_package_id}", "GET") in routes
    assert ("/api/v1/model-executions", "GET") in routes
    assert ("/api/v1/models", "GET") in routes
    assert ("/api/v1/models/{model_key}", "GET") in routes
    assert ("/api/v1/admin/models", "POST") in routes
    assert ("/api/v1/admin/models/{model_key}", "PATCH") in routes
    assert ("/api/v1/admin/models/{model_key}/enable", "POST") in routes
    assert ("/api/v1/admin/models/{model_key}/disable", "POST") in routes
    assert ("/api/v1/providers", "GET") in routes
    assert ("/api/v1/providers/{provider_key}/health", "GET") in routes
    assert ("/api/v1/admin/providers", "POST") in routes
    assert ("/api/v1/admin/providers/{provider_key}", "PATCH") in routes
    assert ("/api/v1/admin/providers/{provider_key}/test", "POST") in routes
    assert ("/api/v1/ai/route", "POST") in routes
    assert ("/api/v1/ai/execute", "POST") in routes
    assert ("/api/v1/ai/executions/{execution_id}", "GET") in routes
    assert ("/api/v1/ai/executions/{execution_id}/evaluation", "GET") in routes
    assert ("/api/v1/tools", "GET") in routes
    assert ("/api/v1/admin/tools", "POST") in routes
    assert ("/api/v1/tools/authorize", "POST") in routes
    assert ("/api/v1/tools/execute", "POST") in routes
    assert ("/api/v1/tools/executions/{execution_id}", "GET") in routes
    assert ("/api/v1/tools/executions/{execution_id}/rollback", "POST") in routes
    assert ("/api/v1/budgets/{scope_type}/{scope_id}", "GET") in routes
    assert ("/api/v1/budgets", "POST") in routes
    assert ("/api/v1/budgets/{budget_id}", "PATCH") in routes
    assert ("/api/v1/budgets/{budget_id}/request-increase", "POST") in routes
    assert ("/api/v1/costs/missions/{mission_id}", "GET") in routes
    assert ("/api/v1/model-executions/{model_execution_id}", "GET") in routes
    assert ("/api/v1/tool-definitions", "GET") in routes
    assert ("/api/v1/tool-executions", "GET") in routes
    assert ("/api/v1/tool-executions/{tool_execution_id}", "GET") in routes
    assert ("/api/v1/policy-evaluations", "GET") in routes
    assert ("/api/v1/policy-evaluations/{policy_evaluation_id}", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/replay", "GET") in routes
    assert ("/api/v1/audit-events", "GET") in routes
    assert ("/api/v1/audit-events/{audit_event_id}", "GET") in routes
    assert ("/api/v1/runtime/usage/records", "GET") in routes
    assert ("/api/v1/runtime/usage/records/{usage_record_id}", "GET") in routes
    assert ("/api/v1/runtime/usage/summary", "GET") in routes
    assert ("/api/v1/missions/{mission_id}/usage", "GET") in routes
    assert ("/api/v1/runtime/health", "GET") in routes
    assert ("/api/v1/security/policies", "GET") in routes
    assert ("/api/v1/security/evaluate", "POST") in routes
    assert ("/api/v1/security/audit", "GET") in routes
    assert ("/api/v1/security/incidents", "POST") in routes
    assert ("/api/v1/security/compliance", "GET") in routes
    assert ("/api/v1/workspaces", "GET") in routes
    assert ("/api/v1/workspaces", "POST") in routes
    assert ("/api/v1/workspaces/{workspace_id}/missions", "GET") in routes
    assert ("/api/v1/workspaces/{workspace_id}/repositories", "POST") in routes
    assert ("/api/v1/workspaces/{workspace_id}/activity", "GET") in routes
    assert ("/api/v1/workspaces/{workspace_id}/organization", "GET") in routes
    assert ("/api/v1/workspaces/{workspace_id}/knowledge", "GET") in routes
    assert ("/api/v1/operations/health", "GET") in routes
    assert ("/api/v1/operations/regions", "GET") in routes
    assert ("/api/v1/operations/workers", "GET") in routes
    assert ("/api/v1/operations/queues", "GET") in routes
    assert ("/api/v1/operations/slos", "GET") in routes
    assert ("/api/v1/operations/failover", "POST") in routes
    assert ("/api/v1/operations/dr-test", "POST") in routes


def test_idempotency_hash_is_stable_and_operation_scoped() -> None:
    payload_a = {"objective": "Build product", "repository_ids": ["repo-1"], "priority": 50}
    payload_b = {"priority": 50, "repository_ids": ["repo-1"], "objective": "Build product"}

    assert calculate_request_hash("mission.create", payload_a) == calculate_request_hash("mission.create", payload_b)
    assert calculate_request_hash("mission.create", payload_a) != calculate_request_hash("mission.compile", payload_a)


def test_workspace_slug_and_settings_are_desktop_mission_first() -> None:
    assert workspace_slug("  Arceus Platform / MVP  ") == "arceus-platform-mvp"
    settings = workspace_settings({"autonomy": "review_first"})

    assert settings["shell"] == "arceus_code"
    assert settings["primary_navigation"] == "missions"
    assert "terminal" in settings["desktop_modules"]
    assert settings["autonomy"] == "review_first"


def test_repository_fingerprint_preserves_indexing_metadata() -> None:
    fingerprint = repository_fingerprint(
        provider="github",
        repository_url="https://github.com/acme/platform",
        local_workspace_path="C:/work/acme",
        metadata={"languages": ["typescript"], "frameworks": ["nextjs"], "build_systems": ["npm"], "indexed": True},
    )

    assert fingerprint["provider"] == "github"
    assert fingerprint["languages"] == ["typescript"]
    assert fingerprint["frameworks"] == ["nextjs"]
    assert fingerprint["indexed"] is True


def test_create_mission_request_rejects_empty_constraint_items() -> None:
    with pytest.raises(ValueError):
        CreateMissionRequest(
            project_id=uuid.uuid4(),
            objective="Analyze this repository and build a safe MVP plan.",
            repository_ids=[uuid.uuid4()],
            constraints=["Use existing patterns", "   "],
        )


def test_mission_transition_matrix_allows_compile_from_draft() -> None:
    mission = ArceusMission(
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Build product",
        objective="Build a safe product mission",
        status="draft",
        version_number=1,
    )

    previous, target = transition_mission(mission, "compile")

    assert previous == "draft"
    assert target == "compiling"
    assert mission.status == "compiling"
    assert mission.version_number == 2


def test_mission_transition_matrix_rejects_start_from_draft() -> None:
    mission = ArceusMission(
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Build product",
        objective="Build a safe product mission",
        status="draft",
        version_number=1,
    )

    with pytest.raises(Exception) as exc_info:
        transition_mission(mission, "start")

    assert getattr(exc_info.value, "code") == "MISSION_STATE_CONFLICT"
    assert mission.status == "draft"
    assert mission.version_number == 1


def test_outbox_backoff_is_bounded_and_attempt_policy_is_finite() -> None:
    assert MAX_OUTBOX_ATTEMPTS == 3
    assert calculate_backoff_seconds(1) == 5
    assert calculate_backoff_seconds(2) == 10
    assert calculate_backoff_seconds(3) == 20
    assert calculate_backoff_seconds(20) == 60


def test_operations_queue_health_blocks_on_dead_letters() -> None:
    health, recommendations = classify_queue_health({"pending": 4, "dead_letter": 1})

    assert health == "blocked"
    assert "inspect_dead_letter_queue" in recommendations


def test_operations_worker_pool_detects_starvation() -> None:
    status, recommendations = classify_worker_pool(
        {
            "task_statuses": {"ready": 3, "running": 0, "blocked": 0, "failed": 0},
            "active_worker_leases": 0,
        }
    )

    assert status == "starved"
    assert "start_or_scale_workers" in recommendations


def test_operations_slo_posture_burns_error_budget_on_queue_blocker() -> None:
    slos = {item["slo_key"]: item for item in calculate_slo_posture({"outbox_statuses": {"dead_letter": 1}, "task_statuses": {}})}

    assert slos["queue_delivery"]["status"] == "breached"
    assert "dead_letter_queue" in slos["queue_delivery"]["burn_reasons"]
    assert slos["mission_state_durability"]["status"] == "met"


def test_operations_failover_guard_is_dry_run_only_without_automation() -> None:
    accepted, reason, approvals = operation_guard(action="failover", dry_run=True)
    assert accepted is True
    assert "dry run accepted" in reason
    assert "sre_lead" in approvals

    accepted, reason, approvals = operation_guard(action="failover", dry_run=False)
    assert accepted is False
    assert "requires external infrastructure automation" in reason
    assert "security_reviewer" in approvals


def test_sse_frame_format_uses_cursor_id_and_stable_event_name() -> None:
    frame = sse_event(
        event_id=42,
        event_name="MISSION_STATE_CHANGED",
        data={"mission_id": "m1", "status": "running"},
    )

    assert frame.startswith("id: 42\n")
    assert "event: mission.state.changed\n" in frame
    assert 'data: {"mission_id":"m1","status":"running"}\n\n' in frame
    assert sse_heartbeat() == ": heartbeat\n\n"


def test_ai_vote_does_not_satisfy_human_required_quorum() -> None:
    approval = ArceusApproval(
        tenant_id=uuid.uuid4(),
        mission_id=uuid.uuid4(),
        approval_type="mission_plan",
        subject_hash="abc",
        quorum_policy={"requires_human": True, "required_human_votes": 1},
    )
    ai_vote = ArceusApprovalVote(
        tenant_id=approval.tenant_id,
        approval_id=uuid.uuid4(),
        vote="approve",
        is_human_vote=False,
    )

    assert quorum_satisfied(approval, [ai_vote]) is False


def test_tool_execution_evidence_records_gateway_provenance() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    task_id = uuid.uuid4()
    approval_id = uuid.uuid4()
    payload = ToolExecutionRequest(
        mission_id=mission_id,
        task_id=task_id,
        tool_key="github",
        action_key="open_pull_request",
        arguments={},
        environment="local",
        timeout_seconds=30,
        dry_run=False,
        approval_id=approval_id,
        idempotency_key="github-open-pr",
    )
    ledger = ArceusAIExecutionLedger(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        execution_kind="tool",
        task_type="tool_execution",
        tool_key="github",
        action_key="open_pull_request",
        status="completed",
        response_hash="sha256:response",
        result={
            "output": {
                "pull_request_url": "https://github.com/acme/platform/pull/42",
                "approved_commit_sha": "abcdef1234567890",
            },
            "evidence": {
                "approved_commit_sha": "abcdef1234567890",
                "pull_request_url": "https://github.com/acme/platform/pull/42",
            },
        },
    )

    evidence = _tool_execution_evidence(tenant_id=tenant_id, payload=payload, ledger=ledger)

    assert evidence is not None
    assert evidence.evidence_type == "tool_github_open_pull_request"
    assert evidence.status == "validated"
    assert evidence.trust_level == "tool_verified"
    assert evidence.verification_method == "gateway_tool:github.open_pull_request"
    assert evidence.payload["execution_ledger_id"] == str(ledger.id)
    assert evidence.payload["approval_id"] == str(approval_id)
    assert evidence.payload["pull_request_url"] == "https://github.com/acme/platform/pull/42"
    assert evidence.content_hash.startswith("sha256:")


def test_tool_execution_evidence_skips_dry_run() -> None:
    payload = ToolExecutionRequest(
        mission_id=uuid.uuid4(),
        tool_key="git",
        action_key="status",
        arguments={},
        environment="local",
        timeout_seconds=30,
        dry_run=True,
        idempotency_key="git-status",
    )
    ledger = ArceusAIExecutionLedger(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        mission_id=payload.mission_id,
        execution_kind="tool",
        task_type="tool_execution",
        tool_key="git",
        action_key="status",
        status="completed",
        result={"evidence": {"side_effect_class": "READ_ONLY"}},
    )

    assert _tool_execution_evidence(tenant_id=ledger.tenant_id, payload=payload, ledger=ledger) is None


def test_human_plan_approval_moves_mission_to_ready() -> None:
    tenant_id = uuid.uuid4()
    mission = ArceusMission(
        tenant_id=tenant_id,
        project_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Build product",
        objective="Build a safe product mission",
        status="awaiting_plan_approval",
        version_number=5,
    )
    approval = ArceusApproval(
        tenant_id=tenant_id,
        mission_id=mission.id or uuid.uuid4(),
        approval_type="mission_plan",
        subject_hash="abc",
        quorum_policy={"requires_human": True, "required_human_votes": 1},
    )
    human_vote = ArceusApprovalVote(
        tenant_id=tenant_id,
        approval_id=uuid.uuid4(),
        vote="approve",
        is_human_vote=True,
    )

    assert resolve_approval_if_ready(approval, mission, [human_vote]) == "approved"
    assert approval.status == "approved"
    assert mission.status == "ready"
    assert mission.version_number == 6


def test_task_retry_requeues_failed_task() -> None:
    task = ArceusTask(
        tenant_id=uuid.uuid4(),
        mission_id=uuid.uuid4(),
        task_key="backend.auth",
        title="Fix auth API",
        task_type="implementation",
        status="failed",
        failure_reason="tests failed",
        version_number=3,
        output_contract={},
    )

    TaskRepository(None).retry(task, reason="After config fix")

    assert task.status == "ready"
    assert task.failure_reason is None
    assert task.started_at is None
    assert task.completed_at is None
    assert task.version_number == 4
    assert task.output_contract["last_retry_reason"] == "After config fix"


def test_task_skip_rejects_running_task() -> None:
    task = ArceusTask(
        tenant_id=uuid.uuid4(),
        mission_id=uuid.uuid4(),
        task_key="frontend.login",
        title="Build login UI",
        task_type="implementation",
        status="running",
        version_number=1,
    )

    with pytest.raises(TaskStateConflict):
        TaskRepository(None).skip(task, reason="No longer needed")


class _DecisionQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def order_by(self, *criteria):
        return self

    def limit(self, value):
        return self

    def all(self):
        rows = list(self.rows)
        if len(self.filters) >= 3:
            rows = [row for row in rows if row.status != "superseded"]
        return rows


class _DecisionDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return _DecisionQuery(self.rows)


def test_current_decisions_exclude_superseded_records() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    rows = [
        ArceusDecision(
            tenant_id=tenant_id,
            mission_id=mission_id,
            decision_key="architecture.current",
            title="Architecture",
            summary="Use modular monolith.",
            selected_option={},
            alternatives=[],
            rationale="Best MVP path.",
            status="approved",
        ),
        ArceusDecision(
            tenant_id=tenant_id,
            mission_id=mission_id,
            decision_key="architecture.old",
            title="Old Architecture",
            summary="Use microservices.",
            selected_option={},
            alternatives=[],
            rationale="Earlier assumption.",
            status="superseded",
        ),
    ]

    current = DecisionRepository(_DecisionDb(rows)).list_for_mission(
        tenant_id=tenant_id,
        mission_id=mission_id,
        current_only=True,
    )

    assert [decision.decision_key for decision in current] == ["architecture.current"]


def test_organization_member_response_exposes_authority_flags() -> None:
    now = datetime.now(timezone.utc)
    member = ArceusOrganizationMember(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        specialist_profile_id=uuid.uuid4(),
        role_key="security_reviewer",
        responsibility="Review material security-sensitive changes.",
        authority={"veto": ["unsafe_change"]},
        can_implement=False,
        can_review=True,
        can_approve=False,
        status="active",
        created_at=now,
        updated_at=now,
        version_number=1,
    )
    profile = ArceusSpecialistProfile(
        id=member.specialist_profile_id,
        specialist_key="security.reviewer",
        display_name="Security Reviewer",
        specialist_type="ai",
        authority_profile={"can_veto": True},
        default_model_policy={"quality": "high"},
        active=True,
    )

    response = _member_response(member, profile)

    assert response.role_key == "security_reviewer"
    assert response.can_implement is False
    assert response.can_review is True
    assert response.can_approve is False
    assert response.authority["veto"] == ["unsafe_change"]
    assert response.specialist_profile is not None
    assert response.specialist_profile.display_name == "Security Reviewer"


def test_capability_response_exposes_verification_methods() -> None:
    now = datetime.now(timezone.utc)
    capability = ArceusCapability(
        id=uuid.uuid4(),
        capability_key="quality.build_verification",
        domain="Quality",
        name="Build Verification",
        description="Run deterministic build checks and collect evidence.",
        verification_methods=["build_exit_code", "artifact_presence"],
        active=True,
        created_at=now,
        updated_at=now,
        version_number=2,
    )

    response = _capability_response(capability)

    assert response is not None
    assert response.capability_key == "quality.build_verification"
    assert response.domain == "Quality"
    assert response.verification_methods == ["build_exit_code", "artifact_presence"]


def test_model_execution_response_exposes_cost_latency_and_prompt_hash_only() -> None:
    now = datetime.now(timezone.utc)
    execution = ArceusModelExecution(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        mission_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        provider="openai",
        model="gpt-5-codex",
        purpose="implementation_planning",
        prompt_hash="sha256:abc123",
        input_tokens=1200,
        output_tokens=340,
        cost_usd="0.042000",
        latency_ms=1800,
        status="succeeded",
        error={},
        created_at=now,
        updated_at=now,
        version_number=1,
    )

    response = _model_execution_response(execution)

    assert response.provider == "openai"
    assert response.model == "gpt-5-codex"
    assert response.prompt_hash == "sha256:abc123"
    assert response.input_tokens == 1200
    assert response.output_tokens == 340
    assert response.latency_ms == 1800
    assert not hasattr(response, "prompt")


def test_replay_event_response_preserves_ordering_metadata() -> None:
    mission_id = uuid.uuid4()
    event = ArceusEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=7,
        event_type="arceus.mission.compiled",
        actor_type="system",
        actor_id="compiler",
        payload={"status": "compiled"},
        metadata_json={"correlation_id": "corr-1"},
        occurred_at=datetime.now(timezone.utc),
    )

    response = _replay_event_response(event)

    assert response.aggregate_id == mission_id
    assert response.aggregate_version == 7
    assert response.event_type == "arceus.mission.compiled"
    assert response.payload["status"] == "compiled"
    assert response.metadata_json["correlation_id"] == "corr-1"


def test_usage_summary_groups_quantity_and_cost_by_type() -> None:
    tenant_id = uuid.uuid4()
    records = [
        SimpleNamespace(usage_type="model_tokens", quantity=Decimal("100.0"), unit="tokens", cost_usd=Decimal("0.010000")),
        SimpleNamespace(usage_type="model_tokens", quantity=Decimal("50.0"), unit="tokens", cost_usd=Decimal("0.005000")),
        SimpleNamespace(usage_type="tool_run", quantity=Decimal("1.0"), unit="run", cost_usd=Decimal("0.000000")),
    ]

    class _UsageRepo(UsageRepository):
        def __init__(self):
            pass

        def list(self, **kwargs):
            assert kwargs["tenant_id"] == tenant_id
            return records

    summary = _UsageRepo().summarize(tenant_id=tenant_id)

    assert summary["record_count"] == 3
    assert summary["cost_usd"] == Decimal("0.015000")
    grouped = {item["usage_type"]: item for item in summary["by_type"]}
    assert grouped["model_tokens"]["quantity"] == Decimal("150.0")
    assert grouped["model_tokens"]["cost_usd"] == Decimal("0.015000")
    assert grouped["tool_run"]["record_count"] == 1


def test_runtime_health_classification_distinguishes_blockers_from_warnings() -> None:
    degraded, blockers, warnings = classify_runtime_health(
        {
            "outbox_statuses": {},
            "task_statuses": {"blocked": 1},
            "approval_statuses": {"pending": 2},
            "stale_processing_outbox": 0,
        }
    )
    assert degraded == "degraded"
    assert blockers == []
    assert set(warnings) == {"blocked_tasks", "pending_approvals"}

    blocked, blockers, warnings = classify_runtime_health(
        {
            "outbox_statuses": {"dead_letter": 1},
            "task_statuses": {},
            "approval_statuses": {},
            "stale_processing_outbox": 0,
        }
    )
    assert blocked == "blocked"
    assert blockers == ["dead_letter_outbox_messages"]
