from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusMissionConstraint,
    ArceusMissionRequirement,
    ArceusMissionSuccessCriterion,
    ArceusMissionUnknown,
    ArceusMissionVersion,
)

from ...os_kernel.mission_compiler import MissionCompileRequest, MissionCompiler
from ..application.errors import MissionStateConflict, MissionVersionConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.contracts import CompileMissionInput, RepositoryScope
from ..compiler.service import MissionCompilerService


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MissionCompilationWorker:
    """Synchronous worker implementation for the durable compilation use case.

    The outbox loop can call this class after claiming an
    arceus.mission.compilation.requested message. Tests and local tools can call
    it directly while Celery/Redis orchestration matures.
    """

    def __init__(self, db: Session, compiler: MissionCompiler | None = None) -> None:
        self.uow = SqlAlchemyUnitOfWork(db)
        self.compiler = compiler or MissionCompiler()

    def process(self, *, tenant_id: UUID, mission_id: UUID, started_version: int | None = None) -> dict[str, Any]:
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        if mission.status != "compiling":
            raise MissionStateConflict(
                "Mission compilation can only run while the mission is compiling.",
                details={"current_state": mission.status},
            )
        if started_version is not None and int(mission.version_number) != int(started_version):
            raise MissionVersionConflict(
                "Stale compilation work cannot overwrite a newer mission.",
                details={"started_version": started_version, "current_version": mission.version_number},
            )

        constraints = self.uow.missions.constraints(tenant_id=tenant_id, mission_id=mission_id)
        success_criteria = self.uow.missions.success_criteria(tenant_id=tenant_id, mission_id=mission_id)
        repository_ids = self.uow.missions.repository_scope_ids(tenant_id=tenant_id, mission_id=mission_id)
        repositories = self.uow.projects.get_repositories(
            tenant_id=tenant_id,
            project_id=mission.project_id,
            repository_ids=repository_ids,
        )
        compiler_run = MissionCompilerService(self.uow).compile(
            CompileMissionInput(
                tenant_id=tenant_id,
                mission_id=mission.id,
                project_id=mission.project_id,
                actor_id="mission-compiler",
                source_mission_version=int(mission.version_number),
                objective=mission.objective,
                repository_scopes=tuple(
                    RepositoryScope(
                        repository_id=repository.id,
                        provider=repository.provider,
                        repository_url=repository.repository_url,
                        base_ref=repository.default_branch,
                    )
                    for repository in repositories
                ),
                constraints=tuple(item.statement for item in constraints),
                desired_outcomes=tuple(item.statement for item in success_criteria),
                budget={
                    "currency": mission.budget_currency,
                    "maximum": str(mission.maximum_budget_amount) if mission.maximum_budget_amount is not None else None,
                },
            )
        )
        compiled = self.compiler.compile(
            MissionCompileRequest(
                tenant_id=str(tenant_id),
                actor_id="mission-compiler",
                project_id=str(mission.project_id),
                objective=mission.objective,
                repository_ids=[str(item) for item in repository_ids],
                constraints=[item.statement for item in constraints],
                desired_outcomes=[item.statement for item in success_criteria],
                budget={
                    "currency": mission.budget_currency,
                    "maximum": str(mission.maximum_budget_amount) if mission.maximum_budget_amount is not None else None,
                },
            )
        )
        definition = compiled.definition
        source_payload = {
            "mission_id": str(mission.id),
            "objective": mission.objective,
            "constraints": [item.statement for item in constraints],
            "success_criteria": [item.statement for item in success_criteria],
            "repository_ids": [str(item) for item in repository_ids],
            "compiled": definition.to_dict(),
        }
        mission_version = ArceusMissionVersion(
            tenant_id=tenant_id,
            mission_id=mission.id,
            version=int(mission.version_number),
            compiled_by=None,
            objective_snapshot=mission.objective,
            mission_contract=definition.to_aml(),
            intent_frame=compiled.intent.to_dict(),
            risk_profile=definition.risk_profile.to_dict(),
            execution_graph=definition.execution_graph.to_dict(),
            source_hash=_stable_hash(source_payload),
        )
        self.uow.db.add(mission_version)
        self.uow.db.flush()
        compiler_run_record = self.uow.compiler_runs.get(tenant_id=tenant_id, compiler_run_id=compiler_run.compiler_run_id)
        self.uow.compiler_runs.finish(
            compiler_run_record,
            status="clarification_required" if compiled.state == "CLARIFICATION_REQUIRED" else "compiled",
            compiled_mission_version_id=mission_version.id,
            warning_codes=list(compiler_run.warning_codes),
        )
        mission.current_version_id = mission_version.id
        mission.risk_level = definition.risk_profile.level
        mission.status = "clarification_required" if compiled.state == "CLARIFICATION_REQUIRED" else "compiled"
        mission.version_number = int(mission.version_number) + 1

        self._replace_compiled_records(tenant_id=tenant_id, mission_id=mission.id, definition=definition)
        event_type = "MISSION_CLARIFICATION_REQUIRED" if mission.status == "clarification_required" else "MISSION_COMPILED"
        topic = "arceus.mission.clarification.required" if mission.status == "clarification_required" else "arceus.mission.compiled"
        event = self.uow.events.append(
            tenant_id=tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=mission.version_number,
            event_type=event_type,
            actor_type="system",
            actor_id="mission-compiler",
            payload={
                "mission_id": str(mission.id),
                "mission_version_id": str(mission_version.id),
                "status": mission.status,
                "unknowns": definition.unknowns,
                "required_capabilities": definition.required_capabilities,
            },
            correlation_id=mission.id,
            idempotency_key=f"mission-compile-result:{mission.id}:{mission.version_number}:{uuid.uuid4()}",
        )
        self.uow.outbox.add_from_event(event, topic=topic)
        self.uow.audit.record(
            tenant_id=tenant_id,
            actor_id=mission.created_by,
            action="mission.compile.worker",
            resource_type="mission",
            resource_id=mission.id,
            result="success",
            metadata={"status": mission.status, "mission_version_id": str(mission_version.id)},
        )
        self.uow.commit()
        return {
            "mission_id": str(mission.id),
            "mission_version_id": str(mission_version.id),
            "status": mission.status,
            "version_number": mission.version_number,
            "clarification_required": mission.status == "clarification_required",
        }

    def _replace_compiled_records(self, *, tenant_id: UUID, mission_id: UUID, definition) -> None:
        self.uow.db.query(ArceusMissionRequirement).filter(
            ArceusMissionRequirement.tenant_id == tenant_id,
            ArceusMissionRequirement.mission_id == mission_id,
        ).delete(synchronize_session=False)
        self.uow.db.query(ArceusMissionUnknown).filter(
            ArceusMissionUnknown.tenant_id == tenant_id,
            ArceusMissionUnknown.mission_id == mission_id,
        ).delete(synchronize_session=False)

        for index, requirement in enumerate(definition.requirements, start=1):
            self.uow.db.add(
                ArceusMissionRequirement(
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    requirement_key=f"requirement_{index}",
                    statement=requirement,
                    source="compiler",
                    priority=3,
                    verified=False,
                )
            )
        for index, unknown in enumerate(definition.unknowns, start=1):
            self.uow.db.add(
                ArceusMissionUnknown(
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    question=unknown,
                    risk_if_unanswered="Compilation marked this as material to safe execution.",
                    status="open",
                )
            )
