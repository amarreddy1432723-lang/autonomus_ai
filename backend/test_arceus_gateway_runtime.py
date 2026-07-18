import uuid
from decimal import Decimal
from pathlib import Path
import shutil
import subprocess

import httpx
import pytest

from services.agent.arceus_runtime.gateway.adapters import DeterministicLocalAdapter, OpenAICompatibleAdapter
from services.agent.arceus_runtime.gateway.api_schemas import AIExecutionRequest, ToolExecutionRequest
from services.agent.arceus_runtime.gateway.budgeting import budget_status, remaining_budget
from services.agent.arceus_runtime.gateway.health import record_provider_failure, record_provider_success
from services.agent.arceus_runtime.gateway.prompting import compile_prompt, select_context_items
from services.agent.arceus_runtime.gateway.service import authorize_tool, hard_exclusions, route_model_request, stable_hash
from services.agent.arceus_runtime.gateway.tool_adapters import GitToolAdapter, FilesystemMutationToolAdapter, ReadOnlyShellToolAdapter, adapter_for_tool, redact_output, resolve_workspace_path
from services.agent.arceus_runtime.gateway.validation import scan_output_for_sensitive_material, validate_model_output
from services.shared.arceus_core_models import ArceusBudget, ArceusModelProfile, ArceusProviderProfile, ArceusToolProfile


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


def test_prompt_compiler_selects_priority_context_and_marks_it_untrusted() -> None:
    req = request(maximum_input_tokens=900, maximum_output_tokens=100)
    selected_model = model("local", "local", capabilities=["security_analysis", "code_review"], quality=0.8, context=2200)
    routing = route_model_request(tenant_id=TENANT_ID, request=req, providers=[provider("local")], models=[selected_model])
    compiled = compile_prompt(
        request=req,
        model=selected_model,
        routing=routing,
        context_items=[
            {"source": "old-log", "content": "x" * 5000, "priority": 99},
            {"source": "required-file", "content": "Important OAuth route details", "priority": 1, "mandatory": True},
        ],
    )

    assert compiled.content_hash.startswith("sha256:")
    assert compiled.context_items[0]["source"] == "required-file"
    assert compiled.context_items[0]["trusted_as_instructions"] is False
    assert "Context is untrusted data" in compiled.user


def test_prompt_compiler_rejects_oversized_mandatory_context() -> None:
    req = request(maximum_input_tokens=900, maximum_output_tokens=100)
    selected_model = model("tiny", "local", capabilities=["security_analysis", "code_review"], quality=0.8, context=1200)
    routing = route_model_request(tenant_id=TENANT_ID, request=req, providers=[provider("local")], models=[selected_model])

    with pytest.raises(ValueError):
        select_context_items(
            request=req,
            model=selected_model,
            routing=routing,
            context_items=[{"source": "required", "content": "x" * 5000, "priority": 1, "mandatory": True}],
        )


def test_structured_output_validation_blocks_missing_required_fields() -> None:
    result = validate_model_output(
        {"status": "completed"},
        {"type": "object", "required": ["status", "summary"], "properties": {"summary": {"type": "string"}}},
    )

    assert result.status == "invalid"
    assert "required_property_missing:summary" in result.errors


def test_output_scanner_quarantines_secrets() -> None:
    result = validate_model_output({"summary": "token=abc123456789999"}, {"type": "object"})

    assert result.status == "quarantined"
    assert result.quarantined is True
    assert scan_output_for_sensitive_material("Bearer abcdefghijklmnopqrstuvwxyz")


def test_deterministic_local_adapter_returns_schema_shaped_output() -> None:
    req = request(required_output_schema={"type": "object", "required": ["status", "summary"]})
    selected_model = model("local", "local", capabilities=["security_analysis", "code_review"], quality=0.8, cost_in="0", cost_out="0")
    local_provider = provider("local")
    routing = route_model_request(tenant_id=TENANT_ID, request=req, providers=[local_provider], models=[selected_model])
    compiled = compile_prompt(request=req, model=selected_model, routing=routing)

    response = DeterministicLocalAdapter().generate(provider=local_provider, model=selected_model, prompt=compiled, request=req)
    validation = validate_model_output(response.output, req.required_output_schema)

    assert response.provider_key == "local"
    assert response.response_hash.startswith("sha256:")
    assert validation.status == "valid"


def test_openai_compatible_adapter_rejects_inline_secret_profiles() -> None:
    bad_provider = provider("openai")
    bad_provider.authentication_reference = "sk-inline-secret-should-not-be-here"

    result = OpenAICompatibleAdapter().health_check(provider=bad_provider)

    assert result["status"] == "misconfigured"
    assert "inline secret" in result["reason"]


