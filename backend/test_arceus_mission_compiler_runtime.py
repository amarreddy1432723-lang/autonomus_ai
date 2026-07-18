import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from services.agent.arceus_runtime.application.errors import CompilerBudgetExceeded, CompilerRunStale
from services.agent.arceus_runtime.application.unit_of_work import SqlAlchemyUnitOfWork
from services.agent.arceus_runtime.compiler.approval_planning import ApprovalPlanningStage
from services.agent.arceus_runtime.compiler.capability_planning import CapabilityPlanningStage
from services.agent.arceus_runtime.compiler.contracts import CompileMissionInput, RepositoryScope
from services.agent.arceus_runtime.compiler.input_normalization import InputNormalizationStage
from services.agent.arceus_runtime.compiler.intent_classifier import IntentClassificationStage
from services.agent.arceus_runtime.compiler.objective_guard import ObjectiveBoundaryGuardStage
from services.agent.arceus_runtime.compiler.proposal import DeterministicProposalStage
from services.agent.arceus_runtime.compiler.requirement_planning import RequirementPlanningStage
from services.agent.arceus_runtime.compiler.risk_planning import RiskPlanningStage
from services.agent.arceus_runtime.compiler.service import MissionCompilerService
from services.agent.arceus_runtime.compiler.source_manifest import SourceManifestStage
from services.agent.arceus_runtime.compiler.stages import run_stage
from services.agent.arceus_runtime.compiler.unknown_planning import UnknownPlanningStage
from services.agent.arceus_runtime.compiler.verification_planning import VerificationPlanningStage
from services.shared.arceus_core_models import ArceusCompilerRun, ArceusEvent, ArceusMission, ArceusProject, ArceusTenant, ArceusUser
from services.shared.database import SessionLocal


def _compiled_stage_payload(objective: str, *, repository_scopes: list[dict] | None = None, constraints: list[str] | None = None) -> dict:
    source = {
        "objective": objective,
        "constraints": constraints or [],
        "desired_outcomes": ["Build evidence and update the work receipt."],
        "repository_scopes": (
            repository_scopes
            if repository_scopes is not None
            else [
            {
                "repository_id": "repo-1",
                "provider": "local",
                "repository_url": "file:///workspace",
                "base_ref": "main",
                "allowed_paths": [],
                "denied_paths": [],
            }
            ]
        ),
        "budget": {"currency": "USD", "maximum": "10.00"},
    }
    normalization = run_stage(InputNormalizationStage(), source)
    manifest = run_stage(SourceManifestStage(), {"source": source})
    intent = run_stage(IntentClassificationStage(), {"input_normalization": normalization.to_record()})
    guard = run_stage(
        ObjectiveBoundaryGuardStage(),
        {
            "input_normalization": normalization.to_record(),
            "intent_classification": intent.to_record(),
        },
    )
    requirements = run_stage(
        RequirementPlanningStage(),
        {
            "input_normalization": normalization.to_record(),
            "intent_classification": intent.to_record(),
        },
    )
    unknowns = run_stage(
        UnknownPlanningStage(),
        {
            "input_normalization": normalization.to_record(),
            "intent_classification": intent.to_record(),
            "objective_boundary_guard": guard.to_record(),
        },
    )
    risk = run_stage(
        RiskPlanningStage(),
        {
            "input_normalization": normalization.to_record(),
            "intent_classification": intent.to_record(),
        },
    )
    capabilities = run_stage(
        CapabilityPlanningStage(),
        {
            "intent_classification": intent.to_record(),
            "requirement_planning": requirements.to_record(),
            "risk_planning": risk.to_record(),
        },
    )
    verification = run_stage(
        VerificationPlanningStage(),
        {
            "intent_classification": intent.to_record(),
            "requirement_planning": requirements.to_record(),
            "risk_planning": risk.to_record(),
        },
    )
    approvals = run_stage(
        ApprovalPlanningStage(),
        {
            "risk_planning": risk.to_record(),
        },
    )
    proposal = run_stage(
        DeterministicProposalStage(),
        {
            "input_normalization": normalization.to_record(),
            "intent_classification": intent.to_record(),
            "objective_boundary_guard": guard.to_record(),
            "requirement_planning": requirements.to_record(),
            "unknown_planning": unknowns.to_record(),
            "risk_planning": risk.to_record(),
            "capability_planning": capabilities.to_record(),
            "verification_planning": verification.to_record(),
            "approval_planning": approvals.to_record(),
        },
    )
    return {
        "source_manifest": manifest,
        "input_normalization": normalization,
        "intent_classification": intent,
        "objective_boundary_guard": guard,
        "requirement_planning": requirements,
        "unknown_planning": unknowns,
        "risk_planning": risk,
        "capability_planning": capabilities,
        "verification_planning": verification,
        "approval_planning": approvals,
        "deterministic_proposal": proposal,
    }


