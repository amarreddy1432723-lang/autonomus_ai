from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem, ArceusMission, ArceusPerformanceObservation
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .api_schemas import (
    ExecutiveBriefingResponse,
    ExecutiveDecisionRequest,
    ExecutiveDecisionResponse,
    StrategicObjectiveRequest,
    StrategicObjectiveResponse,
    StrategyDashboardResponse,
    StrategyPortfolioResponse,
    StrategySimulationRequest,
    StrategySimulationResponse,
)
from .service import (
    build_key_results,
    build_portfolio_summary,
    calculate_enterprise_health,
    evaluate_executive_decision,
    objective_governance,
    score_portfolio_items,
    simulate_strategy,
)


router = APIRouter(prefix="/api/v1/strategy", tags=["strategic-intelligence"])


def _runtime_summary(db: Session, tenant_id: UUID) -> dict:
    return SqlAlchemyUnitOfWork(db).runtime_health.summary(tenant_id=tenant_id)


def _tenant_metrics(db: Session, tenant_id: UUID) -> dict[str, float]:
    observations = db.query(ArceusPerformanceObservation).filter(ArceusPerformanceObservation.tenant_id == tenant_id).limit(1500).all()
    buckets: dict[str, list[float]] = {}
    for item in observations:
        buckets.setdefault(item.metric_key, []).append(float(item.metric_value))
    return {key: round(sum(values) / len(values), 4) for key, values in buckets.items() if values}


def _strategy_memories(db: Session, tenant_id: UUID, content_type: str, limit: int = 100) -> list[ArceusMemoryItem]:
    return (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.content_type == content_type,
            ArceusMemoryItem.lifecycle_status.in_(["proposed", "verified", "approved"]),
        )
        .order_by(ArceusMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )


def _upsert_memory(
    db: Session,
    *,
    tenant_id: UUID,
    title: str,
    content: dict,
    content_type: str,
    source_type: str,
    evidence_ids: list[UUID],
    confidence: float,
    lifecycle_status: str = "proposed",
    trust_level: str = "unverified",
) -> ArceusMemoryItem:
    content_hash = stable_hash({"content_type": content_type, "title": title, "content": content})
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.scope_reference_id.is_(None),
            ArceusMemoryItem.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=tenant_id,
        memory_scope="organization",
        title=title,
        content=json.dumps(content, sort_keys=True),
        content_type=content_type,
        source_type=source_type,
        source_ids=[],
        evidence_ids=[str(item) for item in evidence_ids],
        lifecycle_status=lifecycle_status,
        trust_level=trust_level,
        confidence=confidence,
        sensitivity="organization",
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    return row


