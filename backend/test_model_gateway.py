from __future__ import annotations

from decimal import Decimal

from services.shared.arceus_core_models import ArceusModelProfile, ArceusProviderProfile

from backend.services.agent.arceus_runtime.model_gateway.api_schemas import ModelGatewayRequest
from backend.services.agent.arceus_runtime.model_gateway.service import (
    estimate_gateway_cost,
    model_hard_exclusions,
    provider_health,
    route_models,
)


def _provider(key: str = "openai", *, enabled: bool = True, health: str = "healthy", circuit: str = "closed") -> ArceusProviderProfile:
    return ArceusProviderProfile(
        provider_key=key,
        display_name=key.title(),
        adapter_type="openai_compatible",
        enabled=enabled,
        supported_regions=["global"],
        authentication_reference="env",
        health_status=health,
        circuit_state=circuit,
        retention_policy="standard",
    )


def _model(
    key: str,
    provider: str = "openai",
    *,
    capabilities: list[str] | None = None,
    cost: str = "1.0",
    latency: str = "medium",
    quality: float = 0.8,
    retention: str = "standard",
) -> ArceusModelProfile:
    return ArceusModelProfile(
        model_key=key,
        provider_key=provider,
        provider_model_name=key,
        display_name=key,
        status="available",
        capabilities=capabilities or ["coding", "structured_output", "reasoning"],
        supported_modalities=["text"],
        supported_output_modes=["text", "json"],
        context_window_tokens=128000,
        maximum_output_tokens=8192,
        supports_tool_calling=True,
        supports_structured_output=True,
        supports_streaming=True,
        supports_seed=True,
        supports_prompt_caching=True,
        data_residency_regions=["global"],
        data_retention_policy=retention,
        input_cost_per_million_tokens=Decimal(cost),
        output_cost_per_million_tokens=Decimal(cost) * Decimal("4"),
        expected_latency_class=latency,
        reliability_score=0.92,
        quality_scores={"software_engineering": quality, "general": quality},
    )


def test_routes_best_quality_model_in_quality_first_mode() -> None:
    providers = [_provider("openai")]
    cheap = _model("cheap", quality=0.55, cost="0.1", latency="low")
    smart = _model("smart", quality=0.95, cost="2.0", latency="medium")
    request = ModelGatewayRequest(objective="Refactor repository code", required_capabilities=["coding"], routing_mode="quality_first")

    routing = route_models(request, [cheap, smart], providers)

    assert routing.selected_model_key == "smart"
    assert routing.fallback_model_keys == ["cheap"]


def test_privacy_mode_excludes_standard_retention_for_secret_payloads() -> None:
    provider = _provider("openai")
    standard = _model("standard", retention="standard")
    local = _model("local", provider="ollama", retention="local")
    local_provider = _provider("ollama")
    request = ModelGatewayRequest(objective="Analyze secret auth code", sensitivity="secret", routing_mode="privacy_first")

    exclusions = model_hard_exclusions(request, [standard, local], {"openai": provider, "ollama": local_provider})

    assert "standard" in exclusions
    assert "retention_policy_incompatible" in exclusions["standard"]
    assert "local" not in exclusions


def test_cost_estimate_reports_cheapest_and_fastest() -> None:
    providers = [_provider("openai")]
    cheap = _model("cheap", cost="0.05", latency="high", quality=0.6)
    fast = _model("fast", cost="1.0", latency="low", quality=0.7)
    request = ModelGatewayRequest(objective="Summarize result", routing_mode="balanced")

    estimate = estimate_gateway_cost(request, [cheap, fast], providers)

    assert estimate.cheapest_model_key == "cheap"
    assert estimate.fastest_model_key == "fast"


def test_provider_health_blocks_open_circuit() -> None:
    provider = _provider("anthropic", circuit="open")
    model = _model("claude", provider="anthropic")

    health = provider_health([provider], [model])[0]

    assert health.readiness == "blocked"
    assert "circuit_open" in health.reasons


def test_no_candidate_when_required_capability_missing() -> None:
    provider = _provider("openai")
    model = _model("text-only", capabilities=["summarization"])
    request = ModelGatewayRequest(objective="Generate code", required_capabilities=["coding"])

    routing = route_models(request, [model], [provider])

    assert routing.selected_model_key is None
    assert "text-only" in routing.hard_exclusions

