from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from services.shared.arceus_core_models import ArceusMemoryItem

from backend.services.agent.arceus_runtime.memory_fabric.service import (
    apply_memory_feedback,
    detect_memory_conflicts,
    extract_memory_facts,
    graph_projection_for_memory,
    search_memories,
)


def _memory(title: str, content: str, *, confidence: float = 0.8, status: str = "verified") -> ArceusMemoryItem:
    return ArceusMemoryItem(
        id=uuid4(),
        tenant_id=uuid4(),
        memory_scope="project",
        title=title,
        content=content,
        content_type="semantic",
        source_type="verification",
        source_ids=[],
        evidence_ids=[],
        lifecycle_status=status,
        trust_level="governed",
        confidence=confidence,
        sensitivity="project",
        content_hash=f"hash-{uuid4()}",
        created_at=datetime.now(timezone.utc),
    )


def test_extracts_structured_facts_and_graph_edges() -> None:
    result = extract_memory_facts("StripeWebhookVerifier validates WebhookSignature. BillingService uses StripeWebhookVerifier.")

    assert any(fact["relation"] == "validates" for fact in result["facts"])
    assert any(node["label"] == "StripeWebhookVerifier" for node in result["entities"])
    assert result["relationships"]


def test_graph_projection_links_memory_to_entities() -> None:
    item = _memory("Billing fact", "BillingService uses StripeWebhookVerifier.")

    projection = graph_projection_for_memory(item)

    assert projection["memory_id"] == item.id
    assert any(node["type"] == "Memory" for node in projection["nodes"])
    assert any(edge["relation"] == "documents" for edge in projection["edges"])


def test_conflict_detection_finds_different_objects_for_same_relation() -> None:
    old = _memory("Billing v1", "BillingService uses StripeWebhookVerifier.", confidence=0.7)
    new = _memory("Billing v2", "BillingService uses PaymentWebhookVerifier.", confidence=0.9)

    conflicts = detect_memory_conflicts([old, new])

    assert len(conflicts) == 1
    assert conflicts[0]["suggested_winner_id"] == new.id


def test_feedback_updates_confidence_and_lifecycle() -> None:
    item = _memory("Proposed", "ApiGateway uses AuthService.", confidence=0.66, status="proposed")

    result = apply_memory_feedback(item, rating="correct")

    assert result["new_confidence"] > result["previous_confidence"]
    assert item.lifecycle_status == "verified"


def test_search_prefers_verified_high_confidence_memory() -> None:
    weak = _memory("Weak auth", "AuthService uses TokenStore.", confidence=0.2, status="proposed")
    strong = _memory("Strong auth", "AuthService uses ClerkSessionVerifier.", confidence=0.95, status="verified")

    result = search_memories(
        [weak, strong],
        {
            "query": "AuthService uses verifier",
            "authorized_sensitivities": ["project"],
            "limit": 2,
        },
    )

    assert result["results"][0]["memory"]["id"] == strong.id
