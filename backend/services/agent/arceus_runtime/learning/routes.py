from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusEvidence, ArceusLessonProposal, ArceusMission, ArceusPerformanceObservation
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    LearningEvaluateRequest,
    LearningEvaluateResponse,
    LearningHistoryResponse,
    LearningPatternResponse,
    LearningPromotionRequest,
    LearningPromotionResponse,
    LearningRecordRequest,
    LearningRecordResponse,
    LearningScorecardResponse,
)
from .service import (
    discover_patterns,
    evaluate_learning_record,
    evaluate_promotion,
    scorecard_from_metrics,
    scorecard_from_observations,
)


router = APIRouter(prefix="/api/v1/learning", tags=["autonomous-learning"])


def _mission(db: Session, tenant_id: UUID, mission_id: UUID) -> ArceusMission:
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return mission


def _evidence(db: Session, tenant_id: UUID, mission_id: UUID | None, evidence_ids: list[UUID]) -> list[ArceusEvidence]:
    if not evidence_ids:
        return []
    query = db.query(ArceusEvidence).filter(ArceusEvidence.tenant_id == tenant_id, ArceusEvidence.id.in_(evidence_ids))
    if mission_id:
        query = query.filter(ArceusEvidence.mission_id == mission_id)
    return query.all()


@router.post("/records")
def create_learning_record(
    payload: LearningRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("learning.record.create")),
    db: Session = Depends(get_db),
):
    _mission(db, context.tenant_id, payload.mission_id)
    evidence = _evidence(db, context.tenant_id, payload.mission_id, payload.evidence_ids)
    evaluation = evaluate_learning_record(evidence=evidence, evidence_ids=payload.evidence_ids)
    learning_id = None
    if evaluation["promotion_ready"]:
        lesson = ArceusLessonProposal(
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            title=payload.title,
            lesson=payload.lesson,
            evidence_ids=[str(item) for item in payload.evidence_ids],
            impact=payload.impact,
            status="proposed",
        )
        db.add(lesson)
        db.flush()
        learning_id = lesson.id
        for key, value in payload.outcome_metrics.items():
            db.add(
                ArceusPerformanceObservation(
                    tenant_id=context.tenant_id,
                    mission_id=payload.mission_id,
                    subject_type="mission",
                    subject_id=payload.mission_id,
                    metric_key=key,
                    metric_value=float(value),
                    evidence_ids=[str(item) for item in payload.evidence_ids],
                    attribution={"source_type": payload.source_type, "learning_id": str(learning_id)},
                )
            )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="LEARNING_RECORD_CREATED" if learning_id else "LEARNING_RECORD_BLOCKED",
        resource_type="mission",
        resource_id=payload.mission_id,
        result=evaluation["status"],
        metadata={
            "learning_id": str(learning_id) if learning_id else None,
            "evidence_ids": [str(item) for item in payload.evidence_ids],
            "trusted_evidence_count": evaluation["trusted_evidence_count"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = LearningRecordResponse(
        learning_id=learning_id,
        mission_id=payload.mission_id,
        title=payload.title,
        evidence_ids=payload.evidence_ids,
        **evaluation,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/patterns")
def list_learning_patterns(
    request: Request,
    status: str | None = Query(default=None, max_length=60),
    context: RequestContext = Depends(require_permission("learning.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusLessonProposal).filter(ArceusLessonProposal.tenant_id == context.tenant_id)
    if status:
        query = query.filter(ArceusLessonProposal.status == status)
    patterns = [LearningPatternResponse(**item).model_dump(mode="json") for item in discover_patterns(query.limit(500).all())]
    return collection_response(patterns, request)


@router.get("/scorecards")
def list_learning_scorecards(
    request: Request,
    subject_type: str = Query(default="mission", max_length=80),
    subject_id: UUID | None = Query(default=None),
    context: RequestContext = Depends(require_permission("learning.view")),
    db: Session = Depends(get_db),
):
    observations = db.query(ArceusPerformanceObservation).filter(ArceusPerformanceObservation.tenant_id == context.tenant_id).limit(1000).all()
    scorecard = LearningScorecardResponse(**scorecard_from_observations(subject_type=subject_type, subject_id=subject_id, observations=observations))
    return collection_response([scorecard.model_dump(mode="json")], request)


@router.post("/promote")
def promote_learning(
    payload: LearningPromotionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("learning.promote")),
    db: Session = Depends(get_db),
):
    lesson = db.query(ArceusLessonProposal).filter(ArceusLessonProposal.tenant_id == context.tenant_id, ArceusLessonProposal.id == payload.learning_id).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Learning record not found.")
    evidence_ids = [UUID(str(item)) for item in lesson.evidence_ids]
    evidence = _evidence(db, context.tenant_id, lesson.mission_id, evidence_ids)
    result = evaluate_promotion(lesson=lesson, evidence=evidence, target_scope=payload.target_scope, dry_run=payload.dry_run)
    if result["accepted"] and not payload.dry_run:
        lesson.status = "approved"
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="LEARNING_PROMOTION_EVALUATED",
        resource_type="learning_record",
        resource_id=payload.learning_id,
        result=result["status"],
        metadata={
            "target_scope": payload.target_scope,
            "dry_run": payload.dry_run,
            "accepted": result["accepted"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = LearningPromotionResponse(target_scope=payload.target_scope, audit_recorded=True, **result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/history")
def get_learning_history(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(require_permission("learning.view")),
    db: Session = Depends(get_db),
):
    lessons = (
        db.query(ArceusLessonProposal)
        .filter(ArceusLessonProposal.tenant_id == context.tenant_id)
        .order_by(ArceusLessonProposal.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = [
        LearningHistoryResponse(
            learning_id=item.id,
            mission_id=item.mission_id,
            title=item.title,
            status=item.status,
            impact=item.impact,
            evidence_ids=[UUID(str(evidence_id)) for evidence_id in item.evidence_ids],
            created_at=item.created_at,
        ).model_dump(mode="json")
        for item in lessons
    ]
    return collection_response(rows, request)


@router.post("/evaluate")
def evaluate_learning(
    payload: LearningEvaluateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("learning.evaluate")),
    db: Session = Depends(get_db),
):
    evidence = _evidence(db, context.tenant_id, None, payload.evidence_ids)
    verified = evaluate_learning_record(evidence=evidence, evidence_ids=payload.evidence_ids)
    scorecard_payload = scorecard_from_metrics(subject_type=payload.subject_type, subject_id=payload.subject_id, metrics=payload.metrics)
    recorded = 0
    if verified["promotion_ready"]:
        for key, value in payload.metrics.items():
            db.add(
                ArceusPerformanceObservation(
                    tenant_id=context.tenant_id,
                    subject_type=payload.subject_type,
                    subject_id=payload.subject_id,
                    metric_key=key,
                    metric_value=float(value),
                    evidence_ids=[str(item) for item in payload.evidence_ids],
                    attribution={"source_type": "learning_evaluation"},
                )
            )
            recorded += 1
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="LEARNING_EVALUATED",
        resource_type=payload.subject_type,
        resource_id=payload.subject_id,
        result=scorecard_payload["status"],
        metadata={
            "promotion_ready": verified["promotion_ready"],
            "score": scorecard_payload["score"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    recommendations = [f"Improve {item}" for item in scorecard_payload["improvement_areas"]]
    response = LearningEvaluateResponse(
        scorecard=LearningScorecardResponse(**scorecard_payload),
        learning_recommendations=recommendations,
        promotion_allowed=verified["promotion_ready"],
        reason=verified["reason"],
        recorded_observations=recorded,
    )
    return api_response(response.model_dump(mode="json"), request)
