import uuid
from decimal import Decimal

from services.agent.arceus_runtime.gateway.api_schemas import AIExecutionRequest, ToolExecutionRequest
from services.agent.arceus_runtime.gateway.service import authorize_tool, hard_exclusions, route_model_request
from services.shared.arceus_core_models import ArceusModelProfile, ArceusProviderProfile, ArceusToolProfile


TENANT_ID = uuid.uuid4()
MISSION_ID = uuid.uuid4()


def provider(provider_key: str = "openai", *, enabled: bool = True, circuit_state: str = "closed", health_status: str = "healthy") -> ArceusProviderProfile:
    return ArceusProviderProfile(
        provider_key=provider_key,
        display_name=provider_key.title(),
        adapter_type="openai_compatible",
        enabled=enabled,
        supported_regions=["global", "us"],
        authentication_reference=f"env:{provider_key.upper()}_API_KEY",
        health_status=health_status,
        circuit_state=circuit_state,
        retention_policy="zero_retention",
        supports_zero_retention=True,
    )


def model(
    model_key: str,
    provider_key: str,
    *,
    capabilities: list[str],
    quality: float,
    cost_in: str = "1.00",
    cost_out: str = "3.00",
    context: int = 128000,
    status: str = "available",
    structured: bool = True,
) -> ArceusModelProfile:
    return ArceusModelProfile(
        model_key=model_key,
        provider_key=provider_key,
        provider_model_name=model_key,
        display_name=model_key,
        status=status,
        capabilities=capabilities,
        supported_modalities=["text"],
        supported_output_modes=["text", "json"],
        context_window_tokens=context,
        maximum_output_tokens=8192,
        supports_structured_output=structured,
        supports_seed=True,
        data_residency_regions=["global", "us"],
        data_retention_policy="zero_retention",
        input_cost_per_million_tokens=Decimal(cost_in),
        output_cost_per_million_tokens=Decimal(cost_out),
        expected_latency_class="medium",
        reliability_score=0.95,
        quality_scores={"security_review": quality, "code_generation": quality, "general": quality},
    )


def request(**overrides) -> AIExecutionRequest:
    values = {
        "mission_id": MISSION_ID,
        "task_type": "security_review",
        "objective": "Review the OAuth flow.",
        "required_capabilities": ["security_analysis", "code_review"],
        "required_output_schema": {"type": "object"},
        "sensitivity": "internal",
        "risk_level": "high",
        "maximum_cost_usd": Decimal("0.25"),
        "idempotency_key": "route-1",
        "routing_mode": "quality_first",
    }
    values.update(overrides)
    return AIExecutionRequest(**values)


def test_routing_excludes_policy_incompatible_models_before_scoring() -> None:
    req = request(prohibited_provider_keys=["blocked"], maximum_input_tokens=6000, maximum_output_tokens=2000)
    models = [
        model("good", "openai", capabilities=["security_analysis", "code_review"], quality=0.9),
        model("disabled-model", "openai", capabilities=["security_analysis", "code_review"], quality=0.99, status="disabled"),
        model("small-context", "openai", capabilities=["security_analysis", "code_review"], quality=0.99, context=1000),
        model("no-json", "openai", capabilities=["security_analysis", "code_review"], quality=0.99, structured=False),
        model("blocked-provider", "blocked", capabilities=["security_analysis", "code_review"], quality=0.99),
        model("missing-capability", "openai", capabilities=["code_review"], quality=0.99),
    ]
    exclusions = hard_exclusions(request=req, models=models, providers={"openai": provider(), "blocked": provider("blocked")})

    assert "good" not in exclusions
    assert "model_disabled" in exclusions["disabled-model"]
    assert "context_window_too_small" in exclusions["small-context"]
    assert "structured_output_unsupported" in exclusions["no-json"]
    assert "provider_prohibited" in exclusions["blocked-provider"]
    assert "missing_capabilities:security_analysis" in exclusions["missing-capability"]


def test_quality_first_routing_selects_best_allowed_candidate_with_fallbacks() -> None:
    req = request()
    decision = route_model_request(
        tenant_id=TENANT_ID,
        request=req,
        providers=[provider("openai"), provider("anthropic"), provider("local")],
        models=[
            model("cheap-code", "openai", capabilities=["security_analysis", "code_review"], quality=0.70, cost_in="0.10", cost_out="0.20"),
            model("expert-security", "anthropic", capabilities=["security_analysis", "code_review"], quality=0.96, cost_in="2.00", cost_out="5.00"),
            model("local-review", "local", capabilities=["security_analysis", "code_review", "local_execution"], quality=0.82, cost_in="0", cost_out="0"),
        ],
    )

    assert decision.selected_model_key == "expert-security"
    assert decision.selected_provider_key == "anthropic"
    assert "cheap-code" in decision.candidate_scores
    assert decision.fallback_model_keys
    assert decision.estimated_cost_usd <= Decimal("0.25")
    assert decision.decision_hash.startswith("sha256:")


def test_restricted_sensitive_request_requires_local_or_zero_retention_policy() -> None:
    req = request(sensitivity="restricted", risk_level="critical", required_capabilities=["security_analysis", "local_execution"])
    decision = route_model_request(
        tenant_id=TENANT_ID,
        request=req,
        providers=[provider("cloud"), provider("local")],
        models=[
            model("cloud-security", "cloud", capabilities=["security_analysis", "code_review"], quality=0.99),
            model("local-security", "local", capabilities=["security_analysis", "local_execution"], quality=0.72, cost_in="0", cost_out="0"),
        ],
    )

    assert decision.selected_model_key == "local-security"
    assert "cloud-security" in decision.hard_exclusions


def test_tool_authorization_blocks_risky_side_effect_without_approval() -> None:
    profile = ArceusToolProfile(
        tool_key="git",
        display_name="Git",
        adapter_type="git",
        version="1",
        capabilities=["repository_mutation"],
        supported_actions=["commit"],
        risk_level="medium",
        side_effect_class="REPOSITORY_MUTATION",
        requires_sandbox=True,
        supports_idempotency=True,
        supports_rollback=True,
        allowed_environments=["local"],
        maximum_runtime_seconds=60,
    )
    req = ToolExecutionRequest(
        mission_id=MISSION_ID,
        tool_key="git",
        action_key="commit",
        arguments={"message": "test"},
        environment="local",
        timeout_seconds=30,
        dry_run=False,
        idempotency_key="tool-1",
    )

    authorized, reasons = authorize_tool(profile, req)

    assert authorized is False
    assert "approval_required_for_side_effect" in reasons


def test_tool_authorization_allows_read_only_dry_run() -> None:
    profile = ArceusToolProfile(
        tool_key="ripgrep",
        display_name="ripgrep",
        adapter_type="shell",
        version="1",
        capabilities=["repository_search"],
        supported_actions=["search"],
        risk_level="low",
        side_effect_class="READ_ONLY",
        requires_sandbox=False,
        supports_dry_run=True,
        supports_idempotency=True,
        supports_rollback=False,
        allowed_environments=["local"],
        maximum_runtime_seconds=30,
    )
    req = ToolExecutionRequest(
        mission_id=MISSION_ID,
        tool_key="ripgrep",
        action_key="search",
        arguments={"query": "TODO"},
        environment="local",
        timeout_seconds=10,
        dry_run=True,
        idempotency_key="tool-2",
    )

    authorized, reasons = authorize_tool(profile, req)

    assert authorized is True
    assert reasons == []
