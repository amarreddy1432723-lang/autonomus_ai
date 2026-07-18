from __future__ import annotations

from typing import Any
from uuid import UUID

from .approval_planning import ApprovalPlanningStage
from .capability_planning import CapabilityPlanningStage
from .contracts import CompileMissionInput, CompilerRunResult
from .input_normalization import InputNormalizationStage
from .intent_classifier import IntentClassificationStage
from .objective_guard import ObjectiveBoundaryGuardStage
from .proposal import DeterministicProposalStage
from .requirement_planning import RequirementPlanningStage
from .risk_planning import RiskPlanningStage
from .source_manifest import SourceManifestStage
from .stages import compiler_input_payload, run_stage
from .unknown_planning import UnknownPlanningStage
from .verification_planning import VerificationPlanningStage
from ..application.errors import CompilerBudgetExceeded, CompilerRunStale
from ..application.unit_of_work import SqlAlchemyUnitOfWork


class MissionCompilerService:
    """Deterministic compiler shell with durable stage checkpoints."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.stages = (
            SourceManifestStage(),
            InputNormalizationStage(),
            IntentClassificationStage(),
            ObjectiveBoundaryGuardStage(),
            RequirementPlanningStage(),
            UnknownPlanningStage(),
            RiskPlanningStage(),
            CapabilityPlanningStage(),
            VerificationPlanningStage(),
            ApprovalPlanningStage(),
            DeterministicProposalStage(),
        )

    def compile(self, command: CompileMissionInput) -> CompilerRunResult:
        mission = self.uow.missions.get(tenant_id=command.tenant_id, mission_id=command.mission_id)
        compiler_run = self.uow.compiler_runs.create(
            tenant_id=command.tenant_id,
            mission_id=command.mission_id,
            source_mission_version=command.source_mission_version,
        )
        stage_payload: dict[str, Any] = {"source": compiler_input_payload(command)}
        warning_codes: set[str] = set()
        spent_usd = 0.0
        budget_limit = self._compiler_budget_limit(command.budget)

        try:
            self.uow.compiler_runs.assert_source_version(mission=mission, compiler_run=compiler_run)
            for stage in self.stages:
                self.uow.compiler_runs.start(compiler_run, stage=stage.stage_key)
                result = run_stage(stage, stage_payload)
                spent_usd += result.cost_usd
                if budget_limit is not None and spent_usd > budget_limit:
                    raise CompilerBudgetExceeded(
                        "Compiler budget exceeded.",
                        details={"budget_limit_usd": budget_limit, "spent_usd": spent_usd, "stage": stage.stage_key},
                    )
                self.uow.compiler_runs.record_stage(compiler_run, stage=stage.stage_key, result=result.to_record())
                if stage.stage_key == "source_manifest":
                    source_manifest_id = result.output.get("source_manifest_id")
                    if source_manifest_id:
                        compiler_run.source_manifest_id = UUID(str(source_manifest_id))
                stage_payload[stage.stage_key] = result.to_record()
                warning_codes.update(result.warning_codes)
                self._append_stage_event(
                    compiler_run=compiler_run,
                    stage_result=result.to_record(),
                    correlation_id=command.mission_id,
                )
                if result.status == "rejected":
                    break

            normalized = stage_payload["input_normalization"]["output"]["normalized"]
            intent = stage_payload["intent_classification"]["output"]
            guard = stage_payload.get("objective_boundary_guard", {}).get("output", {})
            proposal = stage_payload.get("deterministic_proposal", {}).get("output", {}).get("proposal", {})
            boundary_status = guard.get("boundary_status", "ok")
            terminal_status = {
                "ok": "compiled",
                "clarification_required": "clarification_required",
                "rejected": "rejected",
            }.get(boundary_status, "failed")
            self.uow.compiler_runs.finish(
                compiler_run,
                status=terminal_status,
                warning_codes=sorted(warning_codes),
                error_code=None if terminal_status in {"compiled", "clarification_required"} else guard.get("reason_code"),
                error_message=None if terminal_status in {"compiled", "clarification_required"} else "Mission objective failed compiler boundary checks.",
            )
            self._append_terminal_event(compiler_run=compiler_run, status=terminal_status, correlation_id=command.mission_id)
            return CompilerRunResult(
                compiler_run_id=compiler_run.id,
                status=terminal_status,
                normalized_objective=normalized["objective"],
                primary_intent=intent["primary_intent"],
                secondary_intents=tuple(intent.get("secondary_intents", [])),
                boundary_status=boundary_status,
                warning_codes=tuple(sorted(warning_codes)),
                clarification_questions=tuple(guard.get("clarification_questions", [])),
                proposal=proposal,
            )
        except CompilerRunStale:
            self.uow.compiler_runs.finish(
                compiler_run,
                status="stale",
                warning_codes=sorted({*warning_codes, "compiler_run_stale"}),
                error_code="COMPILER_RUN_STALE",
                error_message="Mission changed after this compiler run started.",
            )
            self._append_terminal_event(compiler_run=compiler_run, status="stale", correlation_id=command.mission_id)
            raise
        except Exception as exc:
            self.uow.compiler_runs.finish(
                compiler_run,
                status="failed",
                warning_codes=sorted(warning_codes),
                error_code=getattr(exc, "code", exc.__class__.__name__),
                error_message=str(exc),
            )
            self._append_terminal_event(compiler_run=compiler_run, status="failed", correlation_id=command.mission_id)
            raise

    def _compiler_budget_limit(self, budget: dict[str, Any]) -> float | None:
        raw = budget.get("compiler_maximum_usd", budget.get("compiler_maximum", None))
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _append_stage_event(self, *, compiler_run, stage_result: dict[str, Any], correlation_id) -> None:
        self.uow.events.append(
            tenant_id=compiler_run.tenant_id,
            aggregate_type="compiler_run",
            aggregate_id=compiler_run.id,
            aggregate_version=compiler_run.version_number,
            event_type="COMPILER_STAGE_COMPLETED",
            actor_type="system",
            actor_id="mission-compiler",
            payload={
                "compiler_run_id": str(compiler_run.id),
                "mission_id": str(compiler_run.mission_id),
                "stage": stage_result["stage"],
                "status": stage_result["status"],
                "input_hash": stage_result["input_hash"],
                "output_hash": stage_result["output_hash"],
                "duration_ms": stage_result["duration_ms"],
                "warning_codes": stage_result.get("warning_codes", []),
                "cost_usd": stage_result.get("cost_usd", 0.0),
            },
            correlation_id=correlation_id,
            idempotency_key=f"compiler-stage:{compiler_run.id}:{compiler_run.version_number}:{stage_result['stage']}",
        )

    def _append_terminal_event(self, *, compiler_run, status: str, correlation_id) -> None:
        self.uow.events.append(
            tenant_id=compiler_run.tenant_id,
            aggregate_type="compiler_run",
            aggregate_id=compiler_run.id,
            aggregate_version=compiler_run.version_number,
            event_type="COMPILER_RUN_FINISHED",
            actor_type="system",
            actor_id="mission-compiler",
            payload={"compiler_run_id": str(compiler_run.id), "mission_id": str(compiler_run.mission_id), "status": status},
            correlation_id=correlation_id,
            idempotency_key=f"compiler-finished:{compiler_run.id}:{compiler_run.version_number}:{status}",
        )
