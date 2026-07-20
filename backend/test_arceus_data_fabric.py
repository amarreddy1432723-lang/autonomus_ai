from services.agent.arceus_runtime.graph.service import (
    build_digital_twin_sync,
    graph_query,
    graph_search,
    history_from_snapshots,
    normalize_attributes,
    resolve_entities,
    validate_graph_consistency,
)


def test_entity_resolution_merges_aliases_with_provenance_and_confidence():
    resolved = resolve_entities(
        [
            {
                "entity_type": "service",
                "canonical_name": "Authentication Service",
                "aliases": ["Auth"],
                "attributes": {"Owner Team": "Platform"},
                "provenance": [{"source": "repo", "connector": "github", "confidence": 0.9}],
            },
            {
                "entity_type": "service",
                "canonical_name": "Auth",
                "aliases": ["Authentication Service"],
                "attributes": {"Runtime": "production"},
                "provenance": [{"source": "monitor", "connector": "monitoring", "confidence": 0.8}],
            },
        ],
        source_system="test",
        connector="manual",
    )

    assert len(resolved) == 1
    assert "Authentication Service" in resolved[0]["aliases"]
    assert resolved[0]["attributes"]["owner_team"] == "Platform"
    assert resolved[0]["attributes"]["runtime"] == "production"
    assert resolved[0]["confidence"] > 0.7


def test_digital_twin_sync_creates_entities_relationships_diff_and_events():
    snapshot = build_digital_twin_sync(
        {
            "connector": "github",
            "source_system": "repo",
            "entities": [
                {"entity_type": "product", "canonical_name": "Arceus Code"},
                {"entity_type": "service", "canonical_name": "Authentication Service"},
                {"entity_type": "api", "canonical_name": "POST /api/v1/auth/login"},
            ],
            "relationships": [
                {"source_key": "Arceus Code", "destination_key": "Authentication Service", "relationship_type": "uses"},
                {"source_key": "Authentication Service", "destination_key": "POST /api/v1/auth/login", "relationship_type": "implements"},
            ],
            "incremental": True,
        }
    )

    assert snapshot["entity_count"] == 3
    assert snapshot["relationship_count"] == 2
    assert snapshot["consistency"]["valid"] is True
    assert "DIGITAL_TWIN_REFRESHED" in snapshot["events"]
    assert snapshot["diff"]["provenance_updates"] >= 5


def test_graph_consistency_flags_orphan_and_noncanonical_relationships():
    consistency = validate_graph_consistency(
        [{"entity_id": "a", "provenance": [{"source": "x"}], "confidence": 0.8}],
        [{"relationship_id": "r", "source_id": "a", "destination_id": "missing", "relationship_type": "touches"}],
    )

    assert consistency["valid"] is False
    assert any(item["type"] == "orphan_relationship_destination" for item in consistency["violations"])
    assert any(item["type"] == "non_canonical_relationship" for item in consistency["violations"])


def test_graph_search_and_query_traverse_relationships():
    snapshot = build_digital_twin_sync(
        {
            "connector": "github",
            "source_system": "repo",
            "entities": [
                {"entity_type": "customer", "canonical_name": "Acme Corp"},
                {"entity_type": "product", "canonical_name": "Billing Platform"},
                {"entity_type": "service", "canonical_name": "Invoice Service"},
            ],
            "relationships": [
                {"source_key": "Acme Corp", "destination_key": "Billing Platform", "relationship_type": "uses"},
                {"source_key": "Billing Platform", "destination_key": "Invoice Service", "relationship_type": "depends_on"},
            ],
        }
    )

    search = graph_search("invoice", snapshot["resolved_entities"], snapshot["relationships"])
    query = graph_query({"start_entity": "Acme Corp", "max_depth": 2}, snapshot["resolved_entities"], snapshot["relationships"])

    assert search["results"][0]["canonical_name"] == "Invoice Service"
    assert len(query["entities"]) == 3
    assert query["reasoning"]["impact_ready"] is True


def test_history_preserves_temporal_versions_and_source_summary():
    first = build_digital_twin_sync({"connector": "github", "source_system": "repo", "entities": [{"entity_type": "service", "canonical_name": "Auth"}]})
    second = build_digital_twin_sync({"connector": "monitoring", "source_system": "telemetry", "entities": [{"entity_type": "service", "canonical_name": "Auth", "attributes": {"status": "healthy"}, "version": 2}]})
    entity_id = first["resolved_entities"][0]["entity_id"]

    history = history_from_snapshots(entity_id, [first, second])

    assert history["current_version"] == 2
    assert len(history["timeline"]) == 2
    assert history["provenance_summary"]["github"] == 1
    assert history["provenance_summary"]["monitoring"] == 1


def test_attribute_normalization_is_stable_for_connectors():
    normalized = normalize_attributes({"Owner Team": " Platform ", "Monthly Cost USD": 12.5})

    assert normalized == {"owner_team": "Platform", "monthly_cost_usd": 12.5}
