import pytest

from services.agent.os_kernel.generation2 import (
    DynamicOrganizationBuilder,
    OrganizationChange,
    PerformanceLedger,
    PerformanceRecord,
    ProjectKnowledge,
    ProjectMemoryStore,
    Lesson,
    generation2_manifest,
    initial_generation2_capability_catalog,
    initial_generation2_profile_library,
)


def make_builder() -> DynamicOrganizationBuilder:
    return DynamicOrganizationBuilder(initial_generation2_capability_catalog(), initial_generation2_profile_library())


def test_initial_capability_catalog_contains_curated_generation2_taxonomy():
    catalog = initial_generation2_capability_catalog()
    required_keys = {
        "requirement_analysis",
        "user_story_design",
        "acceptance_criteria_definition",
        "product_risk_analysis",
        "roadmap_planning",
        "system_architecture",
        "api_architecture",
        "data_architecture",
        "integration_architecture",
        "architecture_tradeoff_analysis",
        "react_development",
        "nextjs_development",
        "responsive_ui",
        "accessibility_review",
        "frontend_testing",
        "frontend_performance",
        "python_backend_development",
        "fastapi_development",
        "api_design",
        "background_job_design",
        "caching_strategy",
        "websocket_architecture",
        "relational_modeling",
        "postgresql_design",
        "database_migration",
        "query_optimization",
        "tenant_isolation",
        "backup_and_recovery",
        "threat_modeling",
        "authentication_review",
        "authorization_review",
        "secrets_review",
        "dependency_security",
        "input_validation_review",
        "secure_code_review",
        "model_integration",
        "model_routing",
        "structured_output_design",
        "retrieval_architecture",
        "agent_orchestration",
        "evaluation_pipeline",
        "prompt_injection_defense",
        "unit_test_design",
        "integration_testing",
        "end_to_end_testing",
        "regression_testing",
        "build_verification",
        "evidence_validation",
        "docker_configuration",
        "ci_cd_design",
        "cloud_deployment",
        "observability",
        "incident_response",
        "release_management",
        "rollback_design",
        "payment_gateway_integration",
        "subscription_billing",
        "webhook_reliability",
        "payment_security",
        "reconciliation",
        "refund_workflows",
    }

    catalog_keys = {capability.key for capability in catalog.capabilities.values()}

    assert required_keys.issubset(catalog_keys)
    assert all(catalog.by_key(key).verification_methods for key in required_keys)


def profile_keys(plan):
    selected = plan.selected_structure
    return {item["profile_key"] for item in selected.to_dict()["specialists"]}


def test_billing_mission_generates_dynamic_capability_driven_team():
    builder = make_builder()

    plan = builder.build_plan("mission-billing", "Add secure subscription billing with Stripe webhooks and deployment observability")
    profiles = profile_keys(plan)

    assert len(plan.candidate_structures) >= 2
    assert "payments_engineer" in profiles
    assert "backend_engineer" in profiles
    assert "database_engineer" in profiles
    assert "security_reviewer" in profiles
    assert "qa_engineer" in profiles
    assert "devops_engineer" in profiles
    assert "subscription_billing" in plan.required_capabilities
    assert "payment_gateway_integration" in plan.required_capabilities
    assert plan.requires_human_approval is True
    assert plan.coverage_score == 1.0


def test_small_frontend_change_creates_frontend_accessibility_qa_team():
    builder = make_builder()

    plan = builder.build_plan("mission-frontend", "Update a React button component to be responsive and accessible")
    profiles = profile_keys(plan)

    assert "frontend_engineer" in profiles
    assert "accessibility_reviewer" in profiles
    assert "qa_engineer" in profiles
    assert "payments_engineer" not in profiles
    assert "database_engineer" not in profiles
    assert {"react_development", "responsive_ui", "accessibility_review", "frontend_testing"}.issubset(set(plan.required_capabilities))


def test_authentication_redesign_creates_architecture_security_database_team():
    builder = make_builder()

    plan = builder.build_plan("mission-auth", "Redesign authentication, authorization, OAuth sessions, database tenant isolation, and FastAPI login APIs")
    profiles = profile_keys(plan)

    assert "product_analyst" in profiles
    assert "solution_architect" in profiles
    assert "authentication_engineer" in profiles
    assert "backend_engineer" in profiles
    assert "database_engineer" in profiles
    assert "security_reviewer" in profiles
    assert "qa_engineer" in profiles
    assert "authentication_review" in plan.required_capabilities
    assert "tenant_isolation" in plan.required_capabilities


def test_ai_retrieval_feature_creates_ai_data_security_evaluation_team():
    builder = make_builder()

    plan = builder.build_plan("mission-rag", "Build an AI retrieval feature with model routing, embeddings, prompt injection defense, and evaluation pipeline")
    profiles = profile_keys(plan)

    assert "product_analyst" in profiles
    assert "ai_architect" in profiles
    assert "backend_engineer" in profiles
    assert "data_engineer" in profiles
    assert "security_reviewer" in profiles
    assert "evaluation_engineer" in profiles
    assert "qa_engineer" in profiles
    assert "retrieval_architecture" in plan.required_capabilities
    assert "prompt_injection_defense" in plan.required_capabilities


def test_created_specialists_have_rationale_and_policy_controlled_authority():
    builder = make_builder()

    plan = builder.build_plan("mission-auth", "Redesign authentication and authorization")
    assignments = [plan.selected_structure.mission_lead, *plan.selected_structure.specialists]

    assert all(assignment.rationale for assignment in assignments)
    assert any(not assignment.authority.get("can_approve", False) for assignment in assignments)
    assert not any(
        assignment.authority.get("can_execute") and assignment.authority.get("can_approve")
        for assignment in assignments
    )


