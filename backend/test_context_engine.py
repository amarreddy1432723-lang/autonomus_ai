from __future__ import annotations

from pathlib import Path

from services.agent.arceus_runtime.context_engine.api_schemas import ContextBuildRequest, ModelContextProfile
from services.agent.arceus_runtime.context_engine.service import analyze_intent, build_context_package, clear_cache, expand_context


def test_context_engine_builds_ranked_cited_package_from_repository(tmp_path: Path):
    clear_cache()
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"16.0.0","stripe":"latest"}}', encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "billing.ts").write_text(
        "import Stripe from 'stripe';\nexport class BillingService {\n  verifyWebhook() { return true; }\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "billing.test.ts").write_text("import { BillingService } from './billing';\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Billing webhook service for Stripe payments.\n", encoding="utf-8")

    request = ContextBuildRequest(
        mission_id="mission_1",
        prompt="Refactor BillingService webhook verification in src/billing.ts and include tests.",
        root_path=str(tmp_path),
        repository_id="repo_ctx",
        model=ModelContextProfile(model_profile="gpt-large", max_context_tokens=32_000, reserve_output_tokens=4_000),
        memories=["Use strict TypeScript and preserve public APIs."],
        conversation=["The user rejected changing payment provider."],
    )

    package, intent, cache_hit = build_context_package(request)

    assert not cache_hit
    assert intent.task_type == "refactor"
    assert "src/billing.ts" in intent.requested_files
    assert package.package_id.startswith("ctx_")
    assert package.citations
    assert any(item.citation.file == "src/billing.ts" for item in package.items)
    assert any(item.source == "tests" for item in package.items)
    assert "Use only the cited context" in package.prompt

    cached, _, second_hit = build_context_package(request)
    assert second_hit
    assert cached.package_id == package.package_id

    expanded = expand_context(package.package_id, "Stripe import dependency", 2_000)
    assert expanded is not None
    assert expanded.package_id == package.package_id


def test_intent_analysis_detects_debug_and_security_risk():
    intent = analyze_intent("Fix production auth error in backend/services/agent/security.py")

    assert intent.task_type == "debug"
    assert intent.risk_level == "high"
    assert "backend/services/agent/security.py" in intent.requested_files
