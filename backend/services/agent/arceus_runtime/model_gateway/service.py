from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import ArceusAIExecutionLedger, ArceusModelProfile, ArceusProviderProfile, ArceusRoutingDecision

from ..compiler.utils import stable_hash
from .api_schemas import (
    ModelCandidateResponse,
    ModelCostEstimateResponse,
    ModelGatewayRequest,
    ModelInferenceResponse,
    ModelRoutingResponse,
    ProviderHealthResponse,
)


LATENCY_MS = {"ultra_low": 300, "low": 800, "medium": 3000, "high": 9000, "batch": 30000}


def estimate_tokens(payload: ModelGatewayRequest) -> tuple[int, int]:
    prompt_text = " ".join([payload.objective, payload.prompt or ""])
    estimated_input = payload.maximum_input_tokens or max(512, min(200_000, int(len(prompt_text.split()) * 1.6) + 768))
    estimated_output = payload.maximum_output_tokens or 2048
    return estimated_input, estimated_output


def estimate_cost(model: ArceusModelProfile, input_tokens: int, output_tokens: int, *, cached_input_tokens: int = 0) -> Decimal:
    uncached = max(0, input_tokens - cached_input_tokens)
    cached_rate = Decimal(model.cached_input_cost_per_million_tokens if model.cached_input_cost_per_million_tokens is not None else model.input_cost_per_million_tokens or 0)
    input_cost = (Decimal(uncached) / Decimal(1_000_000)) * Decimal(model.input_cost_per_million_tokens or 0)
    cached_cost = (Decimal(cached_input_tokens) / Decimal(1_000_000)) * cached_rate
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * Decimal(model.output_cost_per_million_tokens or 0)
    return (input_cost + cached_cost + output_cost).quantize(Decimal("0.00000001"))


def model_hard_exclusions(payload: ModelGatewayRequest, models: list[ArceusModelProfile], providers: dict[str, ArceusProviderProfile]) -> dict[str, list[str]]:
    input_tokens, output_tokens = estimate_tokens(payload)
    excluded: dict[str, list[str]] = {}
    for model in models:
        reasons: list[str] = []
        provider = providers.get(model.provider_key)
        if provider is None:
            reasons.append("provider_missing")
        else:
            if not provider.enabled:
                reasons.append("provider_disabled")
            if provider.circuit_state == "open":
                reasons.append("provider_circuit_open")
            if provider.health_status in {"unavailable", "misconfigured", "disabled"}:
                reasons.append(f"provider_{provider.health_status}")
        if model.status not in {"available", "degraded"}:
            reasons.append(f"model_{model.status}")
        if payload.allowed_provider_keys and model.provider_key not in payload.allowed_provider_keys:
            reasons.append("provider_not_allowed")
        if model.provider_key in payload.prohibited_provider_keys:
            reasons.append("provider_prohibited")
        if payload.required_region and payload.required_region not in (model.data_residency_regions or []) and "global" not in (model.data_residency_regions or []):
            reasons.append("region_unavailable")
        if model.context_window_tokens < input_tokens + output_tokens:
            reasons.append("context_window_too_small")
        if model.maximum_output_tokens < output_tokens:
            reasons.append("maximum_output_too_small")
        if payload.required_output_schema and not model.supports_structured_output:
            reasons.append("structured_output_unsupported")
        if payload.allow_streaming and not model.supports_streaming:
            reasons.append("streaming_unsupported")
        if payload.allow_tool_calling and not model.supports_tool_calling:
            reasons.append("tool_calling_unsupported")
        if payload.allow_prompt_caching and payload.routing_mode != "latency_first" and not model.supports_prompt_caching:
            # Soft in spirit, but hard for this endpoint when caching is explicitly allowed for cost control.
            pass
        if payload.deterministic_required and not model.supports_seed:
            reasons.append("determinism_unsupported")
        if payload.sensitivity in {"restricted", "secret"} and model.data_retention_policy not in {"zero_retention", "local"}:
            reasons.append("retention_policy_incompatible")
        missing = sorted(set(payload.required_capabilities) - set(model.capabilities or []))
        if missing:
            reasons.append("missing_capabilities:" + ",".join(missing))
        modalities = sorted(set(payload.required_modalities) - set(model.supported_modalities or ["text"]))
        if modalities:
            reasons.append("missing_modalities:" + ",".join(modalities))
        estimated_cost = estimate_cost(model, input_tokens, output_tokens)
        if payload.maximum_cost_usd is not None and estimated_cost > payload.maximum_cost_usd:
            reasons.append("estimated_cost_exceeds_limit")
        if payload.maximum_latency_ms is not None and latency_for_model(model) > payload.maximum_latency_ms * 2:
            reasons.append("latency_out_of_bounds")
        if reasons:
            excluded[model.model_key] = reasons
    return excluded


