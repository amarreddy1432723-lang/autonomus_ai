from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAuditEvent,
    ArceusApproval,
    ArceusApprovalVote,
    ArceusArtifact,
    ArceusArtifactVersion,
    ArceusCapability,
    ArceusCompilerRun,
    ArceusContextPackage,
    ArceusDecision,
    ArceusEvidence,
    ArceusEvent,
    ArceusIdempotencyRecord,
    ArceusMission,
    ArceusMissionOrganization,
    ArceusMissionConstraint,
    ArceusMissionRepositoryScope,
    ArceusMissionRequiredCapability,
    ArceusMissionSuccessCriterion,
    ArceusMissionUnknown,
    ArceusModelExecution,
    ArceusOrganizationMember,
    ArceusOutboxMessage,
    ArceusProject,
    ArceusProjectRepository,
    ArceusSpecialistCapability,
    ArceusSpecialistProfile,
    ArceusTask,
    ArceusTaskAttempt,
    ArceusTaskDependency,
    ArceusToolDefinition,
    ArceusToolExecution,
    ArceusPolicyEvaluation,
    ArceusRuntimeCheckpoint,
    ArceusUsageRecord,
    ArceusVerificationRun,
    ArceusWorkerLease,
    ArceusWorkflowDefinition,
    ArceusWorkflowEdge,
    ArceusWorkflowNode,
)

from .errors import (
    AuditEventNotFound,
    ArtifactNotFound,
    ApprovalNotFound,
    CapabilityNotFound,
    CompilerRunNotFound,
    CompilerRunStale,
    CompilerRunStateConflict,
    ContextPackageNotFound,
    DecisionNotFound,
    EvidenceNotFound,
    IdempotencyConflict,
    MissionNotFound,
    MissionVersionConflict,
    ModelExecutionNotFound,
    OrganizationMemberNotFound,
    OrganizationNotFound,
    ProjectNotFound,
    TaskNotFound,
    TaskStateConflict,
    ToolExecutionNotFound,
    PolicyEvaluationNotFound,
    RuntimeStateConflict,
    UsageRecordNotFound,
    VerificationRunNotFound,
    WorkerLeaseNotFound,
)


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, *, tenant_id: UUID, project_id: UUID) -> ArceusProject:
        project = (
            self.db.query(ArceusProject)
            .filter(ArceusProject.tenant_id == tenant_id, ArceusProject.id == project_id)
            .first()
        )
        if project is None:
            raise ProjectNotFound("Project not found.")
        return project

    def get_repositories(self, *, tenant_id: UUID, project_id: UUID, repository_ids: list[UUID]) -> list[ArceusProjectRepository]:
        repos = (
            self.db.query(ArceusProjectRepository)
            .filter(
                ArceusProjectRepository.tenant_id == tenant_id,
                ArceusProjectRepository.project_id == project_id,
                ArceusProjectRepository.id.in_(repository_ids),
            )
            .all()
        )
        if len(repos) != len(set(repository_ids)):
            raise ProjectNotFound("One or more repositories were not found for this project.")
        return repos


class MissionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, mission: ArceusMission) -> None:
        self.db.add(mission)

    def get(self, *, tenant_id: UUID, mission_id: UUID) -> ArceusMission:
        mission = (
            self.db.query(ArceusMission)
            .filter(ArceusMission.tenant_id == tenant_id, ArceusMission.id == mission_id)
            .first()
        )
        if mission is None:
            raise MissionNotFound("Mission not found.")
        return mission

    def list(self, *, tenant_id: UUID, project_id: UUID | None = None, status: str | None = None, limit: int = 50) -> list[ArceusMission]:
        query = self.db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id)
        if project_id:
            query = query.filter(ArceusMission.project_id == project_id)
        if status:
            query = query.filter(ArceusMission.status == status)
        return query.order_by(ArceusMission.updated_at.desc(), ArceusMission.id.desc()).limit(min(limit, 100)).all()

    def require_version(self, mission: ArceusMission, expected_version: int) -> None:
        if int(mission.version_number) != int(expected_version):
            raise MissionVersionConflict(
                "The mission changed after this page was loaded.",
                details={"expected_version": expected_version, "current_version": mission.version_number},
            )

    def add_repository_scope(self, *, tenant_id: UUID, mission_id: UUID, repository_id: UUID) -> None:
        self.db.add(
            ArceusMissionRepositoryScope(
                tenant_id=tenant_id,
                mission_id=mission_id,
                repository_id=repository_id,
                allowed_paths=[],
                denied_paths=[],
                scope_reason="Requested when mission was created.",
            )
        )

    def add_constraint(self, *, tenant_id: UUID, mission_id: UUID, key: str, statement: str) -> None:
        self.db.add(
            ArceusMissionConstraint(
                tenant_id=tenant_id,
                mission_id=mission_id,
                constraint_key=key,
                statement=statement,
                severity="required",
            )
        )

    def add_success_criterion(self, *, tenant_id: UUID, mission_id: UUID, key: str, statement: str) -> None:
        self.db.add(
            ArceusMissionSuccessCriterion(
                tenant_id=tenant_id,
                mission_id=mission_id,
                criterion_key=key,
                statement=statement,
                verification_method="manual_review",
                required=True,
            )
        )

    def repository_scope_ids(self, *, tenant_id: UUID, mission_id: UUID) -> list[UUID]:
        return [
            row.repository_id
            for row in self.db.query(ArceusMissionRepositoryScope)
            .filter(ArceusMissionRepositoryScope.tenant_id == tenant_id, ArceusMissionRepositoryScope.mission_id == mission_id)
            .all()
        ]

    def constraints(self, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusMissionConstraint]:
        return (
            self.db.query(ArceusMissionConstraint)
            .filter(ArceusMissionConstraint.tenant_id == tenant_id, ArceusMissionConstraint.mission_id == mission_id)
            .order_by(ArceusMissionConstraint.created_at.asc())
            .all()
        )

    def success_criteria(self, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusMissionSuccessCriterion]:
        return (
            self.db.query(ArceusMissionSuccessCriterion)
            .filter(ArceusMissionSuccessCriterion.tenant_id == tenant_id, ArceusMissionSuccessCriterion.mission_id == mission_id)
            .order_by(ArceusMissionSuccessCriterion.created_at.asc())
            .all()
        )

    def unknowns(self, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusMissionUnknown]:
        return (
            self.db.query(ArceusMissionUnknown)
            .filter(ArceusMissionUnknown.tenant_id == tenant_id, ArceusMissionUnknown.mission_id == mission_id)
            .order_by(ArceusMissionUnknown.created_at.asc())
            .all()
        )

    def get_unknowns_by_ids(self, *, tenant_id: UUID, mission_id: UUID, unknown_ids: list[UUID]) -> list[ArceusMissionUnknown]:
        return (
            self.db.query(ArceusMissionUnknown)
            .filter(
                ArceusMissionUnknown.tenant_id == tenant_id,
                ArceusMissionUnknown.mission_id == mission_id,
                ArceusMissionUnknown.id.in_(unknown_ids),
            )
            .all()
        )


class CompilerRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, compiler_run: ArceusCompilerRun) -> None:
        self.db.add(compiler_run)

    def get(self, *, tenant_id: UUID, compiler_run_id: UUID) -> ArceusCompilerRun:
        compiler_run = (
            self.db.query(ArceusCompilerRun)
            .filter(ArceusCompilerRun.tenant_id == tenant_id, ArceusCompilerRun.id == compiler_run_id)
            .first()
        )
        if compiler_run is None:
            raise CompilerRunNotFound("Compiler run not found.")
        return compiler_run

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusCompilerRun]:
        query = self.db.query(ArceusCompilerRun).filter(
            ArceusCompilerRun.tenant_id == tenant_id,
            ArceusCompilerRun.mission_id == mission_id,
        )
        if status:
            query = query.filter(ArceusCompilerRun.status == status)
        return query.order_by(ArceusCompilerRun.created_at.desc(), ArceusCompilerRun.id.desc()).limit(min(limit, 100)).all()

    def latest_for_mission(self, *, tenant_id: UUID, mission_id: UUID) -> ArceusCompilerRun | None:
        return (
            self.db.query(ArceusCompilerRun)
            .filter(ArceusCompilerRun.tenant_id == tenant_id, ArceusCompilerRun.mission_id == mission_id)
            .order_by(ArceusCompilerRun.created_at.desc(), ArceusCompilerRun.id.desc())
            .first()
        )

    def create(self, *, tenant_id: UUID, mission_id: UUID, source_mission_version: int) -> ArceusCompilerRun:
        compiler_run = ArceusCompilerRun(
            tenant_id=tenant_id,
            mission_id=mission_id,
            source_mission_version=source_mission_version,
            status="queued",
            stage_results={},
            model_execution_ids=[],
            warning_codes=[],
        )
        self.db.add(compiler_run)
        self.db.flush()
        return compiler_run

    def start(self, compiler_run: ArceusCompilerRun, *, stage: str) -> None:
        if compiler_run.status not in {"queued", "running"}:
            raise CompilerRunStateConflict(
                "Compiler run cannot be started from its current state.",
                details={"status": compiler_run.status},
            )
        compiler_run.status = "running"
        compiler_run.current_stage = stage
        compiler_run.started_at = compiler_run.started_at or datetime.now(timezone.utc)
        compiler_run.version_number = int(compiler_run.version_number) + 1

    def record_stage(self, compiler_run: ArceusCompilerRun, *, stage: str, result: dict[str, Any]) -> None:
        if compiler_run.status != "running":
            raise CompilerRunStateConflict(
                "Compiler stage results can only be recorded for a running compiler run.",
                details={"status": compiler_run.status},
            )
        stage_results = dict(compiler_run.stage_results or {})
        stage_results[stage] = result
        compiler_run.stage_results = stage_results
        compiler_run.current_stage = stage
        compiler_run.version_number = int(compiler_run.version_number) + 1

    def finish(
        self,
        compiler_run: ArceusCompilerRun,
        *,
        status: str,
        compiled_mission_version_id: UUID | None = None,
        warning_codes: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in {"clarification_required", "compiled", "rejected", "failed", "stale", "cancelled"}:
            raise CompilerRunStateConflict("Unsupported compiler run terminal state.", details={"status": status})
        compiler_run.status = status
        compiler_run.current_stage = None
        compiler_run.completed_at = datetime.now(timezone.utc)
        compiler_run.compiled_mission_version_id = compiled_mission_version_id
        compiler_run.warning_codes = warning_codes or list(compiler_run.warning_codes or [])
        compiler_run.error_code = error_code
        compiler_run.error_message = error_message
        compiler_run.version_number = int(compiler_run.version_number) + 1

    def assert_source_version(self, *, mission: ArceusMission, compiler_run: ArceusCompilerRun) -> None:
        if int(mission.version_number) != int(compiler_run.source_mission_version):
            raise CompilerRunStale(
                "Compiler run is stale because the mission changed after it started.",
                details={
                    "compiler_run_id": str(compiler_run.id),
                    "source_mission_version": compiler_run.source_mission_version,
                    "current_mission_version": mission.version_number,
                },
            )


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(
        self,
        *,
        tenant_id: UUID,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        event_type: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ArceusEvent:
        event = ArceusEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
            metadata_json={"correlation_id": str(correlation_id), "idempotency_key": idempotency_key},
        )
        self.db.add(event)
        self.db.flush()
        return event

    def list_for_mission(self, *, tenant_id: UUID, mission_id: UUID, limit: int = 20) -> list[ArceusEvent]:
        return (
            self.db.query(ArceusEvent)
            .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
            .order_by(ArceusEvent.aggregate_version.desc())
            .limit(limit)
            .all()
        )

    def list_for_mission_after(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        after_version: int = 0,
        limit: int = 50,
    ) -> list[ArceusEvent]:
        return (
            self.db.query(ArceusEvent)
            .filter(
                ArceusEvent.tenant_id == tenant_id,
                ArceusEvent.aggregate_type == "mission",
                ArceusEvent.aggregate_id == mission_id,
                ArceusEvent.aggregate_version > after_version,
            )
            .order_by(ArceusEvent.aggregate_version.asc())
            .limit(limit)
            .all()
        )

    def replay_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        from_version: int = 1,
        to_version: int | None = None,
        limit: int = 500,
    ) -> list[ArceusEvent]:
        query = self.db.query(ArceusEvent).filter(
            ArceusEvent.tenant_id == tenant_id,
            ArceusEvent.aggregate_type == "mission",
            ArceusEvent.aggregate_id == mission_id,
            ArceusEvent.aggregate_version >= from_version,
        )
        if to_version is not None:
            query = query.filter(ArceusEvent.aggregate_version <= to_version)
        return query.order_by(ArceusEvent.aggregate_version.asc()).limit(min(limit, 1000)).all()


class OutboxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_from_event(self, event: ArceusEvent, *, topic: str) -> ArceusOutboxMessage:
        message = ArceusOutboxMessage(
            tenant_id=event.tenant_id,
            event_id=event.id,
            topic=topic,
            payload={
                "event_id": str(event.id),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "event_type": event.event_type,
            },
        )
        self.db.add(message)
        return message

    def claim_batch(self, *, worker_id: str, limit: int = 50) -> list[ArceusOutboxMessage]:
        now = datetime.now(timezone.utc)
        messages = (
            self.db.query(ArceusOutboxMessage)
            .filter(
                ArceusOutboxMessage.status.in_(["pending", "failed"]),
                ArceusOutboxMessage.next_attempt_at <= now,
            )
            .order_by(ArceusOutboxMessage.created_at.asc())
            .limit(limit)
            .all()
        )
        for message in messages:
            message.status = "processing"
            message.locked_by = worker_id
            message.locked_at = now
            message.attempts = int(message.attempts or 0) + 1
        self.db.flush()
        return messages

    def mark_sent(self, message: ArceusOutboxMessage) -> None:
        message.status = "sent"
        message.sent_at = datetime.now(timezone.utc)
        message.locked_by = None
        message.locked_at = None

    def mark_failed(self, message: ArceusOutboxMessage, *, error: str, retry_delay_seconds: int) -> None:
        message.status = "failed"
        message.last_error = error[:2000]
        message.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds)
        message.locked_by = None
        message.locked_at = None

    def move_to_dead_letter(self, message: ArceusOutboxMessage, *, error: str) -> None:
        message.status = "dead_letter"
        message.last_error = error[:2000]
        message.locked_by = None
        message.locked_at = None


class IdempotencyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, *, tenant_id: UUID, scope: str, idempotency_key: str) -> ArceusIdempotencyRecord | None:
        return (
            self.db.query(ArceusIdempotencyRecord)
            .filter(
                ArceusIdempotencyRecord.tenant_id == tenant_id,
                ArceusIdempotencyRecord.scope == scope,
                ArceusIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .first()
        )

    def resolve_existing(self, record: ArceusIdempotencyRecord, request_hash: str) -> dict[str, Any]:
        if record.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key was already used with a different payload.")
        return record.response_payload or {}

    def complete(
        self,
        *,
        tenant_id: UUID,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        response_payload: dict[str, Any],
    ) -> None:
        self.db.add(
            ArceusIdempotencyRecord(
                tenant_id=tenant_id,
                scope=scope,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                status="completed",
            )
        )


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID | str | None,
        result: str,
        metadata: dict[str, Any],
    ) -> None:
        self.db.add(
            ArceusAuditEvent(
                tenant_id=tenant_id,
                actor_type="human",
                actor_id=str(actor_id),
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                result=result,
                metadata_json=metadata,
            )
        )

    def list(
        self,
        *,
        tenant_id: UUID,
        actor_type: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        result: str | None = None,
        limit: int = 100,
    ) -> list[ArceusAuditEvent]:
        query = self.db.query(ArceusAuditEvent).filter(ArceusAuditEvent.tenant_id == tenant_id)
        if actor_type:
            query = query.filter(ArceusAuditEvent.actor_type == actor_type)
        if actor_id:
            query = query.filter(ArceusAuditEvent.actor_id == actor_id)
        if action:
            query = query.filter(ArceusAuditEvent.action == action)
        if resource_type:
            query = query.filter(ArceusAuditEvent.resource_type == resource_type)
        if resource_id:
            query = query.filter(ArceusAuditEvent.resource_id == resource_id)
        if result:
            query = query.filter(ArceusAuditEvent.result == result)
        return query.order_by(ArceusAuditEvent.occurred_at.desc(), ArceusAuditEvent.id.desc()).limit(min(limit, 500)).all()

    def get(self, *, tenant_id: UUID, audit_event_id: UUID) -> ArceusAuditEvent:
        event = self.db.query(ArceusAuditEvent).filter(ArceusAuditEvent.tenant_id == tenant_id, ArceusAuditEvent.id == audit_event_id).first()
        if event is None:
            raise AuditEventNotFound("Audit event not found.")
        return event


class ApprovalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, tenant_id: UUID, mission_id: UUID | None = None, status: str | None = None, limit: int = 50) -> list[ArceusApproval]:
        query = self.db.query(ArceusApproval).filter(ArceusApproval.tenant_id == tenant_id)
        if mission_id:
            query = query.filter(ArceusApproval.mission_id == mission_id)
        if status:
            query = query.filter(ArceusApproval.status == status)
        return query.order_by(ArceusApproval.created_at.desc(), ArceusApproval.id.desc()).limit(min(limit, 100)).all()

    def get(self, *, tenant_id: UUID, approval_id: UUID) -> ArceusApproval:
        approval = (
            self.db.query(ArceusApproval)
            .filter(ArceusApproval.tenant_id == tenant_id, ArceusApproval.id == approval_id)
            .first()
        )
        if approval is None:
            raise ApprovalNotFound("Approval not found.")
        return approval

    def votes(self, *, tenant_id: UUID, approval_id: UUID) -> list[ArceusApprovalVote]:
        return (
            self.db.query(ArceusApprovalVote)
            .filter(ArceusApprovalVote.tenant_id == tenant_id, ArceusApprovalVote.approval_id == approval_id)
            .order_by(ArceusApprovalVote.created_at.asc())
            .all()
        )

    def add_vote(self, *, tenant_id: UUID, approval_id: UUID, voter_user_id: UUID, vote: str, comment: str | None, is_human_vote: bool) -> ArceusApprovalVote:
        approval_vote = ArceusApprovalVote(
            tenant_id=tenant_id,
            approval_id=approval_id,
            voter_user_id=voter_user_id,
            vote=vote,
            comment=comment,
            is_human_vote=is_human_vote,
        )
        self.db.add(approval_vote)
        self.db.flush()
        return approval_vote


class WorkflowRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_mission(self, *, tenant_id: UUID, mission_id: UUID) -> ArceusWorkflowDefinition | None:
        return (
            self.db.query(ArceusWorkflowDefinition)
            .filter(ArceusWorkflowDefinition.tenant_id == tenant_id, ArceusWorkflowDefinition.mission_id == mission_id)
            .order_by(ArceusWorkflowDefinition.created_at.desc(), ArceusWorkflowDefinition.id.desc())
            .first()
        )

    def add(self, workflow: ArceusWorkflowDefinition) -> None:
        self.db.add(workflow)

    def add_node(self, node: ArceusWorkflowNode) -> None:
        self.db.add(node)

    def add_edge(self, edge: ArceusWorkflowEdge) -> None:
        self.db.add(edge)

    def activate_for_mission(self, *, tenant_id: UUID, mission_id: UUID) -> None:
        organization = (
            self.db.query(ArceusMissionOrganization)
            .filter(ArceusMissionOrganization.tenant_id == tenant_id, ArceusMissionOrganization.mission_id == mission_id)
            .first()
        )
        if organization is not None:
            organization.status = "active"

        workflow = (
            self.db.query(ArceusWorkflowDefinition)
            .filter(ArceusWorkflowDefinition.tenant_id == tenant_id, ArceusWorkflowDefinition.mission_id == mission_id)
            .first()
        )
        if workflow is not None:
            workflow.status = "approved"


class ArtifactRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        artifact_type: str | None = None,
        limit: int = 50,
    ) -> list[ArceusArtifact]:
        query = self.db.query(ArceusArtifact).filter(
            ArceusArtifact.tenant_id == tenant_id,
            ArceusArtifact.mission_id == mission_id,
        )
        if artifact_type:
            query = query.filter(ArceusArtifact.artifact_type == artifact_type)
        return query.order_by(ArceusArtifact.updated_at.desc(), ArceusArtifact.id.desc()).limit(min(limit, 100)).all()

    def get(self, *, tenant_id: UUID, artifact_id: UUID) -> ArceusArtifact:
        artifact = (
            self.db.query(ArceusArtifact)
            .filter(ArceusArtifact.tenant_id == tenant_id, ArceusArtifact.id == artifact_id)
            .first()
        )
        if artifact is None:
            raise ArtifactNotFound("Artifact not found.")
        return artifact

    def versions(self, *, tenant_id: UUID, artifact_id: UUID) -> list[ArceusArtifactVersion]:
        self.get(tenant_id=tenant_id, artifact_id=artifact_id)
        return (
            self.db.query(ArceusArtifactVersion)
            .filter(ArceusArtifactVersion.tenant_id == tenant_id, ArceusArtifactVersion.artifact_id == artifact_id)
            .order_by(ArceusArtifactVersion.version.desc())
            .all()
        )

    def get_version(self, *, tenant_id: UUID, version_id: UUID) -> ArceusArtifactVersion:
        version = (
            self.db.query(ArceusArtifactVersion)
            .filter(ArceusArtifactVersion.tenant_id == tenant_id, ArceusArtifactVersion.id == version_id)
            .first()
        )
        if version is None:
            raise ArtifactNotFound("Artifact version not found.")
        return version


class EvidenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        evidence_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusEvidence]:
        query = self.db.query(ArceusEvidence).filter(
            ArceusEvidence.tenant_id == tenant_id,
            ArceusEvidence.mission_id == mission_id,
        )
        if evidence_type:
            query = query.filter(ArceusEvidence.evidence_type == evidence_type)
        if status:
            query = query.filter(ArceusEvidence.status == status)
        return query.order_by(ArceusEvidence.created_at.desc(), ArceusEvidence.id.desc()).limit(min(limit, 100)).all()

    def get(self, *, tenant_id: UUID, evidence_id: UUID) -> ArceusEvidence:
        evidence = (
            self.db.query(ArceusEvidence)
            .filter(ArceusEvidence.tenant_id == tenant_id, ArceusEvidence.id == evidence_id)
            .first()
        )
        if evidence is None:
            raise EvidenceNotFound("Evidence not found.")
        return evidence


class VerificationRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        verification_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusVerificationRun]:
        query = self.db.query(ArceusVerificationRun).filter(
            ArceusVerificationRun.tenant_id == tenant_id,
            ArceusVerificationRun.mission_id == mission_id,
        )
        if verification_type:
            query = query.filter(ArceusVerificationRun.verification_type == verification_type)
        if status:
            query = query.filter(ArceusVerificationRun.status == status)
        return query.order_by(ArceusVerificationRun.started_at.desc(), ArceusVerificationRun.id.desc()).limit(min(limit, 100)).all()

    def get(self, *, tenant_id: UUID, verification_run_id: UUID) -> ArceusVerificationRun:
        verification_run = (
            self.db.query(ArceusVerificationRun)
            .filter(ArceusVerificationRun.tenant_id == tenant_id, ArceusVerificationRun.id == verification_run_id)
            .first()
        )
        if verification_run is None:
            raise VerificationRunNotFound("Verification run not found.")
        return verification_run


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        status: str | None = None,
        owner_member_id: UUID | None = None,
        limit: int = 100,
    ) -> list[ArceusTask]:
        query = self.db.query(ArceusTask).filter(
            ArceusTask.tenant_id == tenant_id,
            ArceusTask.mission_id == mission_id,
        )
        if status:
            query = query.filter(ArceusTask.status == status)
        if owner_member_id:
            query = query.filter(ArceusTask.owner_member_id == owner_member_id)
        return query.order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc()).limit(min(limit, 250)).all()

    def get(self, *, tenant_id: UUID, task_id: UUID) -> ArceusTask:
        task = self.db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id, ArceusTask.id == task_id).first()
        if task is None:
            raise TaskNotFound("Task not found.")
        return task

    def dependencies(self, *, tenant_id: UUID, task_id: UUID) -> list[ArceusTaskDependency]:
        return (
            self.db.query(ArceusTaskDependency)
            .filter(ArceusTaskDependency.tenant_id == tenant_id, ArceusTaskDependency.task_id == task_id)
            .order_by(ArceusTaskDependency.created_at.asc())
            .all()
        )

    def attempts(self, *, tenant_id: UUID, task_id: UUID) -> list[ArceusTaskAttempt]:
        return (
            self.db.query(ArceusTaskAttempt)
            .filter(ArceusTaskAttempt.tenant_id == tenant_id, ArceusTaskAttempt.task_id == task_id)
            .order_by(ArceusTaskAttempt.attempt_number.desc())
            .all()
        )

    def active_leases(self, *, tenant_id: UUID, task_id: UUID) -> list[ArceusWorkerLease]:
        return (
            self.db.query(ArceusWorkerLease)
            .filter(ArceusWorkerLease.tenant_id == tenant_id, ArceusWorkerLease.task_id == task_id, ArceusWorkerLease.status == "active")
            .order_by(ArceusWorkerLease.expires_at.asc())
            .all()
        )

    def dependencies_satisfied(self, *, tenant_id: UUID, task_id: UUID) -> bool:
        dependencies = self.dependencies(tenant_id=tenant_id, task_id=task_id)
        if not dependencies:
            return True
        dependency_ids = [item.depends_on_task_id for item in dependencies]
        completed_count = (
            self.db.query(ArceusTask)
            .filter(
                ArceusTask.tenant_id == tenant_id,
                ArceusTask.id.in_(dependency_ids),
                ArceusTask.status == "completed",
            )
            .count()
        )
        return completed_count == len(dependency_ids)

    def ready_for_mission(self, *, tenant_id: UUID, mission_id: UUID, limit: int = 50) -> list[ArceusTask]:
        tasks = self.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, status="ready", limit=limit)
        return [task for task in tasks if self.dependencies_satisfied(tenant_id=tenant_id, task_id=task.id) and not self.active_leases(tenant_id=tenant_id, task_id=task.id)]

    def prioritized_ready_for_mission(self, *, tenant_id: UUID, mission_id: UUID, limit: int = 50) -> list[ArceusTask]:
        tasks = self.ready_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=250)
        return sorted(tasks, key=self.priority_score, reverse=True)[: min(limit, 100)]

    def priority_score(self, task: ArceusTask) -> float:
        output_contract = task.output_contract or {}
        input_contract = task.input_contract or {}
        risk_weight = {"critical": 30, "high": 20, "medium": 10, "low": 2}.get(str(output_contract.get("risk_level") or "medium"), 10)
        category_weight = {"approval": 25, "review": 20, "verification": 18, "implementation": 15, "design": 10, "analysis": 8}.get(str(task.task_type or "").lower(), 5)
        dependency_weight = self.db.query(ArceusTaskDependency).filter(
            ArceusTaskDependency.tenant_id == task.tenant_id,
            ArceusTaskDependency.depends_on_task_id == task.id,
        ).count() * 4
        estimate = float((output_contract.get("estimates") or input_contract.get("estimates") or {}).get("hours", 1.0) or 1.0)
        return round(category_weight + risk_weight + dependency_weight - min(estimate, 12) * 0.25, 3)

    def create_attempt(self, task: ArceusTask, *, worker_id: str) -> ArceusTaskAttempt:
        latest = self.attempts(tenant_id=task.tenant_id, task_id=task.id)
        attempt_number = (latest[0].attempt_number if latest else 0) + 1
        attempt = ArceusTaskAttempt(
            tenant_id=task.tenant_id,
            task_id=task.id,
            attempt_number=attempt_number,
            status="running",
            worker_id=worker_id,
            idempotency_key=f"task-attempt:{task.id}:{attempt_number}",
            result={},
            error={},
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def finish_attempt(self, attempt: ArceusTaskAttempt, *, status: str, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        attempt.status = status
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.result = result or {}
        attempt.error = error or {}
        attempt.version_number = int(attempt.version_number or 1) + 1

    def retry(self, task: ArceusTask, *, reason: str | None) -> None:
        if task.status not in {"failed", "blocked", "cancelled"}:
            raise TaskStateConflict("Only failed, blocked, or cancelled tasks can be retried.", details={"status": task.status})
        task.status = "ready"
        task.failure_reason = None
        task.started_at = None
        task.completed_at = None
        task.version_number = int(task.version_number or 1) + 1
        task.output_contract = {**(task.output_contract or {}), "last_retry_reason": reason}

    def skip(self, task: ArceusTask, *, reason: str | None) -> None:
        if task.status in {"running", "verifying"}:
            raise TaskStateConflict("Running or verifying tasks cannot be skipped.", details={"status": task.status})
        if task.status == "completed":
            raise TaskStateConflict("Completed tasks cannot be skipped.", details={"status": task.status})
        task.status = "cancelled"
        task.failure_reason = reason or "Skipped by user."
        task.completed_at = datetime.now(timezone.utc)
        task.version_number = int(task.version_number or 1) + 1


class RuntimeExecutionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_lease(self, *, tenant_id: UUID, lease_id: UUID) -> ArceusWorkerLease:
        lease = (
            self.db.query(ArceusWorkerLease)
            .filter(ArceusWorkerLease.tenant_id == tenant_id, ArceusWorkerLease.id == lease_id)
            .first()
        )
        if lease is None:
            raise WorkerLeaseNotFound("Worker lease not found.")
        return lease

    def acquire_lease(
        self,
        *,
        tenant_id: UUID,
        mission: ArceusMission,
        task: ArceusTask,
        worker_id: str,
        ttl_seconds: int = 120,
    ) -> ArceusWorkerLease:
        if mission.status != "running":
            raise RuntimeStateConflict("Worker leases require a running mission.", details={"mission_status": mission.status})
        if task.status != "ready":
            raise RuntimeStateConflict("Only ready tasks can be leased.", details={"task_status": task.status})
        active = (
            self.db.query(ArceusWorkerLease)
            .filter(
                ArceusWorkerLease.tenant_id == tenant_id,
                ArceusWorkerLease.task_id == task.id,
                ArceusWorkerLease.status == "active",
                ArceusWorkerLease.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if active is not None:
            raise RuntimeStateConflict("Task already has an active worker lease.", details={"lease_id": str(active.id)})
        lease = ArceusWorkerLease(
            tenant_id=tenant_id,
            task_id=task.id,
            worker_id=worker_id,
            lease_token=f"lease_{uuid.uuid4().hex}",
            status="active",
            heartbeat_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )
        task.status = "running"
        task.started_at = task.started_at or datetime.now(timezone.utc)
        task.version_number = int(task.version_number or 1) + 1
        self.db.add(lease)
        self.db.flush()
        return lease

    def heartbeat(
        self,
        lease: ArceusWorkerLease,
        *,
        ttl_seconds: int = 120,
    ) -> None:
        if lease.status != "active":
            raise RuntimeStateConflict("Only active leases can heartbeat.", details={"lease_status": lease.status})
        lease.heartbeat_at = datetime.now(timezone.utc)
        lease.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        lease.version_number = int(lease.version_number or 1) + 1

    def release(self, lease: ArceusWorkerLease) -> None:
        lease.status = "released"
        lease.heartbeat_at = datetime.now(timezone.utc)
        lease.version_number = int(lease.version_number or 1) + 1

    def complete_task(self, *, task: ArceusTask, lease: ArceusWorkerLease, outputs: dict[str, Any] | None = None) -> None:
        if lease.status != "active" or lease.task_id != task.id:
            raise RuntimeStateConflict("Task completion requires an active matching lease.")
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.output_contract = {**(task.output_contract or {}), "runtime_outputs": outputs or {}}
        task.version_number = int(task.version_number or 1) + 1
        self.release(lease)

    def fail_task(self, *, task: ArceusTask, lease: ArceusWorkerLease, error: str) -> None:
        if lease.status != "active" or lease.task_id != task.id:
            raise RuntimeStateConflict("Task failure requires an active matching lease.")
        task.status = "failed"
        task.failure_reason = error
        task.completed_at = datetime.now(timezone.utc)
        task.version_number = int(task.version_number or 1) + 1
        self.release(lease)

    def create_checkpoint(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        task_id: UUID,
        workflow_id: UUID | None,
        lease_id: UUID | None,
        checkpoint_key: str,
        workflow_version: int,
        worker_id: str,
        execution_state: dict[str, Any],
        outputs: dict[str, Any] | None = None,
        progress_percent: int = 0,
    ) -> ArceusRuntimeCheckpoint:
        checkpoint = ArceusRuntimeCheckpoint(
            tenant_id=tenant_id,
            mission_id=mission_id,
            task_id=task_id,
            workflow_id=workflow_id,
            worker_lease_id=lease_id,
            checkpoint_key=checkpoint_key,
            workflow_version=workflow_version,
            execution_state=execution_state,
            artifacts=[],
            model_calls=[],
            tool_calls=[],
            outputs=outputs or {},
            progress_percent=max(0, min(progress_percent, 100)),
            created_by_worker_id=worker_id,
        )
        self.db.add(checkpoint)
        self.db.flush()
        return checkpoint

    def checkpoints_for_task(self, *, tenant_id: UUID, task_id: UUID, limit: int = 50) -> list[ArceusRuntimeCheckpoint]:
        return (
            self.db.query(ArceusRuntimeCheckpoint)
            .filter(ArceusRuntimeCheckpoint.tenant_id == tenant_id, ArceusRuntimeCheckpoint.task_id == task_id)
            .order_by(ArceusRuntimeCheckpoint.created_at.desc(), ArceusRuntimeCheckpoint.id.desc())
            .limit(min(limit, 100))
            .all()
        )

    def expire_stale_leases(self, *, tenant_id: UUID | None = None) -> int:
        query = self.db.query(ArceusWorkerLease).filter(
            ArceusWorkerLease.status == "active",
            ArceusWorkerLease.expires_at <= datetime.now(timezone.utc),
        )
        if tenant_id:
            query = query.filter(ArceusWorkerLease.tenant_id == tenant_id)
        expired = 0
        for lease in query.all():
            lease.status = "expired"
            task = self.db.query(ArceusTask).filter(ArceusTask.tenant_id == lease.tenant_id, ArceusTask.id == lease.task_id).first()
            if task is not None and task.status == "running":
                attempt_count = self.db.query(ArceusTaskAttempt).filter(
                    ArceusTaskAttempt.tenant_id == task.tenant_id,
                    ArceusTaskAttempt.task_id == task.id,
                ).count()
                retry_policy = (self.db.query(ArceusWorkflowNode).filter(
                    ArceusWorkflowNode.tenant_id == task.tenant_id,
                    ArceusWorkflowNode.id == task.workflow_node_id,
                ).first() or None)
                max_attempts = int((((retry_policy.config if retry_policy else {}) or {}).get("retry_policy") or {}).get("max_attempts", 3))
                if attempt_count < max_attempts:
                    task.status = "ready"
                    task.failure_reason = "Recovered from expired worker lease; task is ready to resume."
                else:
                    task.status = "failed"
                    task.failure_reason = "Worker lease expired and retry budget was exhausted."
                    task.completed_at = datetime.now(timezone.utc)
                task.version_number = int(task.version_number or 1) + 1
            expired += 1
        return expired


class DecisionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_mission(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        status: str | None = None,
        current_only: bool = False,
        limit: int = 50,
    ) -> list[ArceusDecision]:
        query = self.db.query(ArceusDecision).filter(
            ArceusDecision.tenant_id == tenant_id,
            ArceusDecision.mission_id == mission_id,
        )
        if status:
            query = query.filter(ArceusDecision.status == status)
        elif current_only:
            query = query.filter(ArceusDecision.status != "superseded")
        return query.order_by(ArceusDecision.updated_at.desc(), ArceusDecision.id.desc()).limit(min(limit, 100)).all()

    def get(self, *, tenant_id: UUID, decision_id: UUID) -> ArceusDecision:
        decision = (
            self.db.query(ArceusDecision)
            .filter(ArceusDecision.tenant_id == tenant_id, ArceusDecision.id == decision_id)
            .first()
        )
        if decision is None:
            raise DecisionNotFound("Decision not found.")
        return decision


class OrganizationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_mission(self, *, tenant_id: UUID, mission_id: UUID) -> ArceusMissionOrganization:
        organization = (
            self.db.query(ArceusMissionOrganization)
            .filter(ArceusMissionOrganization.tenant_id == tenant_id, ArceusMissionOrganization.mission_id == mission_id)
            .first()
        )
        if organization is None:
            raise OrganizationNotFound("Mission organization not found.")
        return organization

    def get(self, *, tenant_id: UUID, organization_id: UUID) -> ArceusMissionOrganization:
        organization = (
            self.db.query(ArceusMissionOrganization)
            .filter(ArceusMissionOrganization.tenant_id == tenant_id, ArceusMissionOrganization.id == organization_id)
            .first()
        )
        if organization is None:
            raise OrganizationNotFound("Mission organization not found.")
        return organization

    def members(
        self,
        *,
        tenant_id: UUID,
        organization_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusOrganizationMember]:
        query = self.db.query(ArceusOrganizationMember).filter(
            ArceusOrganizationMember.tenant_id == tenant_id,
            ArceusOrganizationMember.organization_id == organization_id,
        )
        if status:
            query = query.filter(ArceusOrganizationMember.status == status)
        return query.order_by(ArceusOrganizationMember.created_at.asc(), ArceusOrganizationMember.id.asc()).limit(min(limit, 100)).all()

    def get_member(self, *, tenant_id: UUID, member_id: UUID) -> ArceusOrganizationMember:
        member = (
            self.db.query(ArceusOrganizationMember)
            .filter(ArceusOrganizationMember.tenant_id == tenant_id, ArceusOrganizationMember.id == member_id)
            .first()
        )
        if member is None:
            raise OrganizationMemberNotFound("Organization member not found.")
        return member

    def specialist_profile(self, *, specialist_profile_id: UUID) -> ArceusSpecialistProfile | None:
        return self.db.query(ArceusSpecialistProfile).filter(ArceusSpecialistProfile.id == specialist_profile_id).first()


class CapabilityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, *, domain: str | None = None, active: bool | None = True, limit: int = 100) -> list[ArceusCapability]:
        query = self.db.query(ArceusCapability)
        if domain:
            query = query.filter(ArceusCapability.domain == domain)
        if active is not None:
            query = query.filter(ArceusCapability.active == active)
        return query.order_by(ArceusCapability.domain.asc(), ArceusCapability.capability_key.asc()).limit(min(limit, 250)).all()

    def get(self, *, capability_id: UUID) -> ArceusCapability:
        capability = self.db.query(ArceusCapability).filter(ArceusCapability.id == capability_id).first()
        if capability is None:
            raise CapabilityNotFound("Capability not found.")
        return capability

    def required_for_mission(self, *, tenant_id: UUID, mission_id: UUID) -> list[tuple[ArceusMissionRequiredCapability, ArceusCapability | None]]:
        rows = (
            self.db.query(ArceusMissionRequiredCapability)
            .filter(ArceusMissionRequiredCapability.tenant_id == tenant_id, ArceusMissionRequiredCapability.mission_id == mission_id)
            .order_by(ArceusMissionRequiredCapability.created_at.asc())
            .all()
        )
        return [(row, self.db.query(ArceusCapability).filter(ArceusCapability.id == row.capability_id).first()) for row in rows]

    def specialist_capabilities(self, *, specialist_profile_id: UUID) -> list[tuple[ArceusSpecialistCapability, ArceusCapability | None]]:
        rows = (
            self.db.query(ArceusSpecialistCapability)
            .filter(ArceusSpecialistCapability.specialist_profile_id == specialist_profile_id)
            .order_by(ArceusSpecialistCapability.proficiency.desc())
            .all()
        )
        return [(row, self.db.query(ArceusCapability).filter(ArceusCapability.id == row.capability_id).first()) for row in rows]


class ExecutionTraceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def context_packages(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        task_id: UUID | None = None,
        recipient_member_id: UUID | None = None,
        limit: int = 50,
    ) -> list[ArceusContextPackage]:
        query = self.db.query(ArceusContextPackage).filter(
            ArceusContextPackage.tenant_id == tenant_id,
            ArceusContextPackage.mission_id == mission_id,
        )
        if task_id:
            query = query.filter(ArceusContextPackage.task_id == task_id)
        if recipient_member_id:
            query = query.filter(ArceusContextPackage.recipient_member_id == recipient_member_id)
        return query.order_by(ArceusContextPackage.created_at.desc(), ArceusContextPackage.id.desc()).limit(min(limit, 100)).all()

    def context_package(self, *, tenant_id: UUID, context_package_id: UUID) -> ArceusContextPackage:
        item = (
            self.db.query(ArceusContextPackage)
            .filter(ArceusContextPackage.tenant_id == tenant_id, ArceusContextPackage.id == context_package_id)
            .first()
        )
        if item is None:
            raise ContextPackageNotFound("Context package not found.")
        return item

    def model_executions(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID | None = None,
        task_id: UUID | None = None,
        member_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusModelExecution]:
        query = self.db.query(ArceusModelExecution).filter(ArceusModelExecution.tenant_id == tenant_id)
        if mission_id:
            query = query.filter(ArceusModelExecution.mission_id == mission_id)
        if task_id:
            query = query.filter(ArceusModelExecution.task_id == task_id)
        if member_id:
            query = query.filter(ArceusModelExecution.member_id == member_id)
        if status:
            query = query.filter(ArceusModelExecution.status == status)
        return query.order_by(ArceusModelExecution.created_at.desc(), ArceusModelExecution.id.desc()).limit(min(limit, 100)).all()

    def model_execution(self, *, tenant_id: UUID, model_execution_id: UUID) -> ArceusModelExecution:
        item = (
            self.db.query(ArceusModelExecution)
            .filter(ArceusModelExecution.tenant_id == tenant_id, ArceusModelExecution.id == model_execution_id)
            .first()
        )
        if item is None:
            raise ModelExecutionNotFound("Model execution not found.")
        return item

    def tool_definitions(self, *, active: bool | None = True, limit: int = 100) -> list[ArceusToolDefinition]:
        query = self.db.query(ArceusToolDefinition)
        if active is not None:
            query = query.filter(ArceusToolDefinition.active == active)
        return query.order_by(ArceusToolDefinition.tool_key.asc()).limit(min(limit, 250)).all()

    def tool_executions(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID | None = None,
        task_id: UUID | None = None,
        member_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ArceusToolExecution]:
        query = self.db.query(ArceusToolExecution).filter(ArceusToolExecution.tenant_id == tenant_id)
        if mission_id:
            query = query.filter(ArceusToolExecution.mission_id == mission_id)
        if task_id:
            query = query.filter(ArceusToolExecution.task_id == task_id)
        if member_id:
            query = query.filter(ArceusToolExecution.member_id == member_id)
        if status:
            query = query.filter(ArceusToolExecution.status == status)
        return query.order_by(ArceusToolExecution.created_at.desc(), ArceusToolExecution.id.desc()).limit(min(limit, 100)).all()

    def tool_execution(self, *, tenant_id: UUID, tool_execution_id: UUID) -> ArceusToolExecution:
        item = (
            self.db.query(ArceusToolExecution)
            .filter(ArceusToolExecution.tenant_id == tenant_id, ArceusToolExecution.id == tool_execution_id)
            .first()
        )
        if item is None:
            raise ToolExecutionNotFound("Tool execution not found.")
        return item

    def tool_definition(self, *, tool_definition_id: UUID) -> ArceusToolDefinition | None:
        return self.db.query(ArceusToolDefinition).filter(ArceusToolDefinition.id == tool_definition_id).first()

    def policy_evaluations(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID | None = None,
        task_id: UUID | None = None,
        decision: str | None = None,
        limit: int = 50,
    ) -> list[ArceusPolicyEvaluation]:
        query = self.db.query(ArceusPolicyEvaluation).filter(ArceusPolicyEvaluation.tenant_id == tenant_id)
        if mission_id:
            query = query.filter(ArceusPolicyEvaluation.mission_id == mission_id)
        if task_id:
            query = query.filter(ArceusPolicyEvaluation.task_id == task_id)
        if decision:
            query = query.filter(ArceusPolicyEvaluation.decision == decision)
        return query.order_by(ArceusPolicyEvaluation.created_at.desc(), ArceusPolicyEvaluation.id.desc()).limit(min(limit, 100)).all()

    def policy_evaluation(self, *, tenant_id: UUID, policy_evaluation_id: UUID) -> ArceusPolicyEvaluation:
        item = (
            self.db.query(ArceusPolicyEvaluation)
            .filter(ArceusPolicyEvaluation.tenant_id == tenant_id, ArceusPolicyEvaluation.id == policy_evaluation_id)
            .first()
        )
        if item is None:
            raise PolicyEvaluationNotFound("Policy evaluation not found.")
        return item


class UsageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None = None,
        mission_id: UUID | None = None,
        usage_type: str | None = None,
        limit: int = 100,
    ) -> list[ArceusUsageRecord]:
        query = self.db.query(ArceusUsageRecord).filter(ArceusUsageRecord.tenant_id == tenant_id)
        if user_id:
            query = query.filter(ArceusUsageRecord.user_id == user_id)
        if mission_id:
            query = query.filter(ArceusUsageRecord.mission_id == mission_id)
        if usage_type:
            query = query.filter(ArceusUsageRecord.usage_type == usage_type)
        return query.order_by(ArceusUsageRecord.occurred_at.desc(), ArceusUsageRecord.id.desc()).limit(min(limit, 500)).all()

    def get(self, *, tenant_id: UUID, usage_record_id: UUID) -> ArceusUsageRecord:
        record = (
            self.db.query(ArceusUsageRecord)
            .filter(ArceusUsageRecord.tenant_id == tenant_id, ArceusUsageRecord.id == usage_record_id)
            .first()
        )
        if record is None:
            raise UsageRecordNotFound("Usage record not found.")
        return record

    def summarize(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None = None,
        mission_id: UUID | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        records = self.list(tenant_id=tenant_id, user_id=user_id, mission_id=mission_id, limit=limit)
        by_type: dict[str, dict[str, Any]] = {}
        total_cost = 0
        for record in records:
            key = record.usage_type
            bucket = by_type.setdefault(
                key,
                {
                    "usage_type": key,
                    "quantity": 0,
                    "unit": record.unit,
                    "cost_usd": 0,
                    "record_count": 0,
                },
            )
            bucket["quantity"] += record.quantity or 0
            bucket["cost_usd"] += record.cost_usd or 0
            bucket["record_count"] += 1
            total_cost += record.cost_usd or 0
        return {
            "record_count": len(records),
            "cost_usd": total_cost,
            "by_type": list(by_type.values()),
        }


class RuntimeHealthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _status_counts(self, model, status_column, *, tenant_id: UUID) -> dict[str, int]:
        rows = (
            self.db.query(status_column, func.count(model.id))
            .filter(model.tenant_id == tenant_id)
            .group_by(status_column)
            .all()
        )
        return {str(status): int(count or 0) for status, count in rows}

    def summary(self, *, tenant_id: UUID) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        mission_statuses = self._status_counts(ArceusMission, ArceusMission.status, tenant_id=tenant_id)
        task_statuses = self._status_counts(ArceusTask, ArceusTask.status, tenant_id=tenant_id)
        approval_statuses = self._status_counts(ArceusApproval, ArceusApproval.status, tenant_id=tenant_id)
        outbox_statuses = self._status_counts(ArceusOutboxMessage, ArceusOutboxMessage.status, tenant_id=tenant_id)
        active_leases = int(
            self.db.query(func.count(ArceusWorkerLease.id))
            .filter(
                ArceusWorkerLease.tenant_id == tenant_id,
                ArceusWorkerLease.status == "active",
                ArceusWorkerLease.expires_at > now,
            )
            .scalar()
            or 0
        )
        stale_processing_outbox = int(
            self.db.query(func.count(ArceusOutboxMessage.id))
            .filter(
                ArceusOutboxMessage.tenant_id == tenant_id,
                ArceusOutboxMessage.status == "processing",
                ArceusOutboxMessage.locked_at < now - timedelta(minutes=10),
            )
            .scalar()
            or 0
        )
        return {
            "mission_statuses": mission_statuses,
            "task_statuses": task_statuses,
            "approval_statuses": approval_statuses,
            "outbox_statuses": outbox_statuses,
            "active_worker_leases": active_leases,
            "stale_processing_outbox": stale_processing_outbox,
        }


class SqlAlchemyUnitOfWork:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.missions = MissionRepository(db)
        self.compiler_runs = CompilerRunRepository(db)
        self.events = EventRepository(db)
        self.outbox = OutboxRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self.audit = AuditRepository(db)
        self.approvals = ApprovalRepository(db)
        self.workflows = WorkflowRepository(db)
        self.artifacts = ArtifactRepository(db)
        self.evidence = EvidenceRepository(db)
        self.verification_runs = VerificationRunRepository(db)
        self.tasks = TaskRepository(db)
        self.decisions = DecisionRepository(db)
        self.organizations = OrganizationRepository(db)
        self.capabilities = CapabilityRepository(db)
        self.execution_traces = ExecutionTraceRepository(db)
        self.usage = UsageRepository(db)
        self.runtime_health = RuntimeHealthRepository(db)
        self.runtime_execution = RuntimeExecutionRepository(db)

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def new_id(self) -> UUID:
        return uuid.uuid4()
