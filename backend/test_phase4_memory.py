from uuid import UUID

import pytest

from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Memory, MemoryConflict
from services.agent.memory_agent import (
    MemoryWrite,
    PineconeVectorStore,
    PostgresMemoryStore,
    RedisShortTermMemoryStore,
)


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    session.query(MemoryConflict).filter(MemoryConflict.user_id == USER_ID).delete()
    session.query(Memory).filter(Memory.user_id == USER_ID, Memory.content.like("Phase4 test%")).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(MemoryConflict).filter(MemoryConflict.user_id == USER_ID).delete()
        session.query(Memory).filter(Memory.user_id == USER_ID, Memory.content.like("Phase4 test%")).delete()
        session.commit()
        session.close()


def test_memory_create_search_and_archive(db):
    store = PostgresMemoryStore(db)
    memory, outcome = store.create_memory(
        USER_ID,
        MemoryWrite(
            content="Phase4 test user prefers concise technical bullet points",
            memory_type="preference",
            type="preference",
            importance=8,
            source="user_explicit",
            tags=["phase4", "preference"],
        ),
    )

    assert outcome["action"] == "created"
    assert memory.vector is not None
    assert memory.source == "user_explicit"

    results = store.hybrid_search(USER_ID, "concise bullet points", limit=3)
    assert any(item["id"] == str(memory.id) for item in results)

    store.archive_memory(memory)
    results_after_archive = store.hybrid_search(USER_ID, "concise bullet points", limit=3)
    assert all(item["id"] != str(memory.id) for item in results_after_archive)


def test_duplicate_memory_merges_existing_record(db):
    store = PostgresMemoryStore(db)
    first, _ = store.create_memory(
        USER_ID,
        MemoryWrite(content="Phase4 test duplicate stable fact", memory_type="fact", type="fact"),
    )
    second, outcome = store.create_memory(
        USER_ID,
        MemoryWrite(content="Phase4 test duplicate stable fact", memory_type="fact", type="fact", importance=9),
    )

    assert outcome["action"] == "merged"
    assert first.id == second.id
    assert second.importance == 9


def test_conflict_detection_creates_review_record(db):
    store = PostgresMemoryStore(db)
    store.create_memory(
        USER_ID,
        MemoryWrite(content="Phase4 test user prefers AWS for cloud hosting", memory_type="preference", type="preference"),
    )
    new_memory, outcome = store.create_memory(
        USER_ID,
        MemoryWrite(content="Phase4 test user prefers GCP for cloud hosting", memory_type="preference", type="preference"),
    )

    conflicts = db.query(MemoryConflict).filter(
        MemoryConflict.user_id == USER_ID,
        MemoryConflict.new_memory_id == new_memory.id,
    ).all()
    assert outcome["conflicts"] >= 1
    assert conflicts
    assert str(conflicts[0].new_memory_id) == str(new_memory.id)


def test_short_term_memory_redis_fallback_is_safe():
    store = RedisShortTermMemoryStore()
    result = store.append_event(USER_ID, "phase4-test-session", {"role": "user", "content": "hello"})
    assert "stored" in result
    events = store.read_events(USER_ID, "phase4-test-session")
    assert isinstance(events, list)


def test_external_vector_adapter_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr("services.agent.memory_agent.settings.PINECONE_API_KEY", None)
    monkeypatch.setattr("services.agent.memory_agent.settings.PINECONE_HOST", None)
    assert PineconeVectorStore().enabled is False