def test_different_missions_create_different_teams():
    builder = make_builder()

    billing = builder.build_plan("mission-billing", "Add secure subscription billing")
    ai = builder.build_plan("mission-ai", "Improve AI model evaluation for repository analysis")

    billing_profiles = profile_keys(billing)
    ai_profiles = profile_keys(ai)

    assert billing_profiles != ai_profiles
    assert "payments_engineer" in billing_profiles
    assert "evaluation_engineer" in ai_profiles


def test_capability_definitions_do_not_grant_authority():
    catalog = initial_generation2_capability_catalog()
    payment = catalog.by_key("subscription_billing")

    assert payment is not None
    assert payment.required_permissions == []
    assert not hasattr(payment, "authority")


def test_capability_gap_remains_visible_in_plan():
    builder = make_builder()
    builder.catalog.capabilities.clear()
    builder.catalog.register(
        initial_generation2_capability_catalog().by_key("requirement_analysis")
    )

    plan = builder.build_plan("mission-gap", "Add secure subscription billing with Stripe webhooks")

    assert plan.known_gaps
    assert plan.requires_human_approval is True


def test_project_memory_promotes_only_human_approved_items_and_blocks_cross_tenant():
    store = ProjectMemoryStore()
    weak = ProjectKnowledge(
        tenant_id="tenant-a",
        project_id="project-a",
        mission_id="mission",
        knowledge_type="decision",
        title="Weak decision",
        content={"decision": "Maybe use Stripe"},
        source_type="agent",
        source_id="agent",
        created_by="agent",
        trust_level="peer_reviewed",
    )
    approved = ProjectKnowledge(
        tenant_id="tenant-a",
        project_id="project-a",
        mission_id="mission",
        knowledge_type="decision",
        title="Stripe webhook decision",
        content={"decision": "Use idempotency keys for Stripe webhook processing", "components": ["billing"]},
        source_type="human",
        source_id="founder",
        created_by="founder",
        trust_level="human_approved",
        applicability={"components": ["billing", "webhook"]},
        confidence=0.95,
    )

    with pytest.raises(ValueError):
        store.promote(weak)

    store.promote(approved)

    same_project = store.retrieve(tenant_id="tenant-a", project_id="project-a", objective="billing webhook")
    other_tenant = store.retrieve(tenant_id="tenant-b", project_id="project-a", objective="billing webhook")

    assert same_project == [approved]
    assert other_tenant == []


def test_project_memory_supersedes_old_decision_without_overwriting():
    store = ProjectMemoryStore()
    original = store.promote(
        ProjectKnowledge(
            tenant_id="tenant",
            project_id="project",
            knowledge_type="decision",
            title="Billing provider",
            content={"provider": "Stripe"},
            source_type="human",
            source_id="founder",
            created_by="founder",
            trust_level="human_approved",
        )
    )
    replacement = ProjectKnowledge(
        tenant_id="tenant",
        project_id="project",
        knowledge_type="decision",
        title="Billing provider v2",
        content={"provider": "Stripe Billing with Customer Portal"},
        source_type="human",
        source_id="founder",
        created_by="founder",
        trust_level="human_approved",
    )

    store.supersede(original.knowledge_id, replacement)
    current = store.retrieve(tenant_id="tenant", project_id="project", objective="Billing provider")

    assert original.status == "superseded"
    assert replacement.supersedes_id == original.knowledge_id
    assert original not in current


def test_lesson_applicability_is_not_universal():
    lesson = Lesson(
        project_id="project",
        mission_id="mission",
        title="Stripe webhook retry lesson",
        situation={"component": "billing"},
        action_taken={"action": "use idempotency"},
        result={"status": "worked"},
        what_worked=["idempotency keys"],
        what_failed=[],
        root_causes=["duplicate callbacks"],
        applicability_conditions=["stripe", "webhook"],
        anti_applicability_conditions=["offline-only"],
        supporting_evidence=["integration test"],
        confidence=0.9,
        review_status="approved",
        status="active",
    )

    assert lesson.applies_to("Fix stripe webhook retry") is True
    assert lesson.applies_to("Build offline-only local notes") is False


def test_performance_ledger_uses_evidence_not_self_reported_confidence():
    ledger = PerformanceLedger()
    ledger.record(
        PerformanceRecord(
            "specialist_profile",
            "payments_engineer",
            "implementation",
            success=True,
            evidence_quality=0.9,
            cost=0.1,
            latency_ms=1200,
            rework_required=False,
            validation_passed=True,
        )
    )
    ledger.record(
        PerformanceRecord(
            "specialist_profile",
            "payments_engineer",
            "implementation",
            success=False,
            evidence_quality=0.2,
            cost=0.2,
            latency_ms=2000,
            rework_required=True,
            validation_passed=False,
        )
    )

    summary = ledger.aggregate("specialist_profile", "payments_engineer")

    assert summary["count"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["score"] < 1.0


def test_high_impact_organization_change_requires_approval_and_rollback():
    change = OrganizationChange(
        organization_id="org",
        change_type="CHANGE_TOOL_PERMISSION",
        reason="Payments engineer requests broader terminal access",
        evidence=["blocked task"],
        expected_effect="May unblock webhook testing",
        cost_impact=0.1,
        risk_impact="high",
        affected_tasks=["task-1"],
        rollback_plan=["Remove tool permission", "Reassign task"],
    )

    assert change.approval_required is True
    assert change.approved is False
    assert change.rollback_plan


def test_generation2_manifest_exposes_dynamic_org_scope():
    manifest = generation2_manifest()

    assert manifest["preferred_organization_type"] == "HYBRID"
    assert "dynamic_organization_builder" in manifest["core_modules"]
    assert "Add secure subscription billing" in manifest["vertical_slice"]