def latency_for_model(model: ArceusModelProfile) -> int:
    return LATENCY_MS.get(str(model.expected_latency_class or "medium"), 3000)


def score_model(payload: ModelGatewayRequest, model: ArceusModelProfile, provider: ArceusProviderProfile, input_tokens: int, output_tokens: int) -> tuple[float, dict[str, float], Decimal]:
    required = set(payload.required_capabilities)
    available = set(model.capabilities or [])
    capability = 1.0 if not required else len(required & available) / max(1, len(required))
    quality = float((model.quality_scores or {}).get(payload.task_type, (model.quality_scores or {}).get("general", 0.72)))
    reliability = float(model.reliability_score or 0.75)
    if provider.health_status == "degraded" or model.status == "degraded":
        reliability *= 0.82
    latency_ms = latency_for_model(model)
    latency = min(1.0, 1000.0 / max(1.0, latency_ms))
    cost = estimate_cost(model, input_tokens, output_tokens, cached_input_tokens=int(input_tokens * 0.2) if model.supports_prompt_caching and payload.allow_prompt_caching else 0)
    cost_limit = payload.maximum_cost_usd or Decimal("1")
    cost_efficiency = float(max(Decimal("0"), min(Decimal("1"), Decimal("1") - (cost / max(cost_limit, Decimal("0.00000001"))))))
    privacy = {"local": 1.0, "zero_retention": 0.95, "enterprise": 0.86, "standard": 0.55}.get(str(model.data_retention_policy or "standard"), 0.55)
    structured = 1.0 if (not payload.required_output_schema or model.supports_structured_output) else 0.0
    context_fit = min(1.0, float(model.context_window_tokens) / float(max(input_tokens + output_tokens, 1)))
    weights = {
        "quality_first": (0.38, 0.09, 0.10, 0.12, 0.17),
        "latency_first": (0.22, 0.28, 0.11, 0.10, 0.15),
        "cost_first": (0.22, 0.10, 0.32, 0.10, 0.13),
        "privacy_first": (0.25, 0.08, 0.10, 0.30, 0.13),
        "balanced": (0.29, 0.14, 0.17, 0.15, 0.17),
    }[payload.routing_mode]
    score = (
        weights[0] * quality
        + weights[1] * latency
        + weights[2] * cost_efficiency
        + weights[3] * privacy
        + weights[4] * reliability
        + 0.06 * capability
        + 0.03 * structured
        + 0.02 * context_fit
    )
    breakdown = {
        "quality": round(quality, 4),
        "latency": round(latency, 4),
        "cost_efficiency": round(cost_efficiency, 4),
        "privacy": round(privacy, 4),
        "reliability": round(reliability, 4),
        "capability": round(capability, 4),
        "structured_output": round(structured, 4),
        "context_fit": round(context_fit, 4),
    }
    return round(max(0.0, min(1.0, score)), 4), breakdown, cost


