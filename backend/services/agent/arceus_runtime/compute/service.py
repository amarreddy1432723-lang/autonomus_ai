from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..gateway.service import stable_hash


LATENCY_BY_CLASS = {"low": 800, "medium": 3000, "high": 9000}
LOCAL_PRIVACY_TIERS = {"local", "zero_retention"}
CATEGORY_CAPABILITIES = {
    "large_reasoning": {"reasoning", "planning", "architecture_tradeoff_analysis"},
    "fast": {"summarization", "classification", "responsive_ui"},
    "code": {"coding", "code_generation", "python_backend_development", "nextjs_development", "react_development"},
    "vision": {"vision", "ocr", "design_review"},
    "embedding": {"embedding", "retrieval"},
    "verification": {"verification", "security_review", "structured_output"},
}


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _environment(provider: Any, model: Any) -> str:
    provider_key = str(_get(provider, "provider_key", "")).lower()
    adapter = str(_get(provider, "adapter_type", "")).lower()
    capabilities = set(_get(model, "capabilities", []) or [])
    retention = str(_get(model, "data_retention_policy", "")).lower()
    if "local_execution" in capabilities or provider_key in {"ollama", "local", "lmstudio"} or adapter in {"local", "ollama"}:
        return "local"
    if "edge_execution" in capabilities or "edge" in provider_key:
        return "edge"
    if "enterprise" in provider_key or retention == "zero_retention":
        return "enterprise"
    return "cloud"


def _privacy_tier(model: Any, provider: Any) -> str:
    retention = str(_get(model, "data_retention_policy", "standard"))
    if retention in LOCAL_PRIVACY_TIERS or _environment(provider, model) == "local":
        return "high"
    if bool(_get(provider, "supports_zero_retention", False)):
        return "enterprise"
    return "standard"


def compute_resource_from_model(model: Any, provider: Any) -> dict[str, Any]:
    input_cost = _decimal(_get(model, "input_cost_per_million_tokens"))
    output_cost = _decimal(_get(model, "output_cost_per_million_tokens"))
    per_1k = ((input_cost + output_cost) / Decimal("1000")).quantize(Decimal("0.00000001"))
    latency_ms = LATENCY_BY_CLASS.get(str(_get(model, "expected_latency_class", "medium")), 3000)
    reliability = float(_get(model, "reliability_score", 0.85) or 0.85)
    provider_health = str(_get(provider, "health_status", "healthy"))
    availability = reliability * (0.92 if provider_health == "degraded" else 0.4 if provider_health in {"unavailable", "misconfigured"} else 1.0)
    return {
        "resource_id": f"{_get(provider, 'provider_key')}:{_get(model, 'model_key')}",
        "provider_key": str(_get(provider, "provider_key")),
        "model_key": str(_get(model, "model_key")),
        "environment": _environment(provider, model),
        "capabilities": list(_get(model, "capabilities", []) or []),
        "modalities": list(_get(model, "supported_modalities", []) or []),
        "latency_ms": latency_ms,
        "throughput_score": round(1.0 if latency_ms <= 1000 else 0.7 if latency_ms <= 3000 else 0.42, 3),
        "context_limit": int(_get(model, "context_window_tokens", 0) or 0),
        "estimated_cost_per_1k_tokens": per_1k,
        "availability": round(max(0.0, min(1.0, availability)), 3),
        "privacy_tier": _privacy_tier(model, provider),
        "status": str(_get(model, "status", "available")),
    }


def build_compute_resources(models: list[Any], providers: list[Any]) -> list[dict[str, Any]]:
    provider_map = {str(_get(provider, "provider_key")): provider for provider in providers}
    rows = []
    for model in models:
        provider = provider_map.get(str(_get(model, "provider_key")))
        if provider is None:
            continue
        rows.append(compute_resource_from_model(model, provider))
    return rows


def classify_workload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    objective = str(payload.get("objective", "")).lower()
    required = set(payload.get("required_capabilities") or [])
    stages = [
        {"stage": "planning", "capabilities": sorted(required | {"planning", "structured_output"}), "token_share": 0.2},
        {"stage": "generation", "capabilities": sorted(required or {"coding"}), "token_share": 0.45},
        {"stage": "verification", "capabilities": ["verification", "structured_output"], "token_share": 0.2},
        {"stage": "summarization", "capabilities": ["summarization"], "token_share": 0.15},
    ]
    if any(word in objective for word in ["image", "screenshot", "ui", "design", "visual"]):
        stages.insert(1, {"stage": "vision_review", "capabilities": ["vision", "design_review"], "token_share": 0.15})
    if any(word in objective for word in ["search", "repository", "large", "knowledge", "retrieval"]):
        stages.insert(1, {"stage": "retrieval", "capabilities": ["embedding", "retrieval"], "token_share": 0.15})
    return stages


