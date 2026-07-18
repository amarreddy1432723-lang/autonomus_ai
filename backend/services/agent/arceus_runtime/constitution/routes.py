from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    ConstitutionEvaluateRequest,
    ConstitutionEvaluationResponse,
    ConstitutionResponse,
    ConstitutionalRuleResponse,
    EvolutionRequest,
    EvolutionResponse,
    LessonProposalRequest,
    LessonProposalResponse,
    OrganizationFitnessResponse,
    OrganizationStandardResponse,
)
from .service import (
    CONSTITUTION_HIERARCHY,
    CONSTITUTION_KEY,
    CONSTITUTION_VERSION,
    evaluate_constitution,
    evaluate_evolution_change,
    evaluate_fitness,
    evaluate_lesson_promotion,
    list_rules,
    list_standards,
)


router = APIRouter(tags=["constitutional-ai"])


def _rule_response(rule) -> ConstitutionalRuleResponse:
    return ConstitutionalRuleResponse(
        rule_id=rule.rule_id,
        name=rule.name,
        description=rule.description,
        category=rule.category,
        priority=rule.priority,
        applies_to=list(rule.applies_to),
        enforcement_level=rule.enforcement_level,
        version=rule.version,
    )


@router.get("/api/v1/constitution")
def get_constitution(
    request: Request,
    context: RequestContext = Depends(require_permission("constitution.view")),
):
    rules = list_rules()
    response = ConstitutionResponse(
        constitution_key=CONSTITUTION_KEY,
        version=CONSTITUTION_VERSION,
        hierarchy=CONSTITUTION_HIERARCHY,
        rule_count=len(rules),
        absolute_rule_count=sum(1 for rule in rules if rule.enforcement_level == "absolute"),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/constitution/rules")
def get_constitution_rules(
    request: Request,
    context: RequestContext = Depends(require_permission("constitution.view")),
):
    return collection_response([_rule_response(rule).model_dump(mode="json") for rule in list_rules()], request)


@router.post("/api/v1/constitution/evaluate")
def evaluate_constitution_request(
    payload: ConstitutionEvaluateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("constitution.evaluate")),
    db: Session = Depends(get_db),
):
    result = evaluate_constitution(
        action_type=payload.action_type,
        objective=payload.objective,
        evidence_ids=payload.evidence_ids,
        constraints=payload.constraints,
        alternatives=payload.alternatives,
        selected_alternative=payload.selected_alternative,
        risks=payload.risks,
        confidence=payload.confidence,
        requires_human_authority=payload.requires_human_authority,
        irreversible=payload.irreversible,
        learning_change=payload.learning_change,
        repository_change_count=payload.repository_change_count,
    )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="CONSTITUTION_CHECK_COMPLETED",
        resource_type="mission" if payload.mission_id else "constitution",
        resource_id=payload.mission_id or payload.task_id,
        result=result["decision"],
        metadata={
            "mission_id": str(payload.mission_id) if payload.mission_id else None,
            "task_id": str(payload.task_id) if payload.task_id else None,
            "blockers": result["blockers"],
            "warnings": result["warnings"],
            "summary_hash": result["reasoning_summary"]["summary_hash"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(ConstitutionEvaluationResponse(**result).model_dump(mode="json"), request)


@router.get("/api/v1/organization/standards")
def get_organization_standards(
    request: Request,
    context: RequestContext = Depends(require_permission("organization.standards.view")),
):
    return collection_response([OrganizationStandardResponse(**standard).model_dump(mode="json") for standard in list_standards()], request)


@router.get("/api/v1/organization/fitness")
def get_organization_fitness(
    request: Request,
    context: RequestContext = Depends(require_permission("organization.fitness.view")),
    db: Session = Depends(get_db),
):
    summary = SqlAlchemyUnitOfWork(db).runtime_health.summary(tenant_id=context.tenant_id)
    return api_response(OrganizationFitnessResponse(**evaluate_fitness(summary)).model_dump(mode="json"), request)


@router.post("/api/v1/organization/lessons")
def propose_organization_lesson(
    payload: LessonProposalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("organization.lesson.propose")),
    db: Session = Depends(get_db),
):
    result = evaluate_lesson_promotion(evidence_ids=payload.evidence_ids, proposed_scope=payload.proposed_scope)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="LESSON_PROPOSED",
        resource_type="mission",
        resource_id=payload.mission_id,
        result=result["status"],
        metadata={
            "lesson": payload.lesson,
            "evidence_ids": [str(item) for item in payload.evidence_ids],
            "proposed_scope": payload.proposed_scope,
            "outcome_metric": payload.outcome_metric,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(LessonProposalResponse(**result).model_dump(mode="json"), request)


@router.get("/api/v1/reasoning/{reasoning_id}")
def get_reasoning_summary(
    reasoning_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("reasoning.view")),
):
    return api_response(
        {
            "reasoning_id": str(reasoning_id),
            "status": "externalized_summary_required",
            "message": "Reasoning summaries are returned by constitution evaluations and stored as audit/evidence metadata when attached to missions.",
        },
        request,
    )


@router.post("/api/v1/evolution/simulate")
def simulate_evolution(
    payload: EvolutionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evolution.simulate")),
):
    result = evaluate_evolution_change(changes=payload.changes, dry_run=True)
    return api_response(EvolutionResponse(**result).model_dump(mode="json"), request)


@router.post("/api/v1/evolution/propose")
def propose_evolution(
    payload: EvolutionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evolution.propose")),
    db: Session = Depends(get_db),
):
    result = evaluate_evolution_change(changes=payload.changes, dry_run=payload.dry_run)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="EVOLUTION_PROPOSED",
        resource_type="organization",
        resource_id=payload.proposal_key,
        result=result["status"],
        metadata={
            "description": payload.description,
            "changes": payload.changes,
            "baseline_mission_ids": [str(item) for item in payload.baseline_mission_ids],
            "dry_run": payload.dry_run,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(EvolutionResponse(**result).model_dump(mode="json"), request)