@router.post("/objectives")
def create_strategic_objective(
    payload: StrategicObjectiveRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.objective.create")),
    db: Session = Depends(get_db),
):
    key_results = build_key_results(title=payload.title, desired_outcomes=payload.desired_outcomes, kpis=payload.kpis, horizon=payload.horizon)
    governance = objective_governance(priority=payload.priority, domain=payload.domain, evidence_ids=payload.evidence_ids)
    hierarchy = {
        "vision": payload.vision,
        "objective": payload.title,
        "initiatives": [result["title"] for result in key_results],
        "missions": [],
        "kpis": [result["key"] for result in key_results],
        "feedback": "pending_business_outcome_evidence",
    }
    content = {
        "domain": payload.domain,
        "horizon": payload.horizon,
        "desired_outcomes": payload.desired_outcomes,
        "priority": payload.priority,
        "key_results": key_results,
        "hierarchy": hierarchy,
        "required_governance": governance,
    }
    memory = _upsert_memory(
        db,
        tenant_id=context.tenant_id,
        title=payload.title,
        content=content,
        content_type="strategic_objective",
        source_type="executive_input",
        evidence_ids=payload.evidence_ids,
        confidence=0.72 if payload.evidence_ids else 0.55,
        trust_level="evidence_backed" if payload.evidence_ids else "unverified",
    )
    for key, value in payload.kpis.items():
        db.add(
            ArceusPerformanceObservation(
                tenant_id=context.tenant_id,
                subject_type="strategic_objective",
                subject_id=memory.id,
                metric_key=key,
                metric_value=float(value),
                evidence_ids=[str(item) for item in payload.evidence_ids],
                attribution={"source_type": "strategic_objective", "objective_id": str(memory.id), "target": True},
            )
        )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="OBJECTIVE_CREATED",
        resource_type="strategic_objective",
        resource_id=memory.id,
        result="proposed",
        metadata={"correlation_id": str(context.correlation_id), "key_result_count": len(key_results), "governance": governance},
    )
    db.commit()
    response = StrategicObjectiveResponse(
        objective_id=memory.id,
        title=memory.title,
        status=memory.lifecycle_status,
        hierarchy=hierarchy,
        key_results=key_results,
        required_governance=governance,
        traceability={"memory_item_id": memory.id, "audit_event": "OBJECTIVE_CREATED", "evidence_ids": payload.evidence_ids},
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/dashboard")
def get_strategy_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    metrics = _tenant_metrics(db, context.tenant_id)
    health = calculate_enterprise_health(metrics, summary)
    portfolio_summary = build_portfolio_summary(summary)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="HEALTH_SCORE_UPDATED",
        resource_type="strategy_dashboard",
        resource_id=context.tenant_id,
        result=health["status"],
        metadata={"score": health["enterprise_health"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = StrategyDashboardResponse(
        enterprise_health=health["enterprise_health"],
        status=health["status"],
        health_dimensions=health["health_dimensions"],
        kpis=metrics,
        risks=health["risks"],
        recommendations=health["recommendations"],
        portfolio_summary=portfolio_summary,
        generated_at=datetime.now(timezone.utc),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/portfolio")
def get_strategy_portfolio(
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    objectives = [
        {
            "id": item.id,
            "title": item.title,
            "status": item.lifecycle_status,
            "priority": (json.loads(item.content).get("priority") if item.content else 3),
            "confidence": item.confidence or 0.5,
            "evidence_ids": item.evidence_ids or [],
        }
        for item in _strategy_memories(db, context.tenant_id, "strategic_objective", limit=50)
    ]
    missions = (
        db.query(ArceusMission)
        .filter(ArceusMission.tenant_id == context.tenant_id)
        .order_by(ArceusMission.created_at.desc())
        .limit(50)
        .all()
    )
    objectives.extend(
        {
            "id": mission.id,
            "title": mission.title,
            "status": mission.status,
            "priority": mission.priority,
            "confidence": 0.7,
            "evidence_ids": [],
        }
        for mission in missions
    )
    portfolio = score_portfolio_items(objectives, summary)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="PORTFOLIO_CHANGED",
        resource_type="strategy_portfolio",
        resource_id=context.tenant_id,
        result="generated",
        metadata={"item_count": len(objectives), "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = StrategyPortfolioResponse(
        missions_by_status=summary.get("mission_statuses") or {},
        task_flow=summary.get("task_statuses") or {},
        **portfolio,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/simulate")
def simulate_strategy_scenario(
    payload: StrategySimulationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.simulate")),
    db: Session = Depends(get_db),
):
    result = simulate_strategy(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="SIMULATION_COMPLETED",
        resource_type="strategy_simulation",
        resource_id=result["scenario_id"],
        result=result["recommendation"],
        metadata={"confidence": result["confidence"], "risks": result["risks"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(StrategySimulationResponse(**result).model_dump(mode="json"), request)


@router.post("/decisions")
def record_executive_decision(
    payload: ExecutiveDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.decision.record")),
    db: Session = Depends(get_db),
):
    governance = evaluate_executive_decision(
        decision_type=payload.decision_type,
        expected_impact=payload.expected_impact,
        evidence_ids=payload.evidence_ids,
        reversible=payload.reversible,
    )
    content = {
        "decision_type": payload.decision_type,
        "summary": payload.summary,
        "selected_option": payload.selected_option,
        "alternatives": payload.alternatives,
        "expected_impact": payload.expected_impact,
        "reversible": payload.reversible,
        "governance": governance,
    }
    memory = _upsert_memory(
        db,
        tenant_id=context.tenant_id,
        title=payload.title,
        content=content,
        content_type="executive_decision",
        source_type="human_decision",
        evidence_ids=payload.evidence_ids,
        confidence=0.78 if payload.evidence_ids else 0.5,
        lifecycle_status="verified" if governance["status"] == "recorded" else "proposed",
        trust_level="human_recorded" if governance["status"] == "recorded" else "review_required",
    )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="DECISION_RECORDED",
        resource_type="executive_decision",
        resource_id=memory.id,
        result=governance["status"],
        metadata={"decision_type": payload.decision_type, "required_approvals": governance["required_approvals"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = ExecutiveDecisionResponse(
        decision_id=memory.id,
        status=governance["status"],
        governance_decision=governance["governance_decision"],
        required_approvals=governance["required_approvals"],
        reusable_knowledge={
            "memory_item_id": memory.id,
            "content_type": memory.content_type,
            "trust_level": memory.trust_level,
            "applies_only_with_evidence": True,
        },
        traceability={"audit_event": "DECISION_RECORDED", "evidence_ids": payload.evidence_ids},
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/briefing")
def get_executive_briefing(
    request: Request,
    context: RequestContext = Depends(require_permission("strategy.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    metrics = _tenant_metrics(db, context.tenant_id)
    health = calculate_enterprise_health(metrics, summary)
    objectives = _strategy_memories(db, context.tenant_id, "strategic_objective", limit=5)
    decisions = _strategy_memories(db, context.tenant_id, "executive_decision", limit=5)
    headlines = [
        f"Enterprise health is {health['status']} at {health['enterprise_health']}%.",
        f"{len(objectives)} recent strategic objective(s) are active in organization memory.",
    ]
    if health["risks"]:
        headlines.append(f"{len(health['risks'])} strategic risk signal(s) require attention.")
    rows = [
        {"decision_id": item.id, "title": item.title, "status": item.lifecycle_status, "trust_level": item.trust_level}
        for item in decisions
    ]
    next_actions = ["Review objective evidence", "Inspect portfolio blockers"]
    if any(risk["severity"] == "high" for risk in health["risks"]):
        next_actions.insert(0, "Open executive risk review")
    response = ExecutiveBriefingResponse(
        generated_at=datetime.now(timezone.utc),
        headlines=headlines,
        risks=health["risks"],
        decisions=rows,
        recommendations=health["recommendations"],
        next_actions=next_actions,
    )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="EXECUTIVE_REPORT_GENERATED",
        resource_type="executive_briefing",
        resource_id=context.tenant_id,
        result=health["status"],
        metadata={"headline_count": len(headlines), "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(response.model_dump(mode="json"), request)