def route_models(payload: ModelGatewayRequest, models: list[ArceusModelProfile], providers: list[ArceusProviderProfile]) -> ModelRoutingResponse:
    provider_map = {provider.provider_key: provider for provider in providers}
    input_tokens, output_tokens = estimate_tokens(payload)
    excluded = model_hard_exclusions(payload, models, provider_map)
    candidates: list[ModelCandidateResponse] = []
    for model in models:
        if model.model_key in excluded:
            continue
        provider = provider_map.get(model.provider_key)
        if provider is None:
            continue
        score, breakdown, cost = score_model(payload, model, provider, input_tokens, output_tokens)
        candidates.append(
            ModelCandidateResponse(
                provider_key=model.provider_key,
                model_key=model.model_key,
                display_name=model.display_name,
                capabilities=list(model.capabilities or []),
                context_window_tokens=model.context_window_tokens,
                maximum_output_tokens=model.maximum_output_tokens,
                supports_streaming=model.supports_streaming,
                supports_tool_calling=model.supports_tool_calling,
                supports_structured_output=model.supports_structured_output,
                supports_prompt_caching=model.supports_prompt_caching,
                data_retention_policy=model.data_retention_policy,
                expected_latency_ms=latency_for_model(model),
                estimated_cost_usd=cost,
                score=score,
                score_breakdown=breakdown,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    selected = candidates[0] if candidates else None
    fallbacks = [item.model_key for item in candidates[1:4]]
    decision_hash = stable_hash(
        {
            "request_id": str(payload.request_id),
            "selected": selected.model_key if selected else None,
            "scores": {item.model_key: item.score for item in candidates},
            "excluded": excluded,
        }
    )
    return ModelRoutingResponse(
        request_id=payload.request_id,
        selected_provider_key=selected.provider_key if selected else None,
        selected_model_key=selected.model_key if selected else None,
        fallback_model_keys=fallbacks,
        candidates=candidates,
        hard_exclusions=excluded,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=selected.estimated_cost_usd if selected else Decimal("0"),
        estimated_latency_ms=selected.expected_latency_ms if selected else 0,
        reasoning_summary=(
            f"Selected {selected.display_name} via {payload.routing_mode} routing with score {selected.score:.2f}."
            if selected
            else "No policy-compatible model candidate was available."
        ),
        decision_hash=decision_hash,
        events=["MODEL_ROUTE_REQUESTED", "MODEL_SELECTED" if selected else "MODEL_ROUTE_BLOCKED"],
    )


def estimate_gateway_cost(payload: ModelGatewayRequest, models: list[ArceusModelProfile], providers: list[ArceusProviderProfile]) -> ModelCostEstimateResponse:
    routing = route_models(payload, models, providers)
    by_cost = sorted(routing.candidates, key=lambda item: item.estimated_cost_usd)
    by_latency = sorted(routing.candidates, key=lambda item: item.expected_latency_ms)
    by_quality = sorted(routing.candidates, key=lambda item: item.score_breakdown.get("quality", 0), reverse=True)
    return ModelCostEstimateResponse(
        request_id=payload.request_id,
        estimated_input_tokens=routing.estimated_input_tokens,
        estimated_output_tokens=routing.estimated_output_tokens,
        by_model=routing.candidates,
        cheapest_model_key=by_cost[0].model_key if by_cost else None,
        fastest_model_key=by_latency[0].model_key if by_latency else None,
        highest_quality_model_key=by_quality[0].model_key if by_quality else None,
    )


def dry_run_inference(payload: ModelGatewayRequest, routing: ModelRoutingResponse) -> ModelInferenceResponse:
    response = {
        "mode": "dry_run",
        "selected_model": routing.selected_model_key,
        "objective": payload.objective,
        "next_step": "Connect provider adapter execution to run live inference.",
    }
    return ModelInferenceResponse(
        request_id=payload.request_id,
        execution_id=None,
        provider_key=routing.selected_provider_key,
        model_key=routing.selected_model_key,
        status="planned" if routing.selected_model_key else "blocked",
        normalized_output=response if routing.selected_model_key else {"error": "No model candidate available."},
        finish_reason="dry_run",
        input_tokens=routing.estimated_input_tokens,
        output_tokens=0,
        cached_input_tokens=0,
        latency_ms=routing.estimated_latency_ms,
        cost_usd=Decimal("0"),
        fallback_used=False,
        response_hash=stable_hash(response),
        routing=routing,
    )


def provider_health(providers: list[ArceusProviderProfile], models: list[ArceusModelProfile]) -> list[ProviderHealthResponse]:
    rows: list[ProviderHealthResponse] = []
    for provider in providers:
        provider_models = [model for model in models if model.provider_key == provider.provider_key]
        available = [model for model in provider_models if model.status == "available"]
        reasons: list[str] = []
        if not provider.enabled:
            reasons.append("provider_disabled")
        if provider.circuit_state == "open":
            reasons.append("circuit_open")
        if provider.health_status in {"unavailable", "misconfigured", "disabled"}:
            reasons.append(f"health_{provider.health_status}")
        if not available:
            reasons.append("no_available_models")
        readiness = "blocked" if reasons else ("degraded" if provider.health_status == "degraded" else "ready")
        rows.append(
            ProviderHealthResponse(
                provider_key=provider.provider_key,
                enabled=provider.enabled,
                health_status=provider.health_status,
                circuit_state=provider.circuit_state,
                model_count=len(provider_models),
                available_model_count=len(available),
                readiness=readiness,
                reasons=reasons or ["provider_ready"],
            )
        )
    return rows


def routing_decision_record(payload: ModelGatewayRequest, tenant_id: UUID, routing: ModelRoutingResponse) -> ArceusRoutingDecision:
    if payload.mission_id is None:
        raise ValueError("routing_decision_record requires a mission_id")
    return ArceusRoutingDecision(
        tenant_id=tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        request_id=payload.request_id,
        execution_kind="model",
        task_type=payload.task_type,
        routing_mode=payload.routing_mode,
        selected_model_key=routing.selected_model_key,
        selected_provider_key=routing.selected_provider_key,
        fallback_model_keys=routing.fallback_model_keys,
        candidate_scores={item.model_key: item.score for item in routing.candidates},
        hard_exclusions=routing.hard_exclusions,
        applied_policy_ids=[],
        estimated_input_tokens=routing.estimated_input_tokens,
        estimated_output_tokens=routing.estimated_output_tokens,
        estimated_cost_usd=routing.estimated_cost_usd,
        estimated_latency_ms=routing.estimated_latency_ms,
        reasoning_summary=routing.reasoning_summary,
        decision_hash=routing.decision_hash,
    )


def execution_ledger_record(payload: ModelGatewayRequest, tenant_id: UUID, inference: ModelInferenceResponse) -> ArceusAIExecutionLedger:
    if payload.mission_id is None:
        raise ValueError("execution_ledger_record requires a mission_id")
    return ArceusAIExecutionLedger(
        tenant_id=tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        execution_kind="model",
        task_type=payload.task_type,
        provider_key=inference.provider_key,
        model_key=inference.model_key,
        request_hash=stable_hash(payload.model_dump(mode="json")),
        response_hash=inference.response_hash,
        status="completed" if inference.status == "planned" else "denied",
        input_tokens=inference.input_tokens,
        output_tokens=inference.output_tokens,
        cached_input_tokens=inference.cached_input_tokens,
        estimated_cost=inference.routing.estimated_cost_usd,
        actual_cost=inference.cost_usd,
        latency_ms=inference.latency_ms,
        result={"normalized_output": inference.normalized_output, "finish_reason": inference.finish_reason, "dry_run": payload.dry_run},
        error={} if inference.status != "blocked" else {"message": "No model candidate available."},
    )
