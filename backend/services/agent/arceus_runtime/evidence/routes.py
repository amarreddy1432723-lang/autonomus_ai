from __future__ import annotations

import json
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusArtifact, ArceusArtifactVersion, ArceusEvidence, ArceusEvent, ArceusOutboxMessage, ArceusTask
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import EvidenceResponse, TaskChangeSetRequest, ToolEvidenceRequest, VerificationRunResponse


router = APIRouter(tags=["evidence"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _evidence_response(evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=evidence.id,
        mission_id=evidence.mission_id,
        workflow_id=evidence.workflow_id,
        task_id=evidence.task_id,
        artifact_id=evidence.artifact_id,
        evidence_type=evidence.evidence_type,
        status=evidence.status,
        summary=evidence.summary,
        payload=evidence.payload or {},
        verification_method=evidence.verification_method,
        content_hash=evidence.content_hash,
        trust_level=evidence.trust_level,
        immutable=evidence.immutable,
        collected_by_member_id=evidence.collected_by_member_id,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
        version_number=evidence.version_number,
    )


def _verification_run_response(run) -> VerificationRunResponse:
    return VerificationRunResponse(
        id=run.id,
        mission_id=run.mission_id,
        task_id=run.task_id,
        verification_type=run.verification_type,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        command=run.command,
        result=run.result or {},
        evidence_id=run.evidence_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version_number=run.version_number,
    )


def _stable_hash(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _next_event_sequence(db: Session, *, tenant_id: UUID, mission_id: UUID) -> int:
    from sqlalchemy import func

    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def _append_evidence_event(db: Session, *, context: RequestContext, mission_id: UUID, task_id: UUID, evidence_ids: list[str]) -> None:
    event = ArceusEvent(
        tenant_id=context.tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=_next_event_sequence(db, tenant_id=context.tenant_id, mission_id=mission_id),
        event_type="task.evidence.collected",
        actor_type="desktop",
        actor_id=str(context.user_id),
        payload={"mission_id": str(mission_id), "task_id": str(task_id), "evidence_ids": evidence_ids, "count": len(evidence_ids)},
        metadata_json={"correlation_id": str(context.correlation_id), "idempotency_key": f"task.evidence:{task_id}:{_stable_hash({'evidence_ids': evidence_ids})[:16]}"},
    )
    db.add(event)
    db.flush()
    db.add(
        ArceusOutboxMessage(
            tenant_id=context.tenant_id,
            event_id=event.id,
            topic="arceus.task.evidence.collected",
            payload={"event_id": str(event.id), "mission_id": str(mission_id), "task_id": str(task_id), "evidence_ids": evidence_ids},
        )
    )


def _append_task_event(db: Session, *, context: RequestContext, mission_id: UUID, task_id: UUID, event_type: str, payload: dict) -> None:
    event = ArceusEvent(
        tenant_id=context.tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=_next_event_sequence(db, tenant_id=context.tenant_id, mission_id=mission_id),
        event_type=event_type,
        actor_type="desktop",
        actor_id=str(context.user_id),
        payload={"mission_id": str(mission_id), "task_id": str(task_id), **payload},
        metadata_json={"correlation_id": str(context.correlation_id), "idempotency_key": f"{event_type}:{task_id}:{_stable_hash(payload)[:16]}"},
    )
    db.add(event)
    db.flush()
    db.add(
        ArceusOutboxMessage(
            tenant_id=context.tenant_id,
            event_id=event.id,
            topic=f"arceus.{event_type}",
            payload={"event_id": str(event.id), "mission_id": str(mission_id), "task_id": str(task_id), **payload},
        )
    )


@router.get("/api/v1/missions/{mission_id}/evidence")
def list_mission_evidence(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    evidence_type: str | None = Query(default=None, max_length=100),
    evidence_status: str | None = Query(default=None, alias="status", max_length=60),
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    evidence = uow.evidence.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        evidence_type=evidence_type,
        status=evidence_status,
        limit=limit,
    )
    if task_id:
        evidence = [item for item in evidence if item.task_id == task_id]
    return collection_response([_evidence_response(item).model_dump(mode="json") for item in evidence], request)


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/tool-evidence")
def record_task_tool_evidence(
    mission_id: UUID,
    task_id: UUID,
    payload: ToolEvidenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    evidence_rows: list[ArceusEvidence] = []
    for record in payload.records:
        record_payload = record.model_dump(mode="json")
        evidence_payload = {
            "source": payload.source,
            "tool": record.tool,
            "input_summary": record.input_summary,
            "output_summary": record.output_summary,
            "duration_ms": record.duration_ms,
            "status": record.status,
            "error_class": record.error_class,
            "audit_id": record.audit_id,
            "timestamp": record.timestamp,
            "payload": record.payload,
        }
        content_hash = _stable_hash({"mission_id": str(mission_id), "task_id": str(task_id), "record": record_payload})
        evidence = ArceusEvidence(
            tenant_id=context.tenant_id,
            mission_id=mission_id,
            task_id=task_id,
            evidence_type="tool_invocation",
            status="failed" if record.status == "failed" else "validated",
            summary=payload.summary or f"{record.tool} {record.status}",
            payload=evidence_payload,
            verification_method=payload.source,
            content_hash=content_hash,
            trust_level="tool_verified" if record.status != "failed" else "unverified",
            immutable=True,
        )
        db.add(evidence)
        evidence_rows.append(evidence)
    db.flush()
    evidence_ids = [str(item.id) for item in evidence_rows]
    metadata = dict(task.output_contract or {})
    metadata["evidence_ids"] = sorted(set([*(metadata.get("evidence_ids") or []), *evidence_ids]))
    metadata["latest_evidence_count"] = len(metadata["evidence_ids"])
    task.output_contract = metadata
    task.version_number = int(task.version_number or 1) + 1
    _append_evidence_event(db, context=context, mission_id=mission_id, task_id=task_id, evidence_ids=evidence_ids)
    db.commit()
    return api_response(
        {
            "mission_id": str(mission_id),
            "task_id": str(task_id),
            "evidence_count": len(evidence_rows),
            "evidence": [_evidence_response(item).model_dump(mode="json") for item in evidence_rows],
        },
        request,
    )


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/change-set")
def record_task_change_set(
    mission_id: UUID,
    task_id: UUID,
    payload: TaskChangeSetRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    content = payload.model_dump(mode="json")
    content.update({"mission_id": str(mission_id), "task_id": str(task_id)})
    content_hash = _stable_hash(content)
    artifact_key = f"task-{task_id}-change-set-{content_hash[:12]}"
    trust_status = "verified" if payload.review_state in {"applied", "rolled_back"} else "unverified"
    artifact = ArceusArtifact(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        artifact_key=artifact_key,
        artifact_type="change_set",
        title=payload.title,
        trust_status=trust_status,
        metadata_json={
            "source": payload.source,
            "review_state": payload.review_state,
            "change_count": len(payload.changes),
            "content_hash": content_hash,
        },
    )
    db.add(artifact)
    db.flush()
    version = ArceusArtifactVersion(
        tenant_id=context.tenant_id,
        artifact_id=artifact.id,
        version=1,
        content=content,
        content_hash=content_hash,
        provenance={"source": payload.source, "mission_id": str(mission_id), "task_id": str(task_id), "review_state": payload.review_state},
    )
    db.add(version)
    db.flush()
    artifact.current_version_id = version.id

    metadata = dict(task.output_contract or {})
    metadata["change_set_artifact_ids"] = sorted(set([*(metadata.get("change_set_artifact_ids") or []), str(artifact.id)]))
    metadata["latest_change_set"] = {
        "artifact_id": str(artifact.id),
        "version_id": str(version.id),
        "review_state": payload.review_state,
        "change_count": len(payload.changes),
    }
    task.output_contract = metadata
    task.version_number = int(task.version_number or 1) + 1
    _append_task_event(
        db,
        context=context,
        mission_id=mission_id,
        task_id=task_id,
        event_type="task.change_set.recorded",
        payload={"artifact_id": str(artifact.id), "version_id": str(version.id), "review_state": payload.review_state, "change_count": len(payload.changes)},
    )
    db.commit()
    return api_response(
        {
            "mission_id": str(mission_id),
            "task_id": str(task_id),
            "artifact_id": str(artifact.id),
            "artifact_version_id": str(version.id),
            "review_state": payload.review_state,
            "change_count": len(payload.changes),
            "content_hash": content_hash,
        },
        request,
    )


@router.get("/api/v1/evidence/{evidence_id}")
def get_evidence(
    evidence_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    db: Session = Depends(get_db),
):
    evidence = _uow(db).evidence.get(tenant_id=context.tenant_id, evidence_id=evidence_id)
    return api_response(_evidence_response(evidence).model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/verification-runs")
def list_mission_verification_runs(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    verification_type: str | None = Query(default=None, max_length=100),
    verification_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    runs = uow.verification_runs.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        verification_type=verification_type,
        status=verification_status,
        limit=limit,
    )
    return collection_response([_verification_run_response(item).model_dump(mode="json") for item in runs], request)


@router.get("/api/v1/verification-runs/{verification_run_id}")
def get_verification_run(
    verification_run_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    run = _uow(db).verification_runs.get(tenant_id=context.tenant_id, verification_run_id=verification_run_id)
    return api_response(_verification_run_response(run).model_dump(mode="json"), request)
