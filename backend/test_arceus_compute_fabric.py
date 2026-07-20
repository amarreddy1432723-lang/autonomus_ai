from decimal import Decimal
from types import SimpleNamespace

from services.agent.arceus_runtime.compute.service import (
    build_compute_plan,
    build_compute_resources,
    cache_policy,
    classify_workload,
    cost_summary,
)


def _provider(key: str, *, adapter_type: str = "cloud", health_status: str = "healthy", zero_retention: bool = False):
    return SimpleNamespace(
        provider_key=key,
        adapter_type=adapter_type,
        health_status=health_status,
        supports_zero_retention=zero_retention,
    )


def _model(
    key: str,
    provider: str,
    *,
    capabilities: list[str],
    latency: str = "medium",
    cost: str = "2.0",
    retention: str = "standard",
    reliability: float = 0.9,
    status: str = "available",
):
    return SimpleNamespace(
        model_key=key,
        provider_key=provider,
        capabilities=capabilities,
        supported_modalities=["text"],
        context_window_tokens=128000,
        input_cost_per_million_tokens=Decimal(cost),
        output_cost_per_million_tokens=Decimal(cost),
        expected_latency_class=latency,
        reliability_score=reliability,
        data_retention_policy=retention,
        status=status,
    )


def test_compute_resources_abstract_models_as_schedulable_resources():
    resources = build_compute_resources(
        [_model("local-code", "ollama", capabilities=["coding", "local_execution"], retention="local")],
        [_provider("ollama", adapter_type="ollama")],
    )

    assert resources[0]["environment"] == "local"
    assert resources[0]["privacy_tier"] == "high"
    assert resources[0]["resource_id"] == "ollama:local-code"


def test_scheduler_selects_by_capability_policy_cost_and_latency():
    resources = build_compute_resources(
        [
            _model("cheap-fast", "groq", capabilities=["coding"], latency="low", cost="0.2", reliability=0.88),
            _model("reasoning", "openai", capabilities=["coding", "reasoning", "planning"], latency="medium", cost="4.0", reliability=0.96),
        ],
        [_provider("groq"), _provider("openai")],
    )
    plan = build_compute_plan(
        {
            "objective": "Implement a complex architecture refactor",
            "workload_type": "software_engineering",
            "required_capabilities": ["coding", "reasoning"],
            "routing_mode": "quality_first",
            "maximum_context_tokens": 8192,
            "maximum_cost_usd": Decimal("1.00"),
        },
        resources,
    )

    assert plan["selected_resource"]["model_key"] == "reasoning"
    assert "groq:cheap-fast" in plan["hard_exclusions"]
    assert plan["events"][0] == "COMPUTE_PLAN_CREATED"


def test_restricted_workload_excludes_standard_cloud_retention():
    resources = build_compute_resources(
        [
            _model("cloud-code", "openai", capabilities=["coding"], retention="standard"),
            _model("private-code", "enterprise", capabilities=["coding"], retention="zero_retention"),
        ],
        [_provider("openai"), _provider("enterprise", zero_retention=True)],
    )
    plan = build_compute_plan(
        {
            "objective": "Review secret authentication code",
            "required_capabilities": ["coding"],
            "sensitivity": "restricted",
            "routing_mode": "privacy_first",
        },
        resources,
    )

    assert plan["selected_resource"]["model_key"] == "private-code"
    assert "privacy_tier_incompatible" in plan["hard_exclusions"]["openai:cloud-code"]


def test_workload_classification_adds_retrieval_and_vision_stages():
    stages = classify_workload({"objective": "Review large repository screenshots and architecture", "required_capabilities": ["reasoning"]})
    names = [stage["stage"] for stage in stages]

    assert "retrieval" in names
    assert "vision_review" in names
    assert "verification" in names


def test_speculation_and_ensemble_are_policy_bounded():
    resources = build_compute_resources(
        [
            _model("a", "p1", capabilities=["reasoning"], latency="low"),
            _model("b", "p2", capabilities=["reasoning"], latency="medium"),
            _model("c", "p3", capabilities=["reasoning"], latency="high"),
        ],
        [_provider("p1"), _provider("p2"), _provider("p3")],
    )

    speculative = build_compute_plan({"objective": "Plan quickly", "required_capabilities": ["reasoning"], "allow_speculation": True, "routing_mode": "latency_first"}, resources)
    ensemble = build_compute_plan({"objective": "Critical decision", "required_capabilities": ["reasoning"], "allow_ensemble": True, "routing_mode": "quality_first"}, resources)

    assert speculative["speculation"]["enabled"] is True
    assert speculative["speculation"]["bounded_by"]["cancel_on_primary_success"] is True
    assert ensemble["ensemble"]["enabled"] is True
    assert len(ensemble["ensemble"]["resources"]) == 3


def test_cache_and_cost_policies_are_explainable():
    policy = cache_policy({"objective": "Analyze repo", "required_capabilities": ["coding"], "cache_policy": "prefer_cache", "maximum_context_tokens": 4096})
    costs = cost_summary(
        build_compute_resources([_model("a", "openai", capabilities=["coding"], cost="1.0")], [_provider("openai")]),
        plans_per_month=10,
    )

    assert policy["lookup_ms"] <= 5
    assert "repository_hash_change" in policy["invalidation"]
    assert costs["estimated_cache_savings_usd"] > 0
    assert costs["cost_by_provider"]["openai"] > 0
