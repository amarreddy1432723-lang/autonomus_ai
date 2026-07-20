from uuid import UUID

from services.agent.arceus_runtime.platform.service import (
    calculate_capacity_posture,
    evaluate_federation_request,
    region_control_plane_status,
    residency_allows_region,
    tenant_platform_profile,
)
from services.shared.arceus_core_models import ArceusProviderProfile, ArceusTenant


def _tenant(**settings):
    return ArceusTenant(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        name="Acme India",
        slug="acme-india",
        status="active",
        plan_key="enterprise",
        settings=settings,
    )


def test_tenant_profile_enforces_isolation_and_data_residency():
    profile = tenant_platform_profile(
        _tenant(
            home_region="india",
            residency_regions=["india"],
            compliance_profiles=["soc2", "iso27001"],
            failover_regions=["india"],
        )
    )

    assert profile["deployment_model"] == "multi_tenant_saas"
    assert profile["home_region"] == "india"
    assert profile["isolation"]["knowledge_graph"] is True
    assert profile["isolation"]["secrets"] is True
    assert residency_allows_region(profile, "india") is True
    assert residency_allows_region(profile, "us") is False


def test_federation_requires_explicit_policy_and_blocks_sensitive_scopes():
    disabled_profile = tenant_platform_profile(_tenant(home_region="india"))
    disabled = evaluate_federation_request(
        disabled_profile,
        {"peer_deployment_id": "partner-eu", "peer_region": "europe", "shared_scopes": ["verified_lessons"], "dry_run": True},
    )
    assert disabled["accepted"] is False
    assert disabled["status"] == "disabled"

    enabled_profile = tenant_platform_profile(
        _tenant(
            home_region="india",
            federation={"enabled": True, "allowed_scopes": ["verified_lessons", "capability_catalog"]},
        )
    )
    denied = evaluate_federation_request(
        enabled_profile,
        {"peer_deployment_id": "partner-eu", "peer_region": "europe", "shared_scopes": ["verified_lessons", "secrets"], "dry_run": True},
    )
    assert denied["accepted"] is False
    assert "secrets" in denied["denied_scopes"]

    accepted = evaluate_federation_request(
        enabled_profile,
        {"peer_deployment_id": "partner-eu", "peer_region": "europe", "shared_scopes": ["verified_lessons"], "dry_run": True},
    )
    assert accepted["accepted"] is True
    assert accepted["event_type"] == "FEDERATION_ESTABLISHED"


def test_region_profile_reports_provider_health_and_edge_controls():
    providers = [
        ArceusProviderProfile(
            provider_key="openai",
            display_name="OpenAI",
            adapter_type="llm",
            enabled=True,
            supported_regions=["india"],
            authentication_reference="env:OPENAI_API_KEY",
            health_status="healthy",
        ),
        ArceusProviderProfile(
            provider_key="anthropic",
            display_name="Anthropic",
            adapter_type="llm",
            enabled=True,
            supported_regions=["india"],
            authentication_reference="env:ANTHROPIC_API_KEY",
            health_status="unavailable",
        ),
    ]

    region = region_control_plane_status(region_key="india", providers=providers)

    assert region["status"] == "healthy"
    assert region["provider_count"] == 2
    assert region["healthy_provider_count"] == 1
    assert region["edge_runtime"]["local_policy_checks"] is True
    assert "iso27001" in region["compliance_profiles"]


def test_capacity_posture_flags_single_region_and_event_backlog():
    posture = calculate_capacity_posture(
        {
            "mission_statuses": {"running": 2},
            "task_statuses": {"ready": 125, "running": 4},
            "outbox_statuses": {"pending": 1200, "processing": 25},
            "stale_processing_outbox": 0,
        },
        region_count=1,
    )

    assert posture["status"] == "degraded"
    assert "single_region_deployment" in posture["capacity_risks"]
    assert "event_mesh_backlog" in posture["capacity_risks"]
    assert "scale_regional_worker_pool" in posture["recommendations"]
