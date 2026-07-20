from services.agent.arceus_runtime.federation.service import (
    build_capability_index,
    build_delegation,
    create_federation,
    evaluate_join_request,
    federation_status,
    knowledge_share_decision,
    negotiate_resources,
    organization_payload,
    score_organization,
)


def org(org_id, capabilities, trust="partner", capacity=None, certs=None):
    return {
        "organization_id": org_id,
        "name": org_id.replace("_", " ").title(),
        "capabilities": capabilities,
        "specializations": capabilities[:1],
        "certifications": certs or ["soc2"],
        "supported_domains": ["software_engineering"],
        "resource_capacity": capacity or {"ai_specialists": 4, "compute": 60},
        "trust_level": trust,
        "federation_status": "active",
    }


def test_federation_creation_indexes_member_capabilities():
    result = create_federation(
        {
            "name": "Enterprise AI Platform Federation",
            "objectives": ["Build enterprise AI platform"],
            "members": [
                org("core_runtime", ["backend_engineering", "ai_development"]),
                org("security_compliance", ["security", "compliance"]),
            ],
            "governance": {"voting_model": "majority"},
            "policies": ["soc2"],
        }
    )

    assert result["status"] == "active"
    assert "FEDERATION_CREATED" in result["events"]
    assert result["capability_index"]["backend_engineering"] == ["core_runtime"]
    assert result["governance"]["audit_required"] is True


def test_join_request_blocks_sensitive_scope_and_low_trust_members():
    result = evaluate_join_request(
        {
            "organization": org("external_lab", ["research"], trust="public"),
            "requested_scopes": ["capability_catalog", "customer_pii"],
        }
    )

    assert result["status"] == "needs_approval"
    assert "capability_catalog" not in result["authorized_scopes"]
    assert "customer_pii" in result["denied_scopes"]
    assert "trust_review" in result["required_approvals"]


def test_organization_scoring_prefers_capability_coverage_trust_and_capacity():
    strong = organization_payload(org("security_compliance", ["security", "compliance"], trust="enterprise", capacity={"ai_specialists": 8, "compute": 100}))
    weak = organization_payload(org("frontend_only", ["frontend_engineering"], trust="verified", capacity={"ai_specialists": 2}))

    strong_score = score_organization(strong, ["security", "compliance"])
    weak_score = score_organization(weak, ["security", "compliance"])

    assert strong_score["score"] > weak_score["score"]
    assert strong_score["missing_capabilities"] == []


def test_delegation_contract_selects_best_organization_and_records_sync_points():
    result = build_delegation(
        {
            "global_mission": "Build an enterprise AI platform",
            "required_capabilities": ["security", "compliance"],
            "candidate_organizations": [
                org("core_runtime", ["backend_engineering"]),
                org("security_compliance", ["security", "compliance"], trust="enterprise"),
            ],
            "deliverables": ["Threat model", "Compliance review"],
            "evidence_requirements": ["review_report", "audit_event"],
        }
    )

    assert result["status"] == "contract_ready"
    assert result["selected_organization"]["organization_id"] == "security_compliance"
    assert result["contract"]["immutable_after_approval"] is True
    assert "MISSION_DELEGATED" in result["events"]
    assert any(point["name"] == "cross_review" for point in result["synchronization_points"])


def test_knowledge_share_filters_by_trust_and_sensitivity():
    members = [
        organization_payload(org("partner_org", ["research"], trust="partner")),
        organization_payload(org("public_org", ["research"], trust="public")),
    ]
    result = knowledge_share_decision(
        {
            "source_organization_id": "core_runtime",
            "target_organization_ids": ["partner_org", "public_org"],
            "knowledge_type": "verified_workflow",
            "title": "Migration rollback pattern",
            "trust_level_required": "verified",
            "sensitivity": "organization",
        },
        members,
    )

    assert result["status"] == "partially_shared"
    assert result["authorized_targets"] == ["partner_org"]
    assert result["denied_targets"] == ["public_org"]
    assert "preserve_provenance" in result["policy_filters"]


def test_resource_negotiation_allocates_resources_and_flags_budget_approval():
    result = negotiate_resources(
        {
            "requesting_organization_id": "core_runtime",
            "required_resources": {"ai_specialists": 4, "compute": 50},
            "candidate_organizations": [
                org("resource_pool", ["operations"], trust="enterprise", capacity={"ai_specialists": 5, "compute": 70}, certs=["soc2", "iso27001"]),
            ],
            "max_cost": 1,
            "regulatory_constraints": ["iso27001"],
        }
    )

    assert result["selected_provider"]["organization_id"] == "resource_pool"
    assert result["allocation"]["ai_specialists"] == 4
    assert result["status"] == "needs_approval"
    assert "budget_owner" in result["required_approvals"]


def test_federation_status_counts_members_delegations_and_disputes():
    federation = create_federation({"name": "Fed", "objectives": ["Build"], "members": [org("a", ["backend"]), org("b", ["frontend"])]})
    status = federation_status(
        [
            {"content_type": "federation", "content": federation},
            {"content_type": "federation_delegation", "content": {"events": ["MISSION_DELEGATED"]}},
            {"content_type": "federation_knowledge_share", "content": {"events": ["KNOWLEDGE_SHARED"]}},
            {"content_type": "federation_resource_agreement", "content": {"events": ["DISPUTE_OPENED"]}},
        ]
    )

    assert status["federation_count"] == 1
    assert status["member_count"] == 2
    assert status["open_disputes"] == 1
    assert status["status"] == "needs_attention"


def test_capability_index_deduplicates_member_advertisements():
    members = [organization_payload(org("a", ["backend", "backend"])), organization_payload(org("b", ["backend"]))]
    index = build_capability_index(members)

    assert index["backend"] == ["a", "b"]