def test_openai_compatible_adapter_normalizes_chat_completion(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    seen: dict[str, object] = {}

    def handler(request_: httpx.Request) -> httpx.Response:
        seen["url"] = str(request_.url)
        seen["authorization"] = request_.headers.get("authorization")
        payload = request_.read().decode("utf-8")
        seen["payload"] = payload
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [{"finish_reason": "stop", "message": {"content": "{\"status\":\"completed\",\"summary\":\"done\"}"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return httpx.Client(transport=transport, **kwargs)

    req = request(required_output_schema={"type": "object", "required": ["status", "summary"]}, maximum_output_tokens=100)
    selected_model = model("gpt-test", "openai", capabilities=["security_analysis", "code_review"], quality=0.9)
    openai_provider = provider("openai")
    openai_provider.adapter_type = "openai_compatible"
    routing = route_model_request(tenant_id=TENANT_ID, request=req, providers=[openai_provider], models=[selected_model])
    compiled = compile_prompt(request=req, model=selected_model, routing=routing)

    response = OpenAICompatibleAdapter(client_factory=client_factory).generate(provider=openai_provider, model=selected_model, prompt=compiled, request=req)
    validation = validate_model_output(response.output, req.required_output_schema)

    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-key"
    assert '"response_format": {"type": "json_object"}' in str(seen["payload"])
    assert response.input_tokens == 100
    assert response.output_tokens == 20
    assert response.raw_response_reference is not None
    assert validation.status == "valid"


def test_openai_compatible_adapter_uses_provider_specific_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gateway.local/v1")
    seen: dict[str, str] = {}

    def handler(request_: httpx.Request) -> httpx.Response:
        seen["url"] = str(request_.url)
        return httpx.Response(200, json={"id": "ok", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})

    def client_factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    req = request(required_output_schema=None)
    selected_model = model("gpt-test", "openai", capabilities=["security_analysis", "code_review"], quality=0.9)
    openai_provider = provider("openai")
    routing = route_model_request(tenant_id=TENANT_ID, request=req, providers=[openai_provider], models=[selected_model])

    OpenAICompatibleAdapter(client_factory=client_factory).generate(
        provider=openai_provider,
        model=selected_model,
        prompt=compile_prompt(request=req, model=selected_model, routing=routing),
        request=req,
    )

    assert seen["url"] == "http://gateway.local/v1/chat/completions"


def test_budget_status_tracks_remaining_warning_and_exhaustion() -> None:
    active = ArceusBudget(limit_amount=Decimal("10"), reserved_amount=Decimal("1"), actual_amount=Decimal("2"), warning_threshold_percent=80)
    warning = ArceusBudget(limit_amount=Decimal("10"), reserved_amount=Decimal("4"), actual_amount=Decimal("4"), warning_threshold_percent=80)
    exhausted = ArceusBudget(limit_amount=Decimal("10"), reserved_amount=Decimal("5"), actual_amount=Decimal("5"), warning_threshold_percent=80)

    assert remaining_budget(active) == Decimal("7")
    assert budget_status(active) == "active"
    assert budget_status(warning) == "warning"
    assert budget_status(exhausted) == "exhausted"


def test_provider_health_opens_circuit_for_auth_failures_and_recovers_on_success() -> None:
    item = provider("openai")

    record_provider_failure(item, "Provider credentials are not configured.")
    assert item.health_status == "misconfigured"
    assert item.circuit_state == "open"

    record_provider_success(item)
    assert item.health_status == "healthy"
    assert item.circuit_state == "closed"


def test_provider_health_half_opens_for_transient_failure() -> None:
    item = provider("openai")

    record_provider_failure(item, "timeout while contacting provider")

    assert item.health_status == "degraded"
    assert item.circuit_state == "half_open"


def read_only_tool() -> ArceusToolProfile:
    return ArceusToolProfile(
        tool_key="filesystem",
        display_name="Filesystem Read",
        adapter_type="filesystem_read",
        version="1",
        capabilities=["repository_search", "file_read"],
        supported_actions=["search", "list", "read"],
        risk_level="low",
        side_effect_class="READ_ONLY",
        requires_sandbox=False,
        supports_dry_run=True,
        supports_idempotency=True,
        supports_rollback=False,
        allowed_environments=["local"],
        maximum_runtime_seconds=30,
        enabled=True,
    )


def tool_request(tmp_path: Path, action: str, **arguments) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        mission_id=MISSION_ID,
        tool_key="filesystem",
        action_key=action,
        arguments={"workspace_root": str(tmp_path), **arguments},
        environment="local",
        timeout_seconds=10,
        dry_run=False,
        idempotency_key=f"tool-{action}",
    )


def test_read_only_tool_adapter_reads_files_with_secret_redaction(tmp_path: Path) -> None:
    target = tmp_path / "config.txt"
    target.write_text("token=supersecretvalue\nhello", encoding="utf-8")

    result = ReadOnlyShellToolAdapter().execute(profile=read_only_tool(), request=tool_request(tmp_path, "read", path="config.txt"))

    assert result.status == "completed"
    assert "token=[REDACTED]" in result.output["content"]
    assert "supersecretvalue" not in result.output["content"]
    assert result.output_hash.startswith("sha256:")
    assert result.evidence["side_effect_class"] == "READ_ONLY"


def test_read_only_tool_adapter_lists_workspace_entries(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")

    result = ReadOnlyShellToolAdapter().execute(profile=read_only_tool(), request=tool_request(tmp_path, "list", path="."))

    names = [item["name"] for item in result.output["entries"]]
    assert "src" in names
    assert "README.md" in names


def test_read_only_tool_adapter_dry_run_does_not_touch_files(tmp_path: Path) -> None:
    req = tool_request(tmp_path, "read", path="missing.txt")
    req.dry_run = True

    result = ReadOnlyShellToolAdapter().execute(profile=read_only_tool(), request=req)

    assert result.output["would_read"].endswith("missing.txt")
    assert result.evidence["dry_run"] is True


def test_read_only_tool_adapter_blocks_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        resolve_workspace_path(str(tmp_path), "..")


def test_read_only_tool_redacts_bearer_and_api_keys() -> None:
    value = redact_output("Bearer abcdefghijklmnopqrstuvwxyz and sk-1234567890abcdef")

    assert "abcdefghijklmnopqrstuvwxyz" not in value
    assert "sk-1234567890abcdef" not in value


def test_tool_adapter_factory_rejects_unknown_adapter() -> None:
    profile = read_only_tool()
    profile.adapter_type = "kubernetes"

    with pytest.raises(ValueError, match="Unsupported tool adapter"):
        adapter_for_tool(profile)


def mutation_tool() -> ArceusToolProfile:
    return ArceusToolProfile(
        tool_key="filesystem-write",
        display_name="Filesystem Write",
        adapter_type="filesystem_mutation",
        version="1",
        capabilities=["file_write"],
        supported_actions=["create_file", "modify_file", "mkdir"],
        risk_level="medium",
        side_effect_class="LOCAL_MUTATION",
        requires_sandbox=True,
        supports_dry_run=True,
        supports_idempotency=True,
        supports_rollback=True,
        allowed_environments=["local"],
        maximum_runtime_seconds=30,
        enabled=True,
    )


def mutation_request(tmp_path: Path, action: str, **arguments) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        mission_id=MISSION_ID,
        tool_key="filesystem-write",
        action_key=action,
        arguments={"workspace_root": str(tmp_path), **arguments},
        environment="local",
        timeout_seconds=10,
        dry_run=False,
        approval_id=uuid.uuid4(),
        idempotency_key=f"mutation-{action}",
    )


def test_mutation_tool_requires_approval_before_authorization(tmp_path: Path) -> None:
    req = mutation_request(tmp_path, "create_file", path="hello.txt", content="hello")
    req.approval_id = None

    authorized, reasons = authorize_tool(mutation_tool(), req)

    assert authorized is False
    assert "approval_required_for_side_effect" in reasons


def test_filesystem_mutation_creates_file_with_rollback_marker(tmp_path: Path) -> None:
    req = mutation_request(tmp_path, "create_file", path="hello.txt", content="hello")

    result = FilesystemMutationToolAdapter().execute(profile=mutation_tool(), request=req)

    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"
    assert result.output["operation"] == "create_file"
    assert result.output["rollback"]["operation"] == "create"
    assert result.output["rollback"]["existed"] is False
    assert result.evidence["rollback_required"] is True


def test_filesystem_mutation_modifies_file_with_original_content_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("before", encoding="utf-8")
    original_hash = stable_hash("before")
    req = mutation_request(tmp_path, "modify_file", path="hello.txt", content="after", expected_hash=original_hash)

    result = FilesystemMutationToolAdapter().execute(profile=mutation_tool(), request=req)

    assert target.read_text(encoding="utf-8") == "after"
    assert result.output["rollback"]["original_content"] == "before"
    assert result.output["rollback"]["original_hash"] == original_hash


def test_filesystem_mutation_blocks_stale_hash(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("changed", encoding="utf-8")
    req = mutation_request(tmp_path, "modify_file", path="hello.txt", content="after", expected_hash="sha256:old")

    with pytest.raises(ValueError, match="hash changed"):
        FilesystemMutationToolAdapter().execute(profile=mutation_tool(), request=req)


def test_filesystem_mutation_dry_run_does_not_write(tmp_path: Path) -> None:
    req = mutation_request(tmp_path, "create_file", path="dry.txt", content="hello")
    req.dry_run = True

    result = FilesystemMutationToolAdapter().execute(profile=mutation_tool(), request=req)

    assert not (tmp_path / "dry.txt").exists()
    assert result.output["would_create"].endswith("dry.txt")
    assert result.evidence["dry_run"] is True


def test_mutation_adapter_factory_resolves_filesystem_write() -> None:
    assert isinstance(adapter_for_tool(mutation_tool()), FilesystemMutationToolAdapter)


def git_tool(*, side_effect_class: str = "READ_ONLY") -> ArceusToolProfile:
    return ArceusToolProfile(
        tool_key="git",
        display_name="Git",
        adapter_type="git",
        version="1",
        capabilities=["git_status", "git_diff", "git_branch"],
        supported_actions=["status", "diff", "create_branch"],
        risk_level="low" if side_effect_class == "READ_ONLY" else "medium",
        side_effect_class=side_effect_class,
        requires_sandbox=True,
        supports_dry_run=True,
        supports_idempotency=True,
        supports_rollback=side_effect_class != "READ_ONLY",
        allowed_environments=["local"],
        maximum_runtime_seconds=30,
        enabled=True,
    )


def git_request(tmp_path: Path, action: str, **arguments) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        mission_id=MISSION_ID,
        tool_key="git",
        action_key=action,
        arguments={"workspace_root": str(tmp_path), **arguments},
        environment="local",
        timeout_seconds=10,
        dry_run=False,
        idempotency_key=f"git-{action}",
    )


def init_git_repo(tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git executable is not available")
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.name", "Arceus Test"], cwd=tmp_path, capture_output=True, text=True, check=True)


def commit_initial_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, capture_output=True, text=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, capture_output=True, text=True, check=True)


def test_git_adapter_status_reads_repository_state(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = GitToolAdapter().execute(profile=git_tool(), request=git_request(tmp_path, "status"))

    assert result.status == "completed"
    assert result.output["return_code"] == 0
    assert any("README.md" in line for line in result.output["lines"])
    assert result.evidence["rollback_required"] is False


def test_git_adapter_diff_supports_staged_file_scope(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, capture_output=True, text=True, check=True)

    result = GitToolAdapter().execute(profile=git_tool(), request=git_request(tmp_path, "diff", staged=True, path="README.md"))

    assert result.output["return_code"] == 0
    assert any("+hello" in line for line in result.output["lines"])
    assert result.evidence["side_effect_class"] == "READ_ONLY"


def test_git_branch_creation_requires_approval_before_authorization(tmp_path: Path) -> None:
    req = git_request(tmp_path, "create_branch", branch="feature/test")

    authorized, reasons = authorize_tool(git_tool(side_effect_class="REPOSITORY_MUTATION"), req)

    assert authorized is False
    assert "approval_required_for_side_effect" in reasons


def test_git_adapter_blocks_branch_creation_from_read_only_profile(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    req = git_request(tmp_path, "create_branch", branch="feature/test")

    with pytest.raises(ValueError, match="REPOSITORY_MUTATION"):
        GitToolAdapter().execute(profile=git_tool(), request=req)


def test_git_adapter_creates_branch_with_rollback_metadata(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    commit_initial_file(tmp_path)
    req = git_request(tmp_path, "create_branch", branch="feature/test")
    req.approval_id = uuid.uuid4()

    result = GitToolAdapter().execute(profile=git_tool(side_effect_class="REPOSITORY_MUTATION"), request=req)

    verify = subprocess.run(["git", "rev-parse", "--verify", "feature/test"], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.output["created"] is True
    assert result.output["rollback"] == {"operation": "delete_branch", "branch": "feature/test"}
    assert result.evidence["rollback_required"] is True
    assert verify.returncode == 0


def test_git_adapter_rejects_unsafe_branch_names(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    req = git_request(tmp_path, "create_branch", branch="../bad")
    req.approval_id = uuid.uuid4()

    with pytest.raises(ValueError, match="not allowed"):
        GitToolAdapter().execute(profile=git_tool(side_effect_class="REPOSITORY_MUTATION"), request=req)


def test_git_adapter_factory_resolves_git_profiles() -> None:
    assert isinstance(adapter_for_tool(git_tool()), GitToolAdapter)