def test_input_normalization_compacts_and_deduplicates_mission_inputs() -> None:
    result = run_stage(
        InputNormalizationStage(),
        {
            "objective": "  Add   an admin health-status card   ",
            "constraints": ["Use existing UI", "use existing ui", "  "],
            "desired_outcomes": ["Show Redis health", "Show Redis health"],
            "repository_scopes": [{"repository_id": "repo-1"}],
            "budget": {},
        },
    )

    normalized = result.output["normalized"]

    assert normalized["objective"] == "Add an admin health-status card"
    assert normalized["constraints"] == ["Use existing UI"]
    assert normalized["desired_outcomes"] == ["Show Redis health"]
    assert result.output_hash


def test_intent_classifier_derives_capabilities_from_objective() -> None:
    payload = _compiled_stage_payload("Add Clerk login and session health checks to the backend API")
    intent = payload["intent_classification"].output

    assert intent["primary_intent"] in {"authentication_change", "feature_development"}
    assert "authentication_review" in intent["required_capability_hints"]


def test_objective_guard_requires_clarification_for_missing_repository_scope() -> None:
    payload = _compiled_stage_payload("Add a safe health card to the admin page", repository_scopes=[])
    guard = payload["objective_boundary_guard"].output

    assert guard["boundary_status"] == "clarification_required"
    assert "repository_scope_missing" in guard["warning_codes"]
    assert guard["clarification_questions"]


def test_deterministic_proposal_lists_verification_and_approval_gates() -> None:
    payload = _compiled_stage_payload("Add a FastAPI health-status card for Redis readiness")
    proposal = payload["deterministic_proposal"].output["proposal"]

    assert proposal["objective"] == "Add a FastAPI health-status card for Redis readiness"
    assert proposal["required_capabilities"]
    assert "verification_plan" in proposal
    assert any(item["approval_key"] == "human_plan_approval" for item in proposal["approval_gates"])


def test_source_manifest_snapshot_is_stable_and_path_aware() -> None:
    payload = _compiled_stage_payload(
        "Add an admin health-status card",
        repository_scopes=[
            {
                "repository_id": "repo-1",
                "provider": "github",
                "repository_url": "https://github.com/example/app",
                "base_ref": "main",
                "allowed_paths": ["frontend/src/app/admin"],
                "denied_paths": [".env"],
            }
        ],
    )
    manifest = payload["source_manifest"].output

    assert manifest["source_manifest_id"]
    assert manifest["source_manifest"]["workspace_constraints"]["path_scoped"] is True
    assert manifest["source_manifest"]["workspace_constraints"]["has_denied_paths"] is True


def test_compiler_planning_stages_produce_requirements_risk_capabilities_and_verification() -> None:
    payload = _compiled_stage_payload("Add Clerk authentication and protect admin APIs")

    assert payload["requirement_planning"].output["requirements"][0]["requirement_key"] == "FR-001"
    assert payload["risk_planning"].output["risk_profile"]["requires_security_review"] is True
    assert "secure_code_review" in payload["capability_planning"].output["required_capabilities"]
    assert payload["verification_planning"].output["verification_plan"]
    assert any(item["approval_key"] == "security_review_when_risky" for item in payload["approval_planning"].output["approval_gates"])


class _FakeCompilerRuns:
    def __init__(self, mission) -> None:
        self.mission = mission
        self.run = None

    def create(self, *, tenant_id, mission_id, source_mission_version):
        self.run = SimpleNamespace(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            mission_id=mission_id,
            source_mission_version=source_mission_version,
            status="queued",
            current_stage=None,
            stage_results={},
            warning_codes=[],
            version_number=1,
            source_manifest_id=None,
        )
        return self.run

    def assert_source_version(self, *, mission, compiler_run) -> None:
        if int(mission.version_number) != int(compiler_run.source_mission_version):
            raise CompilerRunStale("stale")

    def start(self, compiler_run, *, stage: str) -> None:
        compiler_run.status = "running"
        compiler_run.current_stage = stage
        compiler_run.version_number += 1

    def record_stage(self, compiler_run, *, stage: str, result: dict) -> None:
        compiler_run.stage_results[stage] = result
        compiler_run.version_number += 1

    def finish(self, compiler_run, *, status, compiled_mission_version_id=None, warning_codes=None, error_code=None, error_message=None) -> None:
        compiler_run.status = status
        compiler_run.warning_codes = warning_codes or []
        compiler_run.error_code = error_code
        compiler_run.error_message = error_message
        compiler_run.version_number += 1


class _FakeEvents:
    def __init__(self) -> None:
        self.items = []

    def append(self, **kwargs):
        self.items.append(kwargs)


class _FakeMissions:
    def __init__(self, mission) -> None:
        self.mission = mission

    def get(self, *, tenant_id, mission_id):
        return self.mission


