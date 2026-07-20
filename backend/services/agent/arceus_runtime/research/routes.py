from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .api_schemas import (
    ExperimentRequest,
    ExperimentResponse,
    FindingResponse,
    HypothesisRequest,
    HypothesisResponse,
    InnovationResponse,
    PublicationRequest,
    PublicationResponse,
    ResearchProjectRequest,
    ResearchProjectResponse,
)
from .service import (
    build_publication,
    build_research_project,
    design_experiment,
    generate_hypotheses,
    score_innovation,
    synthesize_findings,
    uncertainty_model,
)


router = APIRouter(prefix="/api/v1/research", tags=["research-innovation"])


def _persist_research_memory(
    db: Session,
    context: RequestContext,
    *,
    title: str,
    content_type: str,
    content: dict,
    event_type: str,
    status_value: str = "verified",
    confidence: float = 0.72,
) -> ArceusMemoryItem:
    content_hash = stable_hash({"content_type": content_type, "title": title, "content": content})
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope="organization",
        title=title,
        content=json.dumps(content, sort_keys=True, default=str),
        content_type=content_type,
        source_type="research_engine",
        source_ids=[str(content.get("research_id") or content.get("hypothesis_id") or content.get("experiment_id") or content.get("publication_id") or title)],
        evidence_ids=[str(item) for item in content.get("evidence_ids", [])],
        lifecycle_status=status_value,
        trust_level="evidence_backed" if content.get("evidence_ids") else "research_generated",
        confidence=confidence,
        sensitivity="organization",
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=event_type,
        resource_type=content_type,
        resource_id=row.id,
        result=status_value,
        metadata={"content_hash": content_hash, "correlation_id": str(context.correlation_id)},
    )
    return row


def _research_memories(db: Session, tenant_id: UUID, content_types: list[str], limit: int = 100) -> list[dict]:
    rows = (
        db.query(ArceusMemoryItem)
        .filter(ArceusMemoryItem.tenant_id == tenant_id, ArceusMemoryItem.content_type.in_(content_types))
        .order_by(ArceusMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )
    payloads = []
    for row in rows:
        try:
            content = json.loads(row.content)
        except (TypeError, json.JSONDecodeError):
            content = row.content
        payloads.append({"id": str(row.id), "title": row.title, "content_type": row.content_type, "content": content, "confidence": row.confidence})
    return payloads


@router.post("/project", status_code=status.HTTP_201_CREATED)
def create_research_project(
    payload: ResearchProjectRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("research.project.create")),
    db: Session = Depends(get_db),
):
    project = build_research_project(payload.model_dump(mode="json"))
    row = _persist_research_memory(
        db,
        context,
        title=project["title"],
        content_type="research_project",
        content={**project, "evidence_ids": payload.evidence_ids},
        event_type="RESEARCH_PROJECT_CREATED",
        confidence=project["confidence"],
    )
    db.commit()
    project["research_id"] = row.id
    return api_response(ResearchProjectResponse(**project).model_dump(mode="json"), request)


@router.post("/hypothesis", status_code=status.HTTP_201_CREATED)
def create_hypothesis(
    payload: HypothesisRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("research.hypothesis.create")),
    db: Session = Depends(get_db),
):
    hypotheses = generate_hypotheses(payload.model_dump(mode="json"))
    uncertainty = uncertainty_model(hypotheses, payload.evidence_ids)
    content = {
        "research_id": str(payload.research_id) if payload.research_id else None,
        "observation": payload.observation,
        "research_goal": payload.research_goal,
        "hypotheses": hypotheses,
        "uncertainty": uncertainty,
        "evidence_ids": payload.evidence_ids,
        "events": ["HYPOTHESIS_GENERATED"],
    }
    row = _persist_research_memory(
        db,
        context,
        title=f"Hypotheses for {payload.research_goal[:120]}",
        content_type="research_hypothesis",
        content=content,
        event_type="HYPOTHESIS_GENERATED",
        status_value="proposed",
        confidence=uncertainty["confidence"],
    )
    db.commit()
    response = HypothesisResponse(
        hypothesis_id=row.id,
        research_id=payload.research_id,
        hypotheses=hypotheses,
        selected_for_experiment=[item["hypothesis_key"] for item in hypotheses if item["testability"] >= 0.7],
        uncertainty=uncertainty,
        events=["HYPOTHESIS_GENERATED"],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/experiment", status_code=status.HTTP_201_CREATED)
def create_experiment(
    payload: ExperimentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("research.experiment.create")),
    db: Session = Depends(get_db),
):
    result = design_experiment(payload.model_dump(mode="json"))
    row = _persist_research_memory(
        db,
        context,
        title=f"Experiment for {payload.hypothesis[:120]}",
        content_type="research_experiment",
        content=result,
        event_type="EXPERIMENT_STARTED",
        status_value="proposed",
        confidence=result["reproducibility"]["reproducibility_score"],
    )
    db.commit()
    result["experiment_id"] = row.id
    return api_response(ExperimentResponse(**result).model_dump(mode="json"), request)


@router.get("/findings")
def get_findings(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(require_permission("research.findings.view")),
    db: Session = Depends(get_db),
):
    payloads = _research_memories(db, context.tenant_id, ["research_project", "research_hypothesis", "research_experiment", "research_publication"], limit=limit)
    findings = synthesize_findings(payloads)
    return collection_response([FindingResponse(**item).model_dump(mode="json") for item in findings], request)


@router.post("/publish", status_code=status.HTTP_201_CREATED)
def publish_research(
    payload: PublicationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("research.publish")),
    db: Session = Depends(get_db),
):
    publication = build_publication(payload.model_dump(mode="json"))
    row = _persist_research_memory(
        db,
        context,
        title=publication["title"],
        content_type="research_publication",
        content={**publication, "research_id": str(payload.research_id) if payload.research_id else None, "evidence_ids": payload.evidence_ids},
        event_type="PUBLICATION_RELEASED" if publication["status"] != "needs_human_review" else "RESEARCH_REVIEW_COMPLETED",
        status_value="verified" if publication["status"] != "needs_human_review" else "proposed",
        confidence=publication["report"]["innovation_score"]["scientific_confidence"],
    )
    db.commit()
    publication["publication_id"] = row.id
    return api_response(PublicationResponse(**publication).model_dump(mode="json"), request)


@router.get("/innovations")
def list_innovations(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(require_permission("research.innovation.view")),
    db: Session = Depends(get_db),
):
    payloads = _research_memories(db, context.tenant_id, ["research_publication", "research_project"], limit=limit)
    rows = []
    for payload in payloads:
        content = payload["content"] if isinstance(payload["content"], dict) else {}
        scores = score_innovation(content)
        rows.append(
            InnovationResponse(
                innovation_id="innovation_" + stable_hash({"memory": payload["id"], "title": payload["title"]})[:16],
                title=payload["title"],
                version=1,
                innovation_type=content.get("publication_type") or content.get("domain") or "research_program",
                scores={key: value for key, value in scores.items() if key != "priority_score"},
                priority_score=scores["priority_score"],
                confidence=scores["scientific_confidence"],
                supporting_evidence=content.get("evidence_ids", []),
                linked_research=[str(content.get("research_id") or payload["id"])],
                status="registered" if scores["priority_score"] >= 0.6 else "needs_more_evidence",
            ).model_dump(mode="json")
        )
    rows.sort(key=lambda item: item["priority_score"], reverse=True)
    return collection_response(rows, request)
