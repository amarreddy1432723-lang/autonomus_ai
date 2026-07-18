from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import (
    ArceusAIExecutionLedger,
    ArceusBudget,
    ArceusCostReservation,
    ArceusModelProfile,
    ArceusProviderProfile,
    ArceusRoutingDecision,
    ArceusToolProfile,
)

from .api_schemas import AIExecutionRequest, ToolExecutionRequest


LATENCY_MS = {"low": 800, "medium": 3000, "high": 9000}
RISKY_SIDE_EFFECTS = {"LOCAL_MUTATION", "REPOSITORY_MUTATION", "EXTERNAL_REVERSIBLE", "EXTERNAL_IRREVERSIBLE", "PRODUCTION_CHANGE", "FINANCIAL_ACTION", "SECRET_ACCESS"}


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def estimate_tokens(request: AIExecutionRequest) -> tuple[int, int]:
    input_tokens = request.maximum_input_tokens or max(256, min(8192, len(request.objective.split()) * 2 + 512))
    output_tokens = request.maximum_output_tokens or 1024
    return input_tokens, output_tokens


def estimate_cost(model: ArceusModelProfile, input_tokens: int, output_tokens: int) -> Decimal:
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * Decimal(model.input_cost_per_million_tokens or 0)
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * Decimal(model.output_cost_per_million_tokens or 0)
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))


def _capability_match(model: ArceusModelProfile, required: list[str]) -> float:
    if not required:
        return 1.0
    available = set(model.capabilities or [])
    matched = len([item for item in required if item in available])
    return matched / len(required)


def hard_exclusions(
    *,
    request: AIExecutionRequest,
    models: list[ArceusModelProfile],
    providers: dict[str, ArceusProviderProfile],
) -> dict[str, list[str]]:
    input_tokens, output_tokens = estimate_tokens(request)
    exclusions: dict[str, list[str]] = {}
    for model in models:
        reasons: list[str] = []
        provider = providers.get(model.provider_key)
        if provider is None:
            reasons.append("provider_missing")
        elif not provider.enabled or provider.health_status == "disabled":
            reasons.append("provider_disabled")
        elif provider.circuit_state == "open":
            reasons.append("provider_circuit_open")
        elif provider.health_status in {"unavailable", "misconfigured"}:
            reasons.append(f"provider_{provider.health_status}")
        if model.status != "available":
            reasons.append(f"model_{model.status}")
        if request.allowed_provider_keys and model.provider_key not in request.allowed_provider_keys:
            reasons.append("provider_not_allowed")
        if model.provider_key in request.prohibited_provider_keys:
            reasons.append("provider_prohibited")
        if request.required_region and request.required_region not in (model.data_residency_regions or []) and "global" not in (model.data_residency_regions or []):
            reasons.append("region_unavailable")
        if model.context_window_tokens < input_tokens + output_tokens:
            reasons.append("context_window_too_small")
        if request.required_output_schema and not model.supports_structured_output:
            reasons.append("structured_output_unsupported")
        if request.deterministic_required and not model.supports_seed:
            reasons.append("determinism_unsupported")
        if request.sensitivity in {"secret", "restricted"} and model.data_retention_policy not in {"zero_retention", "local"}:
            reasons.append("retention_policy_incompatible")
        if request.risk_level in {"critical"} and "local_execution" not in (model.capabilities or []) and request.sensitivity == "restricted":
            reasons.append("critical_restricted_requires_local")
        missing_capabilities = [item for item in request.required_capabilities if item not in (model.capabilities or [])]
        if missing_capabilities:
            reasons.append("missing_capabilities:" + ",".join(sorted(missing_capabilities)))
        estimated = estimate_cost(model, input_tokens, output_tokens)
        if request.maximum_cost_usd is not None and estimated > Decimal(request.maximum_cost_usd):
            reasons.append("estimated_cost_exceeds_limit")
        if reasons:
            exclusions[model.model_key] = reasons
    return exclusions


