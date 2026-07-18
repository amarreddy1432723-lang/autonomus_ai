from services.agent.model_registry import choose_model, model_key_for_task, registry_snapshot


def test_code_tasks_route_to_arceus_codex():
    assert model_key_for_task("code_generation") == "arceus-codex"
    choice = choose_model(task_type="code_generation")
    assert choice.model_key == "arceus-codex"
    assert choice.provider == "openai"
    assert choice.model == "gpt-5.6-sol"


def test_fast_and_reasoning_routes_are_distinct():
    fast = choose_model(task_type="chat")
    reasoning = choose_model(task_type="planning")
    assert fast.model_key == "arceus-fast"
    assert reasoning.model_key == "arceus-reasoning"
    assert fast.model != reasoning.model


def test_legacy_aliases_resolve_to_current_roles():
    code = choose_model(model_key="nexus-code")
    reasoning = choose_model(model_key="nexus-reasoning")
    assert code.model_key == "arceus-codex"
    assert reasoning.model_key == "arceus-reasoning"


def test_registry_snapshot_exposes_tiers_for_admin_ui():
    snapshot = registry_snapshot()
    model = snapshot["models"]["arceus-codex"]
    assert model["quality_tier"] == "frontier"
    assert model["cost_tier"] == "premium"
    assert model["privacy_tier"] == "provider_cloud"
