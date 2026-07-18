from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAIExecutionLedger,
    ArceusBudget,
    ArceusCostReservation,
    ArceusModelProfile,
    ArceusProviderProfile,
    ArceusRoutingDecision,
    ArceusToolProfile,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AIExecutionRequest,
    BudgetRequest,
    BudgetResponse,
    ExecutionLedgerResponse,
    ModelExecutionResultResponse,
    ModelProfileRequest,
    ModelProfileResponse,
    ProviderProfileRequest,
    ProviderProfileResponse,
    RoutingDecisionResponse,
    ToolAuthorizationResponse,
    ToolExecutionRequest,
    ToolProfileRequest,
    ToolProfileResponse,
)
from .adapters import adapter_for
from .budgeting import BudgetExceededError, release_budget, reserve_budget, settle_budget
from .health import record_provider_failure, record_provider_success
from .prompting import compile_prompt
from .service import authorize_tool, execution_request_hash, route_model_request, stable_hash
from .validation import validate_model_output


router = APIRouter(tags=["gateway"])


def _provider_response(item: ArceusProviderProfile) -> ProviderProfileResponse:
    return ProviderProfileResponse(
        id=item.id,
        provider_key=item.provider_key,
        display_name=item.display_name,
        adapter_type=item.adapter_type,
        enabled=item.enabled,
        supported_regions=item.supported_regions or [],
        authentication_reference=item.authentication_reference,
        requests_per_minute=item.requests_per_minute,
        tokens_per_minute=item.tokens_per_minute,
        concurrent_request_limit=item.concurrent_request_limit,
        health_status=item.health_status,
        circuit_state=item.circuit_state,
        retention_policy=item.retention_policy,
        supports_zero_retention=item.supports_zero_retention,
        enterprise_agreement_required=item.enterprise_agreement_required,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _model_response(item: ArceusModelProfile) -> ModelProfileResponse:
    return ModelProfileResponse(
        id=item.id,
        model_key=item.model_key,
        provider_key=item.provider_key,
        provider_model_name=item.provider_model_name,
        display_name=item.display_name,
        status=item.status,
        capabilities=item.capabilities or [],
        supported_modalities=item.supported_modalities or [],
        supported_output_modes=item.supported_output_modes or [],
        context_window_tokens=item.context_window_tokens,
        maximum_output_tokens=item.maximum_output_tokens,
        supports_tool_calling=item.supports_tool_calling,
        supports_structured_output=item.supports_structured_output,
        supports_streaming=item.supports_streaming,
        supports_seed=item.supports_seed,
        supports_prompt_caching=item.supports_prompt_caching,
        data_residency_regions=item.data_residency_regions or [],
        data_retention_policy=item.data_retention_policy,
        input_cost_per_million_tokens=item.input_cost_per_million_tokens,
        output_cost_per_million_tokens=item.output_cost_per_million_tokens,
        cached_input_cost_per_million_tokens=item.cached_input_cost_per_million_tokens,
        expected_latency_class=item.expected_latency_class,
        reliability_score=item.reliability_score,
        quality_scores=item.quality_scores or {},
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _tool_response(item: ArceusToolProfile) -> ToolProfileResponse:
    return ToolProfileResponse(
        id=item.id,
        tool_key=item.tool_key,
        display_name=item.display_name,
        adapter_type=item.adapter_type,
        version=item.version,
        capabilities=item.capabilities or [],
        supported_actions=item.supported_actions or [],
        risk_level=item.risk_level,
        side_effect_class=item.side_effect_class,
        requires_sandbox=item.requires_sandbox,
        supports_dry_run=item.supports_dry_run,
        supports_idempotency=item.supports_idempotency,
        supports_rollback=item.supports_rollback,
        required_authorities=item.required_authorities or [],
        allowed_environments=item.allowed_environments or [],
        maximum_runtime_seconds=item.maximum_runtime_seconds,
        output_schema_key=item.output_schema_key,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _routing_response(item: ArceusRoutingDecision) -> RoutingDecisionResponse:
    return RoutingDecisionResponse(
        id=item.id,
        request_id=item.request_id,
        selected_model_key=item.selected_model_key,
        selected_provider_key=item.selected_provider_key,
        selected_tool_key=item.selected_tool_key,
        selected_action_key=item.selected_action_key,
        fallback_model_keys=item.fallback_model_keys or [],
        candidate_scores=item.candidate_scores or {},
        hard_exclusions=item.hard_exclusions or {},
        applied_policy_ids=[str(policy_id) for policy_id in (item.applied_policy_ids or [])],
        estimated_input_tokens=item.estimated_input_tokens,
        estimated_output_tokens=item.estimated_output_tokens,
        estimated_cost_usd=item.estimated_cost_usd,
        estimated_latency_ms=item.estimated_latency_ms,
        reasoning_summary=item.reasoning_summary,
        decision_hash=item.decision_hash,
    )


def _ledger_response(item: ArceusAIExecutionLedger) -> ExecutionLedgerResponse:
    return ExecutionLedgerResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        execution_kind=item.execution_kind,
        task_type=item.task_type,
        provider_key=item.provider_key,
        model_key=item.model_key,
        tool_key=item.tool_key,
        action_key=item.action_key,
        status=item.status,
        estimated_cost=item.estimated_cost,
        actual_cost=item.actual_cost,
        latency_ms=item.latency_ms,
        result=item.result or {},
        error=item.error or {},
        created_at=item.created_at,
    )


def _budget_response(item: ArceusBudget) -> BudgetResponse:
    return BudgetResponse(
        id=item.id,
        scope_type=item.scope_type,
        scope_id=item.scope_id,
        currency=item.currency,
        limit_amount=item.limit_amount,
        reserved_amount=item.reserved_amount,
        actual_amount=item.actual_amount,
        warning_threshold_percent=item.warning_threshold_percent,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/api/v1/models")
def list_models(request: Request, context: RequestContext = Depends(require_permission("model_registry.view")), db: Session = Depends(get_db)):
    items = db.query(ArceusModelProfile).order_by(ArceusModelProfile.model_key.asc()).all()
    return collection_response([_model_response(item).model_dump(mode="json") for item in items], request)


@router.get("/api/v1/models/{model_key}")
def get_model(model_key: str, request: Request, context: RequestContext = Depends(require_permission("model_registry.view")), db: Session = Depends(get_db)):
    item = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == model_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Model profile not found.")
    return api_response(_model_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/admin/models")
def create_model(payload: ModelProfileRequest, request: Request, context: RequestContext = Depends(require_permission("model_registry.manage")), db: Session = Depends(get_db)):
    if db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == payload.model_key).first():
        raise HTTPException(status_code=409, detail="Model profile already exists.")
    if not db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == payload.provider_key).first():
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    item = ArceusModelProfile(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return api_response(_model_response(item).model_dump(mode="json"), request)


@router.patch("/api/v1/admin/models/{model_key}")
def update_model(model_key: str, payload: ModelProfileRequest, request: Request, context: RequestContext = Depends(require_permission("model_registry.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == model_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Model profile not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.version = int(item.version or 1) + 1
    db.commit()
    db.refresh(item)
    return api_response(_model_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/admin/models/{model_key}/enable")
def enable_model(model_key: str, request: Request, context: RequestContext = Depends(require_permission("model_registry.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == model_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Model profile not found.")
    item.status = "available"
    item.version = int(item.version or 1) + 1
    db.commit()
    db.refresh(item)
    return api_response(_model_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/admin/models/{model_key}/disable")
def disable_model(model_key: str, request: Request, context: RequestContext = Depends(require_permission("model_registry.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == model_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Model profile not found.")
    item.status = "disabled"
    item.version = int(item.version or 1) + 1
    db.commit()
    db.refresh(item)
    return api_response(_model_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/providers")
def list_providers(request: Request, context: RequestContext = Depends(require_permission("provider_registry.view")), db: Session = Depends(get_db)):
    items = db.query(ArceusProviderProfile).order_by(ArceusProviderProfile.provider_key.asc()).all()
    return collection_response([_provider_response(item).model_dump(mode="json") for item in items], request)


@router.get("/api/v1/providers/{provider_key}/health")
def get_provider_health(provider_key: str, request: Request, context: RequestContext = Depends(require_permission("provider_registry.view")), db: Session = Depends(get_db)):
    item = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == provider_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    return api_response(_provider_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/admin/providers")
def create_provider(payload: ProviderProfileRequest, request: Request, context: RequestContext = Depends(require_permission("provider_registry.manage")), db: Session = Depends(get_db)):
    if db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == payload.provider_key).first():
        raise HTTPException(status_code=409, detail="Provider profile already exists.")
    item = ArceusProviderProfile(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return api_response(_provider_response(item).model_dump(mode="json"), request)


@router.patch("/api/v1/admin/providers/{provider_key}")
def update_provider(provider_key: str, payload: ProviderProfileRequest, request: Request, context: RequestContext = Depends(require_permission("provider_registry.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == provider_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.version = int(item.version or 1) + 1
    db.commit()
    db.refresh(item)
    return api_response(_provider_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/admin/providers/{provider_key}/test")
def test_provider(provider_key: str, request: Request, context: RequestContext = Depends(require_permission("provider_registry.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == provider_key).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    try:
        result = adapter_for(item).health_check(provider=item)
    except Exception as exc:
        result = {"status": "misconfigured", "reason": str(exc), "provider_key": provider_key}
    item.health_status = result.get("status", item.health_status)
    item.circuit_state = "open" if item.health_status == "misconfigured" else item.circuit_state
    item.version = int(item.version or 1) + 1
    db.commit()
    return api_response(result, request)


@router.post("/api/v1/ai/route")
def route_ai_request(payload: AIExecutionRequest, request: Request, context: RequestContext = Depends(require_permission("ai.route")), db: Session = Depends(get_db)):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    providers = db.query(ArceusProviderProfile).all()
    models = db.query(ArceusModelProfile).all()
    decision = route_model_request(tenant_id=context.tenant_id, request=payload, models=models, providers=providers)
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return api_response(_routing_response(decision).model_dump(mode="json"), request)


@router.post("/api/v1/ai/execute")
def execute_ai_request(payload: AIExecutionRequest, request: Request, context: RequestContext = Depends(require_permission("ai.execute")), db: Session = Depends(get_db)):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    existing = db.query(ArceusRoutingDecision).filter(ArceusRoutingDecision.tenant_id == context.tenant_id, ArceusRoutingDecision.request_id == payload.request_id).first()
    decision = existing or route_model_request(
        tenant_id=context.tenant_id,
        request=payload,
        models=db.query(ArceusModelProfile).all(),
        providers=db.query(ArceusProviderProfile).all(),
    )
    if existing is None:
        db.add(decision)
        db.flush()
    if not decision.selected_model_key:
        ledger = ArceusAIExecutionLedger(
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            execution_kind="model",
            task_type=payload.task_type,
            request_hash=execution_request_hash(payload.model_dump(mode="json")),
            status="failed",
            routing_decision_id=decision.id,
            error={"code": "NO_ROUTE", "hard_exclusions": decision.hard_exclusions},
        )
        db.add(ledger)
        db.commit()
        raise HTTPException(status_code=409, detail={"code": "NO_POLICY_COMPATIBLE_MODEL", "hard_exclusions": decision.hard_exclusions})
    attempt_model_keys = [decision.selected_model_key, *(decision.fallback_model_keys or [])]
    try:
        reservation = reserve_budget(
            db=db,
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            amount=Decimal(decision.estimated_cost_usd or 0),
            idempotency_key=f"ai:{payload.idempotency_key}:budget",
        )
    except BudgetExceededError as exc:
        db.commit()
        raise HTTPException(
            status_code=402,
            detail={
                "code": "BUDGET_EXCEEDED",
                "budget_id": str(exc.budget_id),
                "requested": str(exc.requested),
                "remaining": str(exc.remaining),
            },
        )
    attempt_errors: list[dict[str, str]] = []
    provider = None
    selected_model = None
    compiled_prompt = None
    provider_response = None
    validation = None
    fallback_used = False
    for attempt_index, model_key in enumerate(attempt_model_keys):
        selected_model = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == model_key).first()
        provider = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.provider_key == selected_model.provider_key).first() if selected_model is not None else None
        if provider is None or selected_model is None:
            attempt_errors.append({"model_key": str(model_key), "code": "ROUTED_PROFILE_MISSING"})
            continue
        try:
            compiled_prompt = compile_prompt(request=payload, model=selected_model, routing=decision)
            provider_response = adapter_for(provider).generate(provider=provider, model=selected_model, prompt=compiled_prompt, request=payload)
            validation = validate_model_output(provider_response.output, payload.required_output_schema)
            if validation.status == "valid":
                fallback_used = attempt_index > 0
                break
            record_provider_failure(provider, ";".join(validation.errors))
            attempt_errors.append({"model_key": model_key, "code": "MODEL_OUTPUT_VALIDATION_FAILED", "message": ",".join(validation.errors)})
        except Exception as exc:
            record_provider_failure(provider, str(exc))
            attempt_errors.append({"model_key": str(model_key), "code": "PROVIDER_EXECUTION_FAILED", "message": str(exc)})
            continue
    if provider_response is None or compiled_prompt is None or validation is None:
        release_budget(db=db, reservation=reservation)
        ledger = ArceusAIExecutionLedger(
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            execution_kind="model",
            task_type=payload.task_type,
            provider_key=decision.selected_provider_key,
            model_key=decision.selected_model_key,
            request_hash=execution_request_hash(payload.model_dump(mode="json")),
            context_hash=None,
            status="failed",
            estimated_cost=decision.estimated_cost_usd,
            routing_decision_id=decision.id,
            cost_reservation_id=reservation.id if reservation is not None else None,
            completed_at=datetime.now(timezone.utc),
            error={"code": "PROVIDER_EXECUTION_FAILED", "attempts": attempt_errors},
        )
        db.add(ledger)
        db.commit()
        raise HTTPException(status_code=502, detail={"code": "PROVIDER_EXECUTION_FAILED", "attempts": attempt_errors})
    output = validation.normalized_output
    response_hash = provider_response.response_hash
    status = "completed" if validation.status == "valid" else "failed"
    settle_budget(db=db, reservation=reservation, actual_amount=Decimal(provider_response.cost_usd or 0))
    if validation.status == "valid":
        record_provider_success(provider)
    ledger = ArceusAIExecutionLedger(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        execution_kind="model",
        task_type=payload.task_type,
        provider_key=provider_response.provider_key,
        model_key=provider_response.model_key,
        request_hash=execution_request_hash(payload.model_dump(mode="json")),
        context_hash=compiled_prompt.content_hash,
        response_hash=response_hash,
        status=status,
        input_tokens=provider_response.input_tokens,
        output_tokens=provider_response.output_tokens,
        cached_input_tokens=provider_response.cached_input_tokens,
        estimated_cost=decision.estimated_cost_usd,
        actual_cost=provider_response.cost_usd,
        latency_ms=provider_response.latency_ms,
        fallback_used=fallback_used,
        routing_decision_id=decision.id,
        cost_reservation_id=reservation.id if reservation is not None else None,
        completed_at=datetime.now(timezone.utc),
        result={
            "normalized_output": output,
            "validation_status": validation.status,
            "finish_reason": provider_response.finish_reason,
            "raw_response_reference": provider_response.raw_response_reference,
            "prompt_hash": compiled_prompt.content_hash,
            "context_items": len(compiled_prompt.context_items),
            "attempts": attempt_errors,
        },
        error={} if validation.status == "valid" else {"validation_errors": validation.errors},
    )
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    if validation.status != "valid":
        raise HTTPException(status_code=422, detail={"code": "MODEL_OUTPUT_VALIDATION_FAILED", "errors": validation.errors, "execution_id": str(ledger.id)})
    response = ModelExecutionResultResponse(
        execution_id=ledger.id,
        request_id=payload.request_id,
        provider_key=ledger.provider_key,
        model_key=ledger.model_key,
        normalized_output=output,
        finish_reason=provider_response.finish_reason,
        validation_status=validation.status,
        input_tokens=ledger.input_tokens,
        output_tokens=ledger.output_tokens,
        cached_input_tokens=ledger.cached_input_tokens,
        latency_ms=ledger.latency_ms or 0,
        cost_usd=ledger.actual_cost,
        retry_count=ledger.retry_count,
        fallback_used=ledger.fallback_used,
        response_hash=response_hash,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/ai/executions/{execution_id}")
def get_ai_execution(execution_id: UUID, request: Request, context: RequestContext = Depends(require_permission("model_execution.view")), db: Session = Depends(get_db)):
    item = db.query(ArceusAIExecutionLedger).filter(ArceusAIExecutionLedger.tenant_id == context.tenant_id, ArceusAIExecutionLedger.id == execution_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return api_response(_ledger_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/ai/executions/{execution_id}/evaluation")
def get_ai_execution_evaluation(execution_id: UUID, request: Request, context: RequestContext = Depends(require_permission("model_execution.view"))):
    return api_response({"execution_id": str(execution_id), "status": "pending_evaluation"}, request)


@router.get("/api/v1/tools")
def list_tools(request: Request, context: RequestContext = Depends(require_permission("tool_registry.view")), db: Session = Depends(get_db)):
    items = db.query(ArceusToolProfile).order_by(ArceusToolProfile.tool_key.asc()).all()
    return collection_response([_tool_response(item).model_dump(mode="json") for item in items], request)


@router.post("/api/v1/admin/tools")
def create_tool(payload: ToolProfileRequest, request: Request, context: RequestContext = Depends(require_permission("tool_registry.manage")), db: Session = Depends(get_db)):
    if db.query(ArceusToolProfile).filter(ArceusToolProfile.tool_key == payload.tool_key).first():
        raise HTTPException(status_code=409, detail="Tool profile already exists.")
    item = ArceusToolProfile(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return api_response(_tool_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/tools/authorize")
def authorize_tool_request(payload: ToolExecutionRequest, request: Request, context: RequestContext = Depends(require_permission("tool.authorize")), db: Session = Depends(get_db)):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    profile = db.query(ArceusToolProfile).filter(ArceusToolProfile.tool_key == payload.tool_key).first()
    authorized, reasons = authorize_tool(profile, payload)
    response = ToolAuthorizationResponse(
        authorized=authorized,
        denial_reasons=reasons,
        tool_key=payload.tool_key,
        action_key=payload.action_key,
        side_effect_class=profile.side_effect_class if profile else None,
        requires_approval=bool(profile and profile.side_effect_class in {"LOCAL_MUTATION", "REPOSITORY_MUTATION", "EXTERNAL_REVERSIBLE", "EXTERNAL_IRREVERSIBLE", "PRODUCTION_CHANGE", "FINANCIAL_ACTION", "SECRET_ACCESS"}),
        requires_sandbox=bool(profile and profile.requires_sandbox),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/tools/execute")
def execute_tool_request(payload: ToolExecutionRequest, request: Request, context: RequestContext = Depends(require_permission("tool.execute")), db: Session = Depends(get_db)):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    profile = db.query(ArceusToolProfile).filter(ArceusToolProfile.tool_key == payload.tool_key).first()
    authorized, reasons = authorize_tool(profile, payload)
    ledger = ArceusAIExecutionLedger(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        execution_kind="tool",
        task_type="tool_execution",
        tool_key=payload.tool_key,
        action_key=payload.action_key,
        request_hash=execution_request_hash(payload.model_dump(mode="json")),
        status="completed" if authorized else "denied",
        completed_at=datetime.now(timezone.utc) if authorized else None,
        result={"dry_run": payload.dry_run, "authorized": authorized, "expected_outputs": payload.expected_outputs},
        error={} if authorized else {"denial_reasons": reasons},
    )
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    if not authorized:
        raise HTTPException(status_code=403, detail={"code": "TOOL_AUTHORIZATION_DENIED", "reasons": reasons, "execution_id": str(ledger.id)})
    return api_response(_ledger_response(ledger).model_dump(mode="json"), request)


@router.get("/api/v1/tools/executions/{execution_id}")
def get_tool_execution(execution_id: UUID, request: Request, context: RequestContext = Depends(require_permission("tool_execution.view")), db: Session = Depends(get_db)):
    item = db.query(ArceusAIExecutionLedger).filter(
        ArceusAIExecutionLedger.tenant_id == context.tenant_id,
        ArceusAIExecutionLedger.id == execution_id,
        ArceusAIExecutionLedger.execution_kind == "tool",
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Tool execution not found.")
    return api_response(_ledger_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/tools/executions/{execution_id}/rollback")
def rollback_tool_execution(execution_id: UUID, request: Request, context: RequestContext = Depends(require_permission("tool.execute")), db: Session = Depends(get_db)):
    item = db.query(ArceusAIExecutionLedger).filter(ArceusAIExecutionLedger.tenant_id == context.tenant_id, ArceusAIExecutionLedger.id == execution_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Tool execution not found.")
    item.result = {**(item.result or {}), "rollback_requested": True}
    item.status = "completed"
    db.commit()
    return api_response(_ledger_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/budgets/{scope_type}/{scope_id}")
def get_budget(scope_type: str, scope_id: UUID, request: Request, context: RequestContext = Depends(require_permission("budget.view")), db: Session = Depends(get_db)):
    item = db.query(ArceusBudget).filter(ArceusBudget.tenant_id == context.tenant_id, ArceusBudget.scope_type == scope_type, ArceusBudget.scope_id == scope_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Budget not found.")
    return api_response(_budget_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/budgets")
def create_budget(payload: BudgetRequest, request: Request, context: RequestContext = Depends(require_permission("budget.manage")), db: Session = Depends(get_db)):
    item = ArceusBudget(tenant_id=context.tenant_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return api_response(_budget_response(item).model_dump(mode="json"), request)


@router.patch("/api/v1/budgets/{budget_id}")
def update_budget(budget_id: UUID, payload: BudgetRequest, request: Request, context: RequestContext = Depends(require_permission("budget.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusBudget).filter(ArceusBudget.tenant_id == context.tenant_id, ArceusBudget.id == budget_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Budget not found.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return api_response(_budget_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/budgets/{budget_id}/request-increase")
def request_budget_increase(budget_id: UUID, request: Request, context: RequestContext = Depends(require_permission("budget.manage")), db: Session = Depends(get_db)):
    item = db.query(ArceusBudget).filter(ArceusBudget.tenant_id == context.tenant_id, ArceusBudget.id == budget_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Budget not found.")
    return api_response({"budget_id": str(budget_id), "status": "increase_requested"}, request)


@router.get("/api/v1/costs/missions/{mission_id}")
def mission_costs(mission_id: UUID, request: Request, context: RequestContext = Depends(require_permission("budget.view")), db: Session = Depends(get_db)):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    rows = db.query(ArceusAIExecutionLedger).filter(ArceusAIExecutionLedger.tenant_id == context.tenant_id, ArceusAIExecutionLedger.mission_id == mission_id).all()
    estimated = sum(Decimal(row.estimated_cost or 0) for row in rows)
    actual = sum(Decimal(row.actual_cost or 0) for row in rows)
    return api_response({"mission_id": str(mission_id), "execution_count": len(rows), "estimated_cost": str(estimated), "actual_cost": str(actual)}, request)
