import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import httpx
import redis
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from services.shared.database import SessionLocal
from services.shared.models import AuditLog, EmbeddingJob, Memory, MemoryConflict
from .config import settings
from .llm_router import get_chat_llm, get_embedding_vector


RELIABILITY_WEIGHTS = {
    "user_explicit": 1.0,
    "user_correction": 1.0,
    "ai_extracted": 0.8,
    "tool_result": 0.7,
    "external_content": 0.5,
    "ai_speculated": 0.4,
}

OPPOSING_PAIRS = [
    ("aws", "gcp"),
    ("aws", "render"),
    ("gcp", "render"),
    ("next.js", "vite"),
    ("react", "angular"),
    ("stripe", "paddle"),
    ("postgres", "mongodb"),
]


def get_embedding(text: str) -> list[float]:
    return get_embedding_vector(text or "")


def _as_vector(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    try:
        return list(value)
    except TypeError:
        return None


def cosine_distance_py(v1: list[float] | None, v2: list[float] | None) -> float:
    if v1 is None or v2 is None or len(v1) != len(v2):
        return 1.0
    dot = sum(x * y for x, y in zip(v1, v2))
    norm1 = math.sqrt(sum(x * x for x in v1))
    norm2 = math.sqrt(sum(x * x for x in v2))
    if norm1 == 0 or norm2 == 0:
        return 1.0
    return 1.0 - (dot / (norm1 * norm2))


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", (text or "").lower()) if len(t) > 2}


def _is_conflict(existing: str, incoming: str) -> bool:
    existing_lower = (existing or "").lower()
    incoming_lower = (incoming or "").lower()
    for left, right in OPPOSING_PAIRS:
        if (left in existing_lower and right in incoming_lower) or (right in existing_lower and left in incoming_lower):
            return True
    return False


def _has_meaningful_overlap(existing: str, incoming: str) -> bool:
    existing_terms = _tokenize(existing)
    incoming_terms = _tokenize(incoming)
    if not existing_terms or not incoming_terms:
        return False
    overlap = existing_terms & incoming_terms
    return len(overlap) >= 3 or (len(overlap) / max(len(incoming_terms), 1)) >= 0.35


def _memory_to_dict(memory: Memory, score: float | None = None, similarity: float | None = None) -> dict:
    return {
        "id": str(memory.id),
        "user_id": str(memory.user_id),
        "content": memory.content,
        "type": memory.type,
        "memory_type": memory.memory_type or memory.type,
        "importance": memory.importance or 5,
        "confidence": memory.confidence if memory.confidence is not None else 0.8,
        "source": memory.source or "ai_extracted",
        "source_url": memory.source_url,
        "access_count": memory.access_count or 0,
        "last_accessed_at": memory.last_accessed_at.isoformat() if memory.last_accessed_at else None,
        "is_archived": bool(memory.is_archived),
        "is_superseded": bool(memory.is_superseded),
        "tags": memory.tags or [],
        "related_memory_ids": memory.related_memory_ids or [],
        "compressed_from": memory.compressed_from or [],
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        "score": float(score) if score is not None else None,
        "similarity": float(similarity) if similarity is not None else None,
    }


@dataclass
class MemoryWrite:
    content: str
    memory_type: str = "fact"
    type: str = "fact"
    importance: int = 5
    confidence: float = 0.8
    source: str = "ai_extracted"
    source_session_id: UUID | None = None
    source_url: str | None = None
    tags: list[str] | None = None
    meta_data: dict | None = None


class PineconeVectorStore:
    def __init__(self):
        self.api_key = settings.PINECONE_API_KEY
        self.host = settings.PINECONE_HOST
        self.index = settings.PINECONE_INDEX

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.host)

    def upsert_memory(self, memory: Memory, vector: list[float]) -> bool:
        if not self.enabled:
            return False
        payload = {
            "vectors": [{
                "id": str(memory.id),
                "values": vector,
                "metadata": {
                    "user_id": str(memory.user_id),
                    "memory_type": memory.memory_type or memory.type,
                    "content": memory.content[:500],
                    "importance": memory.importance or 5,
                    "is_archived": bool(memory.is_archived),
                    "created_at": memory.created_at.isoformat() if memory.created_at else None,
                    "tags": memory.tags or [],
                },
            }],
            "namespace": f"user_{memory.user_id}",
        }
        response = httpx.post(
            f"{self.host.rstrip('/')}/vectors/upsert",
            headers={"Api-Key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        return True

    def query(self, user_id: UUID, vector: list[float], top_k: int = 20) -> list[dict]:
        if not self.enabled:
            return []
        response = httpx.post(
            f"{self.host.rstrip('/')}/query",
            headers={"Api-Key": self.api_key, "Content-Type": "application/json"},
            json={
                "vector": vector,
                "topK": top_k,
                "includeMetadata": True,
                "namespace": f"user_{user_id}",
                "filter": {"is_archived": {"$eq": False}},
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("matches", [])

    def delete_user(self, user_id: UUID) -> bool:
        if not self.enabled:
            return False
        response = httpx.post(
            f"{self.host.rstrip('/')}/vectors/delete",
            headers={"Api-Key": self.api_key, "Content-Type": "application/json"},
            json={"deleteAll": True, "namespace": f"user_{user_id}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return True


class Neo4jGraphStore:
    def __init__(self):
        self.enabled = bool(settings.NEO4J_URI and settings.NEO4J_USERNAME and settings.NEO4J_PASSWORD)
        self._driver = None
        if self.enabled:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(
                    settings.NEO4J_URI,
                    auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
                )
            except Exception:
                self.enabled = False

    def sync_memory(self, memory: Memory) -> bool:
        if not self.enabled or not self._driver:
            return False
        concepts = self._extract_concepts(memory)
        with self._driver.session() as session:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                MERGE (m:Memory {id: $memory_id})
                SET m.content = $content, m.memory_type = $memory_type
                MERGE (u)-[:HAS_MEMORY]->(m)
                """,
                user_id=str(memory.user_id),
                memory_id=str(memory.id),
                content=memory.content[:1000],
                memory_type=memory.memory_type or memory.type,
            )
            for concept in concepts:
                session.run(
                    """
                    MERGE (c:Concept {name: $name})
                    WITH c
                    MATCH (m:Memory {id: $memory_id})
                    MERGE (m)-[:REFERENCES]->(c)
                    """,
                    name=concept,
                    memory_id=str(memory.id),
                )
        return True

    def delete_user(self, user_id: UUID) -> bool:
        if not self.enabled or not self._driver:
            return False
        with self._driver.session() as session:
            session.run("MATCH (u:User {id: $user_id}) DETACH DELETE u", user_id=str(user_id))
        return True

    def _extract_concepts(self, memory: Memory) -> list[str]:
        tags = [str(t).strip() for t in (memory.tags or []) if str(t).strip()]
        capitalized = re.findall(r"\b[A-Z][A-Za-z0-9\.\-]{2,}\b", memory.content or "")
        return sorted(set((tags + capitalized)[:20]))


class RedisShortTermMemoryStore:
    def __init__(self):
        self.ttl = settings.SHORT_TERM_MEMORY_TTL_SECONDS
        self.max_events = settings.SHORT_TERM_MEMORY_MAX_EVENTS
        try:
            if settings.REDIS_URL:
                self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            else:
                self.client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=0,
                    decode_responses=True,
                )
            self.client.ping()
        except Exception:
            self.client = None

    def _key(self, user_id: UUID | str, session_id: str) -> str:
        return f"stm:{user_id}:{session_id}"

    def append_event(self, user_id: UUID | str, session_id: str, event: dict) -> dict:
        if not self.client:
            return {"stored": False, "reason": "redis_unavailable"}
        key = self._key(user_id, session_id)
        payload = {
            "role": event.get("role", "user"),
            "content": event.get("content", ""),
            "name": event.get("name"),
            "timestamp": event.get("timestamp") or datetime.utcnow().isoformat() + "Z",
            "meta_data": event.get("meta_data") or {},
        }
        self.client.rpush(key, json.dumps(payload))
        self.client.expire(key, self.ttl)
        length = self.client.llen(key)
        if length > self.max_events:
            self.client.ltrim(key, -self.max_events, -1)
        return {"stored": True, "event_count": min(length, self.max_events), "compression_suggested": length >= settings.SHORT_TERM_MEMORY_COMPRESS_AT}

    def read_events(self, user_id: UUID | str, session_id: str, limit: int = 50) -> list[dict]:
        if not self.client:
            return []
        key = self._key(user_id, session_id)
        raw_events = self.client.lrange(key, max(0, -limit), -1)
        self.client.expire(key, self.ttl)
        events = []
        for raw in raw_events:
            try:
                events.append(json.loads(raw))
            except Exception:
                continue
        return events

    def delete_user_sessions(self, user_id: UUID | str) -> int:
        if not self.client:
            return 0
        deleted = 0
        for key in self.client.scan_iter(match=f"stm:{user_id}:*"):
            deleted += self.client.delete(key)
        return deleted


class PostgresMemoryStore:
    def __init__(self, db: Session):
        self.db = db
        self.pinecone = PineconeVectorStore()
        self.graph = Neo4jGraphStore()

    def list_memories(
        self,
        user_id: UUID,
        memory_type: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[Memory]:
        query = self.db.query(Memory).filter(Memory.user_id == user_id)
        if not include_archived:
            query = query.filter(Memory.is_archived == False)
        if memory_type:
            query = query.filter(or_(Memory.memory_type == memory_type, Memory.type == memory_type))
        return query.order_by(Memory.importance.desc(), Memory.updated_at.desc()).limit(min(limit, 500)).all()

    def create_memory(self, user_id: UUID, data: MemoryWrite) -> tuple[Memory, dict]:
        content = " ".join((data.content or "").split())
        if not content:
            raise ValueError("Memory content cannot be empty")

        vector = get_embedding(content)
        existing = self.list_memories(user_id, include_archived=False, limit=500)

        for memory in existing:
            similarity = 1.0 - cosine_distance_py(vector, _as_vector(memory.vector))
            if similarity > 0.92:
                return self._merge_duplicate(memory, data, vector), {"action": "merged", "similarity": similarity}

        conflicts = []
        for memory in existing:
            similarity = 1.0 - cosine_distance_py(vector, _as_vector(memory.vector))
            if _is_conflict(memory.content, content) and (similarity >= 0.70 or _has_meaningful_overlap(memory.content, content)):
                memory.is_superseded = True
                memory.confidence = min(memory.confidence or 0.8, 0.3)
                conflicts.append((memory, similarity))

        memory = Memory(
            user_id=user_id,
            type=data.type or data.memory_type or "fact",
            memory_type=data.memory_type or data.type or "fact",
            content=content,
            vector=vector,
            content_vector=vector,
            source=data.source,
            source_session_id=data.source_session_id,
            source_url=data.source_url,
            confidence=max(0.0, min(1.0, data.confidence)),
            importance=max(1, min(10, data.importance)),
            tags=data.tags or [],
            related_memory_ids=[str(m.id) for m, _ in conflicts],
            meta_data=data.meta_data or {},
        )
        self.db.add(memory)
        self.db.flush()

        for existing_memory, similarity in conflicts:
            self.db.add(MemoryConflict(
                user_id=user_id,
                existing_memory_id=existing_memory.id,
                new_memory_id=memory.id,
                incoming_content=content,
                similarity=float(similarity),
                meta_data={"existing_content": existing_memory.content},
            ))

        self._queue_embedding_job(memory, provider="pgvector", status="completed")
        self._sync_external(memory, vector)
        self.db.commit()
        self.db.refresh(memory)
        return memory, {"action": "created", "conflicts": len(conflicts)}

    def _merge_duplicate(self, memory: Memory, data: MemoryWrite, vector: list[float]) -> Memory:
        if data.content not in memory.content:
            memory.content = f"{memory.content} | {data.content}"
        memory.importance = max(memory.importance or 5, data.importance)
        memory.confidence = max(memory.confidence or 0.8, data.confidence)
        memory.access_count = (memory.access_count or 0) + 1
        memory.last_accessed_at = datetime.utcnow()
        memory.vector = vector
        memory.content_vector = vector
        memory.tags = sorted(set((memory.tags or []) + (data.tags or [])))
        meta = memory.meta_data or {}
        meta.update(data.meta_data or {})
        meta["deduplicated_at"] = datetime.utcnow().isoformat() + "Z"
        memory.meta_data = meta
        flag_modified(memory, "meta_data")
        self._queue_embedding_job(memory, provider="pgvector", status="completed")
        self._sync_external(memory, vector)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def _queue_embedding_job(self, memory: Memory, provider: str, status: str = "queued", error: str | None = None) -> None:
        self.db.add(EmbeddingJob(
            user_id=memory.user_id,
            memory_id=memory.id,
            provider=provider,
            model=settings.EMBEDDING_MODEL,
            status=status,
            operation="upsert",
            error_message=error,
            attempts=1,
        ))

    def _sync_external(self, memory: Memory, vector: list[float]) -> None:
        if self.pinecone.enabled:
            try:
                self.pinecone.upsert_memory(memory, vector)
                self._queue_embedding_job(memory, provider="pinecone", status="completed")
            except Exception as exc:
                self._queue_embedding_job(memory, provider="pinecone", status="failed", error=str(exc))

        try:
            self.graph.sync_memory(memory)
        except Exception:
            pass

    def hybrid_search(self, user_id: UUID, query: str, limit: int = 10, memory_type: str | None = None) -> list[dict]:
        query_vector = get_embedding(query)
        candidates = self.list_memories(user_id, memory_type=memory_type, include_archived=False, limit=500)
        dense_ranked = self._dense_rank(candidates, query_vector)
        sparse_ranked = self._sparse_rank(candidates, query)

        external_matches = []
        try:
            external_matches = self.pinecone.query(user_id, query_vector, top_k=limit) if self.pinecone.enabled else []
        except Exception:
            external_matches = []

        scores: dict[str, float] = {}
        memories_by_id = {str(m.id): m for m in candidates}
        for rank, (memory, _) in enumerate(dense_ranked, 1):
            scores[str(memory.id)] = scores.get(str(memory.id), 0.0) + 1.0 / (60 + rank)
        for rank, (memory, _) in enumerate(sparse_ranked, 1):
            scores[str(memory.id)] = scores.get(str(memory.id), 0.0) + 1.0 / (60 + rank)
        for rank, match in enumerate(external_matches, 1):
            match_id = match.get("id")
            if match_id in memories_by_id:
                scores[match_id] = scores.get(match_id, 0.0) + 1.0 / (60 + rank)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        results = []
        max_access = max([m.access_count or 0 for m in candidates] + [1])

        for memory_id, rrf_score in ranked[:limit]:
            memory = memories_by_id[memory_id]
            similarity = 1.0 - cosine_distance_py(query_vector, _as_vector(memory.vector))
            final_score = self._final_score(memory, similarity, rrf_score, max_access)
            memory.access_count = (memory.access_count or 0) + 1
            memory.last_accessed_at = datetime.utcnow()
            results.append(_memory_to_dict(memory, score=final_score, similarity=similarity))

        self.db.commit()
        return sorted(results, key=lambda item: item["score"] or 0.0, reverse=True)[:limit]

    def _dense_rank(self, memories: list[Memory], query_vector: list[float]) -> list[tuple[Memory, float]]:
        ranked = []
        for memory in memories:
            similarity = 1.0 - cosine_distance_py(query_vector, _as_vector(memory.vector))
            ranked.append((memory, similarity))
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _sparse_rank(self, memories: list[Memory], query: str) -> list[tuple[Memory, float]]:
        query_terms = _tokenize(query)
        ranked = []
        for memory in memories:
            content_terms = _tokenize(memory.content)
            if not query_terms or not content_terms:
                score = 0.0
            else:
                overlap = len(query_terms & content_terms)
                score = overlap / max(len(query_terms), 1)
                if query.lower() in memory.content.lower():
                    score += 0.5
            if score > 0:
                ranked.append((memory, score))
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _final_score(self, memory: Memory, similarity: float, rrf_score: float, max_access: int) -> float:
        created_naive = memory.created_at.replace(tzinfo=None) if memory.created_at else datetime.utcnow()
        days_ago = max((datetime.utcnow() - created_naive).days, 0)
        recency = math.exp(-0.05 * days_ago)
        importance = (memory.importance or 5) / 10.0
        access_freq = math.log(1 + (memory.access_count or 0)) / math.log(1 + max_access)
        reliability = RELIABILITY_WEIGHTS.get(memory.source or "ai_extracted", 0.8)
        confidence = memory.confidence if memory.confidence is not None else 0.8
        return float(round(
            (0.35 * similarity)
            + (0.20 * recency)
            + (0.18 * importance)
            + (0.10 * access_freq)
            + (0.07 * reliability)
            + (0.05 * confidence)
            + (0.05 * min(rrf_score * 100, 1.0)),
            6,
        ))

    def update_memory(self, memory: Memory, **changes) -> Memory:
        content_changed = False
        for field in ["content", "type", "memory_type", "source", "source_url", "confidence", "importance", "tags", "is_archived", "expires_at"]:
            if field in changes and changes[field] is not None:
                setattr(memory, field, changes[field])
                content_changed = content_changed or field == "content"
        if "meta_data" in changes and changes["meta_data"] is not None:
            meta = memory.meta_data or {}
            meta.update(changes["meta_data"])
            memory.meta_data = meta
            flag_modified(memory, "meta_data")
        if content_changed:
            vector = get_embedding(memory.content)
            memory.vector = vector
            memory.content_vector = vector
            self._sync_external(memory, vector)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def archive_memory(self, memory: Memory) -> Memory:
        memory.is_archived = True
        meta = memory.meta_data or {}
        meta["archived_at"] = datetime.utcnow().isoformat() + "Z"
        memory.meta_data = meta
        flag_modified(memory, "meta_data")
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def compress_memories(self, user_id: UUID) -> int:
        candidates = [
            m for m in self.list_memories(user_id, include_archived=False, limit=1000)
            if (m.importance or 5) < 6 and (m.access_count or 0) < 3
        ]
        clusters: list[list[Memory]] = []
        for memory in candidates:
            placed = False
            for cluster in clusters:
                if cosine_distance_py(_as_vector(memory.vector), _as_vector(cluster[0].vector)) < 0.20:
                    cluster.append(memory)
                    placed = True
                    break
            if not placed:
                clusters.append([memory])

        compressed_count = 0
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            content = "Consolidated memory: " + " AND ".join(m.content for m in cluster)
            memory, _ = self.create_memory(
                user_id,
                MemoryWrite(
                    content=content,
                    memory_type="compressed",
                    type="compressed",
                    importance=max(m.importance or 5 for m in cluster),
                    confidence=max(m.confidence or 0.8 for m in cluster),
                    source="memory_compression",
                    tags=sorted({tag for m in cluster for tag in (m.tags or [])}),
                    meta_data={"compressed_from": [str(m.id) for m in cluster]},
                ),
            )
            memory.compressed_from = [str(m.id) for m in cluster]
            for original in cluster:
                original.is_archived = True
            compressed_count += 1
        self.db.commit()
        return compressed_count

    def archive_expired(self, user_id: UUID) -> int:
        threshold = datetime.utcnow() - timedelta(days=180)
        candidates = self.db.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.is_archived == False,
            Memory.importance < 4,
            or_(Memory.last_accessed_at == None, Memory.last_accessed_at < threshold),
        ).all()
        for memory in candidates:
            memory.is_archived = True
        self.db.commit()
        return len(candidates)

    def hard_delete_user_memories(self, user_id: UUID) -> dict:
        memory_ids = [m.id for m in self.db.query(Memory.id).filter(Memory.user_id == user_id).all()]
        deleted_count = len(memory_ids)
        self.db.query(MemoryConflict).filter(MemoryConflict.user_id == user_id).delete(synchronize_session=False)
        self.db.query(EmbeddingJob).filter(EmbeddingJob.user_id == user_id).delete(synchronize_session=False)
        self.db.query(Memory).filter(Memory.user_id == user_id).delete(synchronize_session=False)
        self.db.add(AuditLog(
            user_id=user_id,
            event_type="memory_hard_delete",
            entity_type="Memory",
            actor_type="system_memory",
            action=f"Hard-deleted {deleted_count} memory records for user",
            metadata_json={"deleted_count": deleted_count},
        ))
        self.db.commit()

        pinecone_deleted = False
        graph_deleted = False
        try:
            pinecone_deleted = self.pinecone.delete_user(user_id)
        except Exception:
            pinecone_deleted = False
        try:
            graph_deleted = self.graph.delete_user(user_id)
        except Exception:
            graph_deleted = False
        redis_deleted = RedisShortTermMemoryStore().delete_user_sessions(user_id)

        return {
            "postgres_deleted": deleted_count,
            "redis_sessions_deleted": redis_deleted,
            "pinecone_deleted": pinecone_deleted,
            "neo4j_deleted": graph_deleted,
        }


def retrieve_context(user_id: UUID, query: str, limit: int = 5) -> list[dict]:
    db = SessionLocal()
    try:
        return PostgresMemoryStore(db).hybrid_search(user_id, query, limit=limit)
    except Exception as e:
        print(f"Error retrieving memory context: {e}")
        return []
    finally:
        db.close()


def save_memory(user_id: UUID, content: str, mem_type: str, importance: int = 5, meta_data: dict | None = None) -> bool:
    db = SessionLocal()
    try:
        source = (meta_data or {}).get("source", "ai_extracted")
        confidence = float((meta_data or {}).get("confidence", 0.8))
        tags = (meta_data or {}).get("tags", [])
        PostgresMemoryStore(db).create_memory(
            user_id,
            MemoryWrite(
                content=content,
                memory_type=mem_type,
                type=mem_type,
                importance=importance,
                confidence=confidence,
                source=source,
                tags=tags,
                meta_data=meta_data or {},
            ),
        )
        return True
    except Exception as e:
        print(f"Error saving memory: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def compress_memories(db: Session, user_id: UUID) -> int:
    return PostgresMemoryStore(db).compress_memories(user_id)


def archive_expired_memories(db: Session, user_id: UUID) -> int:
    return PostgresMemoryStore(db).archive_expired(user_id)


def extract_memories(user_id: UUID, chat_history: str) -> list[dict]:
    is_mock = settings.LLM_PROVIDER.lower() in ("", "mock")
    extracted = []
    if is_mock:
        lowered = chat_history.lower()
        if "my name is" in lowered:
            name = lowered.split("my name is")[-1].strip().split()[0].strip(".,!?")
            extracted.append({"content": f"User's name is {name.title()}", "type": "fact", "importance": 8})
        if "i prefer" in lowered:
            pref = chat_history.split("i prefer", 1)[-1].strip().split(".")[0].strip()
            extracted.append({"content": f"User prefers {pref}", "type": "preference", "importance": 6})
    else:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            llm = get_chat_llm(role="extraction")
            response = llm.invoke([
                SystemMessage(content=(
                    "Extract stable long-term user memories from the conversation. "
                    "Return only JSON: [{\"content\":\"...\",\"type\":\"fact|preference|decision|relationship|skill|constraint|goal_context|tool_preference\",\"importance\":1-10,\"confidence\":0-1,\"tags\":[\"...\"]}]. "
                    "Return [] if nothing should be remembered."
                )),
                HumanMessage(content=chat_history),
            ])
            raw_text = response.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1].removeprefix("json").strip()
            parsed = json.loads(raw_text)
            extracted = parsed if isinstance(parsed, list) else parsed.get("memories", [])
        except Exception as e:
            print(f"Error extracting memories: {e}")
            extracted = []

    saved = []
    db = SessionLocal()
    try:
        store = PostgresMemoryStore(db)
        for item in extracted:
            content = item.get("content")
            if not content:
                continue
            memory, outcome = store.create_memory(
                user_id,
                MemoryWrite(
                    content=content,
                    memory_type=item.get("type", "fact"),
                    type=item.get("type", "fact"),
                    importance=int(item.get("importance", 5)),
                    confidence=float(item.get("confidence", 0.8)),
                    source="ai_extracted",
                    tags=item.get("tags", []),
                ),
            )
            saved.append({**item, "id": str(memory.id), "outcome": outcome})
        return saved
    finally:
        db.close()
