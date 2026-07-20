from services.agent.arceus_runtime.extensions.service import (
    OFFICIAL_MARKETPLACE,
    evaluate_permission_grants,
    sdk_manifest,
    validate_plugin_manifest,
)


def test_extension_manifest_accepts_signed_official_provider():
    response = validate_plugin_manifest(
        {
            "id": "arceus.ollama",
            "name": "Ollama Provider",
            "version": "1.0.0",
            "publisher": "Arceus",
            "extensionTypes": ["model_provider"],
            "runtime": {"type": "remote_http", "minCoreVersion": "2.0.0"},
            "permissions": ["model.invoke"],
            "integrity": {
                "signature": "sha256:abc123",
                "packageDigest": "sha256:" + "a" * 64,
            },
        }
    )

    assert response.valid is True
    assert response.plugin_key == "arceus.ollama"
    assert response.verified is True
    assert response.review_required is False
    assert response.security_score >= 80


def test_extension_manifest_blocks_unknown_permission_and_future_core():
    response = validate_plugin_manifest(
        {
            "id": "bad.future",
            "name": "Future Plugin",
            "version": "1.0.0",
            "publisher": "Unknown",
            "extensionTypes": ["tool"],
            "runtime": {"type": "container", "minCoreVersion": "99.0.0"},
            "permissions": ["root.everything"],
        }
    )

    assert response.valid is False
    assert any("Unsupported permission" in error for error in response.errors)
    assert any("requires Arceus Core" in error for error in response.errors)


def test_high_risk_permission_requires_review_even_when_signed():
    response = validate_plugin_manifest(
        {
            "id": "railway.deploy",
            "name": "Railway Deploy",
            "version": "1.0.0",
            "publisher": "Railway",
            "extensionTypes": ["deployment_provider"],
            "runtime": {"type": "remote_http", "minCoreVersion": "2.0.0"},
            "permissions": ["deployment.execute", "secrets.use"],
            "signature": "sha256:signed",
        }
    )

    assert response.valid is True
    assert response.review_required is True
    assert any("High-risk permission review required" in warning for warning in response.warnings)


def test_permission_evaluation_is_default_deny_and_allows_low_risk_grant():
    denied = evaluate_permission_grants(
        installation_status="enabled",
        granted_permissions=[],
        requested_permission="repository.read",
        risk_level="low",
    )
    assert denied.allowed is False
    assert denied.decision == "deny"

    allowed = evaluate_permission_grants(
        installation_status="enabled",
        granted_permissions=[{"permission": "repository.read", "scope": {"repository": "demo"}, "risk_level": "low"}],
        requested_permission="repository.read",
        risk_level="low",
        scope={"repository": "demo"},
    )
    assert allowed.allowed is True
    assert allowed.decision == "allow"


def test_high_risk_invocation_requires_review_after_grant():
    decision = evaluate_permission_grants(
        installation_status="enabled",
        granted_permissions=[{"permission": "deployment.execute", "scope": {}, "risk_level": "high"}],
        requested_permission="deployment.execute",
        risk_level="high",
    )

    assert decision.allowed is False
    assert decision.decision == "needs_review"
    assert "request_human_approval" in decision.obligations


def test_marketplace_and_sdk_expose_initial_official_extensions():
    keys = {item["plugin_key"] for item in OFFICIAL_MARKETPLACE}
    assert "github.connector" in keys
    assert "jira.connector" in keys
    assert "slack.notifications" in keys
    assert "openai.model_provider" in keys
    assert "gemini.model_provider" in keys
    assert "groq.model_provider" in keys
    assert "railway.deployment" in keys
    assert "sentry.observability" in keys

    sdk = sdk_manifest()
    assert "model_provider" in sdk["supported_extension_types"]
    assert "workflow_template" in sdk["supported_extension_types"]
    assert "telemetry_exporter" in sdk["supported_extension_types"]
    assert "repository.read" in sdk["supported_permissions"]
    assert sdk["security"]["default_deny"] is True


def test_part46_extension_type_aliases_normalize_to_public_contract():
    response = validate_plugin_manifest(
        {
            "id": "legacy.workflow",
            "name": "Legacy Workflow",
            "version": "1.0.0",
            "publisher": "Arceus",
            "type": "workflow_pack",
            "permissions": ["mission.read"],
            "signature": "sha256:signed",
        }
    )

    assert response.valid is True
    assert response.extension_types == ["workflow_template"]