def _hard_exclusions(resource: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    required = set(payload.get("required_capabilities") or [])
    modalities = set(payload.get("modalities") or ["text"])
    if resource["status"] != "available":
        reasons.append(f"model_{resource['status']}")
    if required and not required.issubset(set(resource["capabilities"])):
        missing = sorted(required - set(resource["capabilities"]))
        reasons.append("missing_capabilities:" + ",".join(missing))
    if modalities and not modalities.issubset(set(resource["modalities"]) | {"text"}):
        reasons.append("missing_modalities")
    required_region = payload.get("required_region")
    if required_region and resource["environment"] == "cloud" and required_region not in {"global", "cloud"}:
        reasons.append("region_unavailable")
    sensitivity = payload.get("sensitivity", "internal")
    if sensitivity in {"restricted", "secret"} and resource["privacy_tier"] not in {"high", "enterprise"}:
        reasons.append("privacy_tier_incompatible")
    max_context = payload.get("maximum_context_tokens")
    if max_context and resource["context_limit"] < int(max_context):
        reasons.append("context_window_too_small")
    max_latency = payload.get("maximum_latency_ms")
    if max_latency and resource["latency_ms"] > int(max_latency) * 1.8:
        reasons.append("latency_out_of_bounds")
    if resource["availability"] < 0.5:
        reasons.append("resource_unavailable")
    return reasons


def _score_resource(resource: dict[str, Any], payload: dict[str, Any]) -> float:
    mode = payload.get("routing_mode", "balanced")
    quality = _quality_score(resource, payload)
    latency = 1.0 / max(1.0, resource["latency_ms"] / 1000.0)
    latency = min(1.0, latency)
    cost_limit = _decimal(payload.get("maximum_cost_usd") or "1")
    estimated = estimate_plan_cost(resource, payload)
    cost = float(max(Decimal("0"), min(Decimal("1"), Decimal("1") - (estimated / max(cost_limit, Decimal("0.00000001"))))))
    privacy = {"high": 1.0, "enterprise": 0.86, "standard": 0.55}.get(resource["privacy_tier"], 0.5)
    reliability = resource["availability"]
    weights = {
        "quality_first": (0.42, 0.08, 0.12, 0.1, 0.14),
        "latency_first": (0.2, 0.3, 0.12, 0.08, 0.16),
        "cost_first": (0.2, 0.1, 0.34, 0.08, 0.14),
        "privacy_first": (0.24, 0.08, 0.1, 0.3, 0.14),
        "balanced": (0.28, 0.16, 0.18, 0.14, 0.18),
    }.get(mode, (0.28, 0.16, 0.18, 0.14, 0.18))
    return round(weights[0] * quality + weights[1] * latency + weights[2] * cost + weights[3] * privacy + weights[4] * reliability, 4)


def _quality_score(resource: dict[str, Any], payload: dict[str, Any]) -> float:
    required = set(payload.get("required_capabilities") or [])
    available = set(resource["capabilities"])
    if not required:
        if "reasoning" in available or "coding" in available:
            return 0.82
        return 0.68
    return max(0.35, len(required & available) / len(required))


def estimate_plan_cost(resource: dict[str, Any], payload: dict[str, Any]) -> Decimal:
    context_tokens = Decimal(payload.get("maximum_context_tokens") or 4096)
    output_tokens = Decimal(1024)
    total_1k = (context_tokens + output_tokens) / Decimal("1000")
    return (resource["estimated_cost_per_1k_tokens"] * total_1k).quantize(Decimal("0.00000001"))


def context_distribution(payload: dict[str, Any]) -> list[dict[str, Any]]:
    budget = int(payload.get("maximum_context_tokens") or 8192)
    sensitivity = payload.get("sensitivity", "internal")
    slices = [
        ("mission", 0.18, "mission_objective_and_acceptance"),
        ("repository", 0.32, "selected_symbols_and_changed_files"),
        ("knowledge", 0.18, "verified_project_memory"),
        ("policies", 0.12, "applicable_governance_rules"),
        ("artifacts", 0.12, "current_plans_and_evidence"),
        ("history", 0.08, "recent_relevant_events"),
    ]
    return [
        {
            "context_type": key,
            "token_budget": max(128, int(budget * share)),
            "selection_policy": policy,
            "privacy_filter": "strict" if sensitivity in {"restricted", "secret"} else "standard",
        }
        for key, share, policy in slices
    ]


def cache_policy(payload: dict[str, Any]) -> dict[str, Any]:
    policy = payload.get("cache_policy", "prefer_cache")
    cacheable = ["embeddings", "retrieval_results", "structured_outputs", "verified_plans"]
    if payload.get("sensitivity") in {"restricted", "secret"}:
        cacheable = ["local_embeddings", "non_sensitive_retrieval_keys"]
    return {
        "policy": policy,
        "lookup_ms": 5,
        "read_allowed": policy != "bypass_cache",
        "write_allowed": policy in {"prefer_cache", "write_through"},
        "cache_key": stable_hash({"objective": payload.get("objective"), "capabilities": payload.get("required_capabilities"), "context": payload.get("maximum_context_tokens")}),
        "cacheable_items": cacheable,
        "invalidation": ["mission_version_change", "repository_hash_change", "policy_version_change", "knowledge_superseded"],
    }


def build_compute_plan(payload: dict[str, Any], resources: list[dict[str, Any]]) -> dict[str, Any]:
    exclusions = {resource["resource_id"]: _hard_exclusions(resource, payload) for resource in resources}
    exclusions = {key: value for key, value in exclusions.items() if value}
    candidates = [resource for resource in resources if resource["resource_id"] not in exclusions]
    scores = {resource["resource_id"]: _score_resource(resource, payload) for resource in candidates}
    ranked = sorted(candidates, key=lambda item: scores[item["resource_id"]], reverse=True)
    selected = ranked[0] if ranked else None
    fallback = ranked[1:4]
    stages = classify_workload(payload)
    estimated_cost = estimate_plan_cost(selected, payload) if selected else Decimal("0")
    estimated_latency = selected["latency_ms"] if selected else 0
    speculation = {
        "enabled": bool(payload.get("allow_speculation") and len(ranked) >= 2 and payload.get("routing_mode") in {"latency_first", "balanced"}),
        "bounded_by": {"max_extra_cost_multiplier": 1.35, "cancel_on_primary_success": True},
        "secondary_resource": fallback[0]["resource_id"] if fallback else None,
    }
    ensemble = {
        "enabled": bool(payload.get("allow_ensemble") and len(ranked) >= 3 and payload.get("routing_mode") == "quality_first"),
        "consensus_policy": "independent_majority_with_verification",
        "resources": [item["resource_id"] for item in ranked[:3]] if len(ranked) >= 3 else [],
    }
    events = ["COMPUTE_PLAN_CREATED"]
    if selected:
        events.append("MODEL_SELECTED")
    cache = cache_policy(payload)
    events.append("CACHE_HIT" if cache["read_allowed"] else "CACHE_MISS")
    reasoning = (
        f"Selected {selected['resource_id']} for {payload.get('workload_type')} using {payload.get('routing_mode')} routing; "
        f"estimated latency {estimated_latency} ms and cost ${estimated_cost}."
        if selected
        else "No policy-compatible compute resource is available."
    )
    return {
        "plan_id": stable_hash({"payload": payload, "selected": selected["resource_id"] if selected else None})[:24],
        "workload_type": payload.get("workload_type", "software_engineering"),
        "selected_resource": selected,
        "fallback_resources": fallback,
        "stages": stages,
        "context_distribution": context_distribution(payload),
        "cache": cache,
        "speculation": speculation,
        "ensemble": ensemble,
        "estimated_cost_usd": estimated_cost,
        "estimated_latency_ms": estimated_latency,
        "candidate_scores": scores,
        "hard_exclusions": exclusions,
        "reasoning_summary": reasoning,
        "events": events,
    }


def cost_summary(resources: list[dict[str, Any]], plans_per_month: int = 1000) -> dict[str, Any]:
    provider_costs: dict[str, Decimal] = {}
    for resource in resources:
        monthly = (resource["estimated_cost_per_1k_tokens"] * Decimal("5.12") * Decimal(plans_per_month)).quantize(Decimal("0.00000001"))
        provider_costs[resource["provider_key"]] = provider_costs.get(resource["provider_key"], Decimal("0")) + monthly
    total = sum(provider_costs.values(), Decimal("0")).quantize(Decimal("0.00000001"))
    savings = (total * Decimal("0.22")).quantize(Decimal("0.00000001"))
    recommendations = ["Enable prompt/context caching for repeated repository analysis.", "Prefer local embeddings for large repositories."]
    if len(provider_costs) > 1:
        recommendations.append("Use provider failover to avoid outage-driven mission stalls.")
    return {
        "estimated_monthly_cost_usd": total,
        "estimated_cache_savings_usd": savings,
        "cost_by_provider": provider_costs,
        "optimization_recommendations": recommendations,
    }
