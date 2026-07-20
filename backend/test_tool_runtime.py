from __future__ import annotations

from backend.services.agent.arceus_runtime.tool_runtime.api_schemas import ToolAuthorizationRequest, ToolExecutionReceipt, ToolRuntimeProfile
from backend.services.agent.arceus_runtime.tool_runtime.service import (
    authorize_tool_request,
    classify_tool_action,
    idempotency_fingerprint,
    redact_tool_payload,
    verify_tool_receipt,
)


def test_redacts_secret_like_values_recursively() -> None:
    payload = {
        "header": "Bearer abcdefghijklmnop",
        "nested": {"api_key": "sk-testsecret123456789"},
        "url": "https://example.test?token=abc123",
    }

    redacted = redact_tool_payload(payload)

    assert redacted["header"] == "Bearer [REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert "token=[REDACTED]" in redacted["url"]


def test_read_only_dry_run_is_authorized() -> None:
    response = authorize_tool_request(
        ToolAuthorizationRequest(
            tool_key="repository.search",
            action_key="search",
            arguments={"query": "ToolRuntime"},
            requester_authorities=["repository.search"],
            dry_run=True,
        )
    )

    assert response.decision == "allow"
    assert response.side_effect_class == "READ_ONLY"


def test_destructive_action_requires_review() -> None:
    profile = ToolRuntimeProfile(
        tool_key="filesystem.write",
        display_name="Filesystem Write",
        supported_actions=["delete_file"],
        risk_level="high",
        side_effect_class="LOCAL_MUTATION",
        required_authorities=["tool.execute"],
    )

    decision, reasons, approvals = classify_tool_action(profile, "delete_file", {"path": "app.py"}, "local")

    assert decision == "require_review"
    assert approvals
    assert any("destructive" in reason.lower() for reason in reasons)


def test_unknown_tool_is_denied_even_with_dry_run_when_disabled() -> None:
    response = authorize_tool_request(ToolAuthorizationRequest(tool_key="unknown.cloud", action_key="deploy", dry_run=True))

    assert response.decision == "deny"
    assert any("disabled" in reason.lower() for reason in response.reasons)


def test_idempotency_fingerprint_is_stable_and_redacted() -> None:
    payload = ToolAuthorizationRequest(
        tool_key="echo.message",
        action_key="echo",
        arguments={"message": "hello", "token": "secret-value"},
    )

    assert idempotency_fingerprint(payload) == idempotency_fingerprint(payload)
    assert "secret-value" not in idempotency_fingerprint(payload)


def test_receipt_verification_rejects_succeeded_denied_receipt() -> None:
    receipt = ToolExecutionReceipt(
        status="succeeded",
        decision="deny",
        tool_key="echo.message",
        action_key="echo",
        dry_run=False,
        input_hash="sha256:test",
        output_hash="sha256:output",
        redacted_input={},
    )

    valid, reasons = verify_tool_receipt(receipt)

    assert valid is False
    assert any("allow decision" in reason for reason in reasons)