class _FakeUow:
    def __init__(self, *, mission_version: int = 1) -> None:
        self.mission = SimpleNamespace(id=uuid.uuid4(), version_number=mission_version)
        self.missions = _FakeMissions(self.mission)
        self.compiler_runs = _FakeCompilerRuns(self.mission)
        self.events = _FakeEvents()


def _compile_command(
    *,
    tenant_id,
    mission_id,
    source_version: int,
    compiler_budget: float | None = None,
    objective: str = "Add a FastAPI health-status card for Redis readiness",
) -> CompileMissionInput:
    budget = {"currency": "USD"}
    if compiler_budget is not None:
        budget["compiler_maximum_usd"] = compiler_budget
    return CompileMissionInput(
        tenant_id=tenant_id,
        mission_id=mission_id,
        project_id=uuid.uuid4(),
        actor_id="test",
        source_mission_version=source_version,
        objective=objective,
        repository_scopes=(
            RepositoryScope(
                repository_id=uuid.uuid4(),
                provider="local",
                repository_url="file:///workspace",
                base_ref="main",
            ),
        ),
        budget=budget,
    )


def test_compiler_budget_enforcement_fails_the_run() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(mission_version=1)

    with pytest.raises(CompilerBudgetExceeded):
        MissionCompilerService(uow).compile(_compile_command(tenant_id=tenant_id, mission_id=mission_id, source_version=1, compiler_budget=0.00001))

    assert uow.compiler_runs.run.status == "failed"
    assert uow.compiler_runs.run.error_code == "COMPILER_BUDGET_EXCEEDED"


def test_compiler_emits_stage_and_terminal_events() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(mission_version=1)

    result = MissionCompilerService(uow).compile(_compile_command(tenant_id=tenant_id, mission_id=mission_id, source_version=1))

    event_types = [item["event_type"] for item in uow.events.items]
    assert result.status == "compiled"
    assert "COMPILER_STAGE_COMPLETED" in event_types
    assert event_types[-1] == "COMPILER_RUN_FINISHED"
    assert uow.compiler_runs.run.source_manifest_id is not None


def test_compiler_stale_result_marks_run_stale_before_rethrow() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(mission_version=2)

    with pytest.raises(CompilerRunStale):
        MissionCompilerService(uow).compile(_compile_command(tenant_id=tenant_id, mission_id=mission_id, source_version=1))

    assert uow.compiler_runs.run.status == "stale"
    assert "compiler_run_stale" in uow.compiler_runs.run.warning_codes


def test_compiler_stale_recovery_persists_with_real_db_workflow() -> None:
    if os.getenv("ARCEUS_RUNTIME_DB_TESTS") != "1":
        pytest.skip("Set ARCEUS_RUNTIME_DB_TESTS=1 to run the real Postgres compiler workflow test.")

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    db = SessionLocal()

    try:
        db.add(ArceusTenant(id=tenant_id, name="Compiler Test Tenant", slug=f"compiler-test-{tenant_id}", status="active"))
        db.add(
            ArceusUser(
                id=user_id,
                external_identity_id=f"compiler-test-{user_id}",
                email=f"compiler-test-{user_id}@example.com",
                display_name="Compiler Test User",
                status="active",
            )
        )
        db.add(
            ArceusProject(
                id=project_id,
                tenant_id=tenant_id,
                name="Compiler Test Project",
                slug=f"compiler-test-{project_id}",
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
                title="Compile stale mission",
                objective="Add a FastAPI health-status card for Redis readiness",
                status="draft",
                version_number=2,
            )
        )
        db.commit()

        with pytest.raises(CompilerRunStale):
            MissionCompilerService(SqlAlchemyUnitOfWork(db)).compile(
                _compile_command(tenant_id=tenant_id, mission_id=mission_id, source_version=1)
            )
        db.commit()

        compiler_run = (
            db.query(ArceusCompilerRun)
            .filter(ArceusCompilerRun.tenant_id == tenant_id, ArceusCompilerRun.mission_id == mission_id)
            .one()
        )
        terminal_event = (
            db.query(ArceusEvent)
            .filter(
                ArceusEvent.tenant_id == tenant_id,
                ArceusEvent.aggregate_type == "compiler_run",
                ArceusEvent.aggregate_id == compiler_run.id,
                ArceusEvent.event_type == "COMPILER_RUN_FINISHED",
            )
            .one()
        )

        assert compiler_run.status == "stale"
        assert "compiler_run_stale" in compiler_run.warning_codes
        assert terminal_event.payload["status"] == "stale"
    except OperationalError as exc:
        pytest.skip(f"Real DB compiler workflow test skipped because the configured database is unavailable: {exc}")
    finally:
        db.rollback()
        try:
            db.query(ArceusEvent).filter(ArceusEvent.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusCompilerRun).filter(ArceusCompilerRun.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusProject).filter(ArceusProject.tenant_id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusTenant).filter(ArceusTenant.id == tenant_id).delete(synchronize_session=False)
            db.query(ArceusUser).filter(ArceusUser.id == user_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