def route_model_request(
    *,
    tenant_id: UUID,
    request: AIExecutionRequest,
    models: list[ArceusModelProfile],
    providers: list[ArceusProviderProfile],
) -> ArceusRoutingDecision:
    provider_map = {item.provider_key: item for item in providers}
    excluded = hard_exclusions(request=request, models=models, providers=provider_map)
    input_tokens, output_tokens = estimate_tokens(request)
    candidates = [model for model in models if model.model_key not in excluded]
    if not candidates:
        return ArceusRoutingDecision(
            tenant_id=tenant_id,
            mission_id=request.mission_id,
            task_id=request.task_id,
            request_id=request.request_id,
            execution_kind=request.execution_kind.value,
            task_type=request.task_type,
            routing_mode=request.routing_mode,
            fallback_model_keys=[],
            candidate_scores={},
            hard_exclusions=excluded,
            applied_policy_ids=[],
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_cost_usd=Decimal("0"),
            estimated_latency_ms=0,
            reasoning_summary="No policy-compatible model candidate was available.",
            decision_hash=stable_hash({"request_id": request.request_id, "excluded": excluded}),
        )

    scored: list[tuple[float, ArceusModelProfile, Decimal, int]] = []
    for model in candidates:
        provider = provider_map[model.provider_key]
        quality = float((model.quality_scores or {}).get(request.task_type, (model.quality_scores or {}).get("general", 0.7)))
        capability = _capability_match(model, request.required_capabilities)
        reliability = float(model.reliability_score or 0)
        latency = LATENCY_MS.get(model.expected_latency_class, 3000)
        latency_fit = 1.0 if request.maximum_latency_ms is None else max(0.0, min(1.0, request.maximum_latency_ms / max(latency, 1)))
        cost = estimate_cost(model, input_tokens, output_tokens)
        cost_limit = Decimal(request.maximum_cost_usd) if request.maximum_cost_usd is not None else Decimal("1")
        cost_efficiency = float(max(Decimal("0"), min(Decimal("1"), Decimal("1") - (cost / max(cost_limit, Decimal("0.00000001"))))))
        structured = 1.0 if (not request.required_output_schema or model.supports_structured_output) else 0.0
        context_fit = min(1.0, float(model.context_window_tokens) / float(max(input_tokens + output_tokens, 1)))
        provider_health = 0.8 if provider.health_status == "degraded" else 1.0
        weights = {"quality_first": (0.38, 0.08, 0.12, 0.08), "cost_first": (0.18, 0.26, 0.12, 0.12), "latency_first": (0.18, 0.12, 0.28, 0.12), "privacy_first": (0.25, 0.08, 0.08, 0.20)}
        quality_w, cost_w, latency_w, reliability_w = weights.get(request.routing_mode, (0.28, 0.16, 0.10, 0.12))
        score = (
            quality_w * quality
            + cost_w * cost_efficiency
            + latency_w * latency_fit
            + reliability_w * reliability
            + 0.12 * capability
            + 0.06 * structured
            + 0.05 * context_fit
            + 0.03 * provider_health
        )
        scored.append((round(score, 4), model, cost, latency))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected_score, selected, cost, latency = scored[0]
    scores = {model.model_key: score for score, model, _, _ in scored}
    fallback = [model.model_key for _, model, _, _ in scored[1:4]]
    decision_hash = stable_hash(
        {
            "request_id": str(request.request_id),
            "selected_model_key": selected.model_key,
            "scores": scores,
            "excluded": excluded,
            "cost": str(cost),
        }
    )
    return ArceusRoutingDecision(
        tenant_id=tenant_id,
        mission_id=request.mission_id,
        task_id=request.task_id,
        request_id=request.request_id,
        execution_kind=request.execution_kind.value,
        task_type=request.task_type,
        routing_mode=request.routing_mode,
        selected_model_key=selected.model_key,
        selected_provider_key=selected.provider_key,
        fallback_model_keys=fallback,
        candidate_scores=scores,
        hard_exclusions=excluded,
        applied_policy_ids=[],
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=cost,
        estimated_latency_ms=latency,
        reasoning_summary=f"Selected {selected.display_name} for {request.task_type}; score {selected_score:.2f}, policy-compatible, estimated cost ${cost}.",
        decision_hash=decision_hash,
    )


def authorize_tool(profile: ArceusToolProfile | None, request: ToolExecutionRequest) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if profile is None:
        return False, ["tool_not_found"]
    if profile.enabled is False:
        reasons.append("tool_disabled")
    if request.action_key not in (profile.supported_actions or []):
        reasons.append("action_not_supported")
    if request.environment not in (profile.allowed_environments or []):
        reasons.append("environment_not_allowed")
    if request.timeout_seconds > int(profile.maximum_runtime_seconds or 0):
        reasons.append("timeout_exceeds_tool_limit")
    if profile.side_effect_class in RISKY_SIDE_EFFECTS and not request.approval_id and not request.dry_run:
        reasons.append("approval_required_for_side_effect")
    if request.secret_reference_ids and profile.side_effect_class != "SECRET_ACCESS":
        reasons.append("secret_access_not_declared")
    if ".." in json.dumps(request.arguments, sort_keys=True):
        reasons.append("path_traversal_pattern_detected")
    return not reasons, reasons


def execution_request_hash(payload: Any) -> str:
    return stable_hash(payload)
