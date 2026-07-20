from datetime import datetime, timezone
from uuid import uuid4

from services.agent.arceus_runtime.memory_fabric.service import (
    build_memory_payload,
    can_forget,
    classify_memory,
    memory_response_payload,
    relevance_score,
    search_memories,
    summarize_memories,
)
from services.shared.arceus_core_models import ArceusMemoryItem


def make_memory(**overrides):
    payload = {
        "memory_type": "episodic",
        "title": "Production outage recovery",
        "content": "During the production outage, Redis queue saturation caused delayed jobs. The recovery procedure is to pause new jobs, scale workers, clear dead letters, and verify queue depth.",
        "source_type": "incident",
        "source_ids": ["inc_1"],
        "evidence_ids": ["ev_1"],
        "memory_scope": "organization",
        "sensitivity": "organization",
        "relationships": [{"type": "caused_by", "target": "redis_queue"}],
        "tags": ["redis", "outage"],
        "importance": "critical",
    }
    payload.update(overrides)
    built = build_memory_payload(payload, owner_id=str(uuid4()))
    item = ArceusMemoryItem(
        id=uuid4(),
        tenant_id=uuid4(),
        memory_scope=built["memory_scope"],
        scope_reference_id=payload.get("scope_reference_id"),
        title=built["title"],
        content='{"content": %r, "memory": {}}' % built["content"],
        content_type=built["content_type"],
        source_type=built["source_type"],
        source_ids=built["source_ids"],
        evidence_ids=built["evidence_ids"],
        lifecycle_status=built["lifecycle_status"],
        trust_level=built["trust_level"],
        confidence=built["confidence"],
        sensitivity=built["sensitivity"],
        content_hash=built["content_hash"],
        created_at=datetime.now(timezone.utc),
    )
    from services.agent.arceus_runtime.memory_fabric.service import encode_content

    item.content = encode_content(built["content"], built["metadata"])
    return item


def test_memory_classification_covers_cognitive_categories():
    assert classify_memory({"title": "Incident report", "content": "Production outage resolved."}) == "episodic"
    assert classify_memory({"title": "Deployment playbook", "content": "Runbook and procedure for release."}) == "procedural"
    assert classify_memory({"title": "Company roadmap", "content": "Strategic objective and market positioning."}) == "strategic"
    assert classify_memory({"title": "SOC2 policy", "content": "Compliance audit control."}) == "compliance"


def test_build_memory_payload_preserves_provenance_importance_and_summary():
    built = build_memory_payload(
        {
            "title": "OAuth Architecture Decision",
            "content": "Architecture decision: use Clerk for authentication because it reduces implementation risk and supports organization SSO.",
            "source_type": "decision",
            "source_ids": ["dec_1"],
            "evidence_ids": ["ev_1", "ev_2"],
            "memory_scope": "project",
            "tags": ["authentication"],
        },
        owner_id=str(uuid4()),
    )

    assert built["content_type"] == "semantic"
    assert built["confidence"] >= 0.8
    assert built["metadata"]["provenance"]["source_ids"] == ["dec_1"]
    assert "authentication" in built["metadata"]["tags"]
    assert built["lifecycle_status"] == "verified"


def test_search_ranks_relevant_verified_memory_and_filters_sensitivity():
    incident = make_memory()
    private = make_memory(title="Private coding preference", content="Use compact responses.", sensitivity="private", importance="low")

    result = search_memories(
        [incident, private],
        {
            "query": "redis outage recovery procedure",
            "mission_context": {"system": "redis queue"},
            "authorized_sensitivities": ["organization"],
            "limit": 5,
        },
    )

    assert result["events"] == ["MEMORY_RECALLED"]
    assert len(result["results"]) == 1
    assert result["results"][0]["memory"]["title"] == "Production outage recovery"
    assert result["results"][0]["relevance_score"] > 0.5


def test_memory_response_decodes_cognitive_metadata():
    item = make_memory()
    response = memory_response_payload(item)

    assert response["memory_type"] == "episodic"
    assert response["importance"] == "critical"
    assert response["lifecycle_stage"] in {"verified", "active"}
    assert response["provenance"]["evidence_ids"] == ["ev_1"]
    assert response["relationships"][0]["target"] == "redis_queue"


def test_summarization_preserves_evidence_and_patterns():
    incident = make_memory()
    procedure = make_memory(title="Redis queue runbook", content="Runbook procedure: pause ingestion, scale workers, drain queue, verify metrics.", memory_type="procedural", importance="high")

    summary = summarize_memories([incident, procedure], query="redis outage")

    assert "MEMORY_SUMMARIZED" in summary["events"]
    assert "experience_to_procedure" in summary["patterns"]
    assert "ev_1" in summary["evidence_ids"]
    assert len(summary["source_memory_ids"]) == 2


def test_forgetting_blocks_critical_verified_memory_until_archived():
    item = make_memory()

    allowed, reason = can_forget(item)

    assert allowed is False
    assert "archived" in reason


def test_forgetting_allows_low_importance_archived_memory():
    item = make_memory(importance="low")
    item.lifecycle_status = "archived"

    allowed, reason = can_forget(item)

    assert allowed is True
    assert "forgotten" in reason or "can be forgotten" in reason


def test_relevance_score_explains_context_overlap():
    item = make_memory()
    score, factors = relevance_score(item, "redis recovery", {"runtime": "redis workers"})

    assert score > 0.4
    assert factors["context_overlap"] > 0
