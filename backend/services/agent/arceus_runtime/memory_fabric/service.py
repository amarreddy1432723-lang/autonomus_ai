from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from services.shared.arceus_core_models import ArceusMemoryItem

from ..compiler.utils import stable_hash


MEMORY_TYPES = {
    "episodic",
    "semantic",
    "procedural",
    "working",
    "operational",
    "strategic",
    "organizational",
    "project",
    "mission",
    "personal",
    "compliance",
    "historical",
}

SCOPE_MAP = {"working": "working", "task": "task", "mission": "mission", "project": "project", "workspace": "project", "organization": "organization", "global": "global", "personal": "organization"}
IMPORTANCE_ORDER = {"temporary": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SOURCE_RELIABILITY = {"verification": 0.9, "deployment": 0.86, "incident": 0.84, "decision": 0.82, "repository": 0.78, "document": 0.7, "chat": 0.55, "manual": 0.62, "ai": 0.48}
LIFECYCLE_BY_STATUS = {"proposed": "candidate", "verified": "verified", "approved": "active", "disputed": "candidate", "superseded": "summarized", "archived": "archived"}
RETENTION_POLICIES = {
    "working": {"default_scope": "working", "default_retention": "1 hour", "deletion_policy": "delete_after_task", "sensitivity": "task"},
    "conversation": {"default_scope": "mission", "default_retention": "90 days", "deletion_policy": "summarize_then_archive", "sensitivity": "mission"},
    "mission": {"default_scope": "mission", "default_retention": "permanent", "deletion_policy": "archive_only_when_verified", "sensitivity": "mission"},
    "repository": {"default_scope": "project", "default_retention": "permanent", "deletion_policy": "supersede_on_new_revision", "sensitivity": "project"},
    "semantic": {"default_scope": "project", "default_retention": "permanent", "deletion_policy": "version_and_supersede", "sensitivity": "project"},
    "procedural": {"default_scope": "organization", "default_retention": "permanent", "deletion_policy": "version_and_supersede", "sensitivity": "organization"},
    "organizational": {"default_scope": "organization", "default_retention": "permanent", "deletion_policy": "governed_archive", "sensitivity": "organization"},
    "user": {"default_scope": "organization", "default_retention": "until_user_deletes", "deletion_policy": "user_controlled", "sensitivity": "restricted"},
    "system": {"default_scope": "global", "default_retention": "permanent", "deletion_policy": "admin_governed", "sensitivity": "organization"},
}

RELATION_PATTERNS = (
    (re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\s+(uses|calls|imports|depends on|owns|implements|validates|creates|fixes|documents|approves)\s+([A-Z][A-Za-z0-9_./:-]{2,})", re.I), 0.78),
    (re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\s+is\s+(?:implemented by|backed by|protected by)\s+([A-Z][A-Za-z0-9_./:-]{2,})", re.I), 0.72),
    (re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\s*->\s*([A-Z][A-Za-z0-9_./:-]{2,})"), 0.68),
)


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (value or "").strip().lower()).strip("_")


def tokenize(value: str) -> list[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z0-9_./:-]+", value or "") if len(item) > 1]


def classify_memory(payload: dict[str, Any]) -> str:
    explicit = normalize_token(str(payload.get("memory_type") or ""))
    if explicit in MEMORY_TYPES:
        return explicit
    haystack = " ".join([payload.get("title", ""), payload.get("content", ""), payload.get("source_type", ""), " ".join(payload.get("tags") or [])]).lower()
    if any(term in haystack for term in ("runbook", "workflow", "playbook", "sop", "procedure", "how to")):
        return "procedural"
    if any(term in haystack for term in ("incident", "outage", "deployment", "meeting", "conversation", "completed mission")):
        return "episodic"
    if any(term in haystack for term in ("vision", "objective", "roadmap", "strategy", "market", "investment")):
        return "strategic"
    if any(term in haystack for term in ("gdpr", "soc2", "hipaa", "policy", "compliance", "audit")):
        return "compliance"
    if any(term in haystack for term in ("preference", "coding style", "favorite", "communication style")):
        return "personal"
    if any(term in haystack for term in ("api", "architecture", "standard", "business rule", "documentation", "schema")):
        return "semantic"
    return "semantic"


def normalize_scope(scope: str) -> str:
    return SCOPE_MAP.get(normalize_token(scope), "project")


def infer_importance(payload: dict[str, Any], memory_type: str) -> str:
    explicit = normalize_token(str(payload.get("importance") or ""))
    if explicit in IMPORTANCE_ORDER:
        return explicit
    content = " ".join([payload.get("title", ""), payload.get("content", "")]).lower()
    if any(term in content for term in ("production outage", "security incident", "legal requirement", "critical", "rollback")):
        return "critical"
    if memory_type in {"procedural", "strategic", "compliance"}:
        return "high"
    if memory_type == "working":
        return "temporary"
    return "medium"


def infer_confidence(payload: dict[str, Any]) -> float:
    if payload.get("confidence") is not None:
        return round(max(0.0, min(1.0, float(payload["confidence"]))), 3)
    source_type = normalize_token(str(payload.get("source_type") or "manual"))
    base = SOURCE_RELIABILITY.get(source_type, 0.6)
    corroboration = min(0.2, len(payload.get("evidence_ids") or []) * 0.04 + len(payload.get("source_ids") or []) * 0.02)
    human_bonus = 0.08 if source_type in {"verification", "decision", "incident"} else 0
    return round(max(0.1, min(0.98, base + corroboration + human_bonus)), 3)


def summarize_text(content: str, *, max_chars: int = 360) -> str:
    cleaned = re.sub(r"\s+", " ", content or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    sentence_match = re.match(r"^(.{80,360}?[.!?])\s", cleaned)
    if sentence_match:
        return sentence_match.group(1)
    return cleaned[: max_chars - 1].rstrip() + "."


def extract_themes(text: str, tags: list[str] | None = None, limit: int = 8) -> list[str]:
    stop = {"the", "and", "for", "that", "with", "this", "from", "into", "your", "will", "should", "are", "was", "were", "has", "have", "been"}
    tokens = [token for token in tokenize(text) if token not in stop and len(token) > 3]
    counts = Counter(tokens)
    result = [normalize_token(tag) for tag in tags or [] if normalize_token(tag)]
    for token, _ in counts.most_common(limit * 2):
        if token not in result:
            result.append(token)
        if len(result) >= limit:
            break
    return result


def canonical_relation(value: str) -> str:
    normalized = normalize_token(value.replace(" ", "_"))
    aliases = {"depends_on": "depends_on", "depends": "depends_on", "validates": "validates", "implemented_by": "implements", "backed_by": "uses", "protected_by": "uses"}
    return aliases.get(normalized, normalized or "related_to")


def extract_memory_facts(content: str, *, max_facts: int = 24) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    entities: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", content or "")
    for sentence in sentences:
        text = sentence.strip()
        if not text:
            continue
        for pattern, confidence in RELATION_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            groups = match.groups()
            if len(groups) == 3:
                subject, relation, obj = groups
            else:
                subject, obj = groups
                relation = "related_to"
            subject = subject.strip("`'\" ")
            obj = obj.strip("`'\" ")
            relation = canonical_relation(relation)
            fact = {"subject": subject, "relation": relation, "object": obj, "confidence": confidence, "source_quote": summarize_text(text, max_chars=220)}
            if fact not in facts:
                facts.append(fact)
            for label in (subject, obj):
                entities.setdefault(
                    normalize_token(label),
                    {
                        "node_id": "node_" + stable_hash({"label": label}).replace("sha256:", "")[:16],
                        "label": label,
                        "type": infer_entity_type(label),
                        "metadata": {"source": "memory_extraction"},
                    },
                )
            relationships.append(
                {
                    "edge_id": "edge_" + stable_hash(fact).replace("sha256:", "")[:16],
                    "from": entities[normalize_token(subject)]["node_id"],
                    "to": entities[normalize_token(obj)]["node_id"],
                    "relation": relation,
                    "confidence": confidence,
                    "metadata": {"source_quote": fact["source_quote"]},
                }
            )
            if len(facts) >= max_facts:
                return {"facts": facts, "entities": list(entities.values()), "relationships": relationships}
    if not facts:
        for token in extract_themes(content, limit=8):
            label = token.replace("_", " ").title()
            entities[normalize_token(label)] = {
                "node_id": "node_" + stable_hash({"label": label}).replace("sha256:", "")[:16],
                "label": label,
                "type": infer_entity_type(label),
                "metadata": {"source": "theme_extraction"},
            }
    return {"facts": facts, "entities": list(entities.values()), "relationships": relationships}


def infer_entity_type(label: str) -> str:
    value = label.lower()
    if any(term in value for term in ("service", "manager", "controller", "adapter", "verifier")):
        return "Service"
    if any(term in value for term in ("api", "endpoint", "route")):
        return "API"
    if any(term in value for term in ("db", "database", "schema", "table")):
        return "Database"
    if any(term in value for term in ("mission", "task", "approval")):
        return "Mission"
    if any(term in value for term in ("tool", "model", "agent")):
        return "Tool"
    return "Entity"


def build_memory_payload(payload: dict[str, Any], *, owner_id: str | None = None) -> dict[str, Any]:
    memory_type = classify_memory(payload)
    memory_scope = normalize_scope(payload.get("memory_scope", "project"))
    importance = infer_importance(payload, memory_type)
    confidence = infer_confidence(payload)
    summary = summarize_text(payload.get("content", ""))
    tags = sorted(set(extract_themes(" ".join([payload.get("title", ""), payload.get("content", "")]), payload.get("tags") or [])))
    provenance = {
        "source_type": normalize_token(payload.get("source_type", "manual")),
        "source_ids": [str(item) for item in payload.get("source_ids") or []],
        "evidence_ids": [str(item) for item in payload.get("evidence_ids") or []],
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "owner_id": owner_id or (str(payload.get("owner_id")) if payload.get("owner_id") else None),
    }
    envelope = {
        "memory_type": memory_type,
        "summary": summary,
        "importance": importance,
        "relationships": payload.get("relationships") or [],
        "tags": tags,
        "retention_policy": normalize_token(payload.get("retention_policy", "standard")),
        "provenance": provenance,
    }
    content_hash = stable_hash({"title": payload.get("title"), "content": payload.get("content"), "envelope": envelope})
    return {
        "memory_scope": memory_scope,
        "title": payload["title"],
        "content": payload["content"],
        "content_type": memory_type,
        "source_type": provenance["source_type"],
        "source_ids": provenance["source_ids"],
        "evidence_ids": provenance["evidence_ids"],
        "lifecycle_status": "verified" if confidence >= 0.72 else "proposed",
        "trust_level": "governed" if confidence >= 0.72 else "unverified",
        "confidence": confidence,
        "sensitivity": normalize_token(payload.get("sensitivity", "mission")),
        "content_hash": content_hash,
        "valid_until": payload.get("expires_at"),
        "metadata": envelope,
    }


def encode_content(raw_content: str, metadata: dict[str, Any]) -> str:
    return json.dumps({"content": raw_content, "memory": metadata}, sort_keys=True, default=str)


def decode_content(item: ArceusMemoryItem) -> tuple[str, dict[str, Any]]:
    try:
        decoded = json.loads(item.content)
    except (TypeError, json.JSONDecodeError):
        return item.content, {}
    if isinstance(decoded, dict) and "memory" in decoded:
        return str(decoded.get("content") or ""), decoded.get("memory") or {}
    return item.content, {}


def memory_response_payload(item: ArceusMemoryItem) -> dict[str, Any]:
    raw_content, metadata = decode_content(item)
    return {
        "id": item.id,
        "memory_type": metadata.get("memory_type") or item.content_type,
        "memory_scope": item.memory_scope,
        "scope_reference_id": item.scope_reference_id,
        "owner_id": metadata.get("provenance", {}).get("owner_id"),
        "title": item.title,
        "summary": metadata.get("summary") or summarize_text(raw_content),
        "content": raw_content,
        "importance": metadata.get("importance") or "medium",
        "lifecycle_stage": LIFECYCLE_BY_STATUS.get(item.lifecycle_status, "candidate"),
        "lifecycle_status": item.lifecycle_status,
        "trust_level": item.trust_level,
        "confidence": item.confidence,
        "sensitivity": item.sensitivity,
        "provenance": metadata.get("provenance") or {"source_type": item.source_type, "source_ids": item.source_ids or [], "evidence_ids": item.evidence_ids or []},
        "relationships": metadata.get("relationships") or [],
        "tags": metadata.get("tags") or [],
        "retention_policy": metadata.get("retention_policy") or "standard",
        "content_hash": item.content_hash,
        "created_at": item.created_at,
        "valid_until": item.valid_until,
    }


def graph_projection_for_memory(item: ArceusMemoryItem) -> dict[str, Any]:
    raw_content, metadata = decode_content(item)
    extracted = extract_memory_facts(raw_content)
    memory_node = {
        "node_id": "memory_" + str(item.id),
        "label": item.title,
        "type": "Memory",
        "metadata": {
            "memory_type": metadata.get("memory_type") or item.content_type,
            "memory_scope": item.memory_scope,
            "confidence": item.confidence,
            "trust_level": item.trust_level,
        },
    }
    nodes = [memory_node] + extracted["entities"]
    edges = [
        {
            "edge_id": "edge_" + stable_hash({"memory": str(item.id), "node": node["node_id"]}).replace("sha256:", "")[:16],
            "from": memory_node["node_id"],
            "to": node["node_id"],
            "relation": "documents",
            "confidence": float(item.confidence or 0.5),
            "metadata": {"source": "memory_projection"},
        }
        for node in extracted["entities"]
    ]
    edges.extend(extracted["relationships"])
    graph_hash = stable_hash({"memory_id": str(item.id), "nodes": nodes, "edges": edges})
    return {"memory_id": item.id, "nodes": nodes, "edges": edges, "graph_hash": graph_hash}


def relevance_score(item: ArceusMemoryItem, query: str, mission_context: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
    raw_content, metadata = decode_content(item)
    query_terms = set(tokenize(query))
    context_terms = set(tokenize(" ".join(str(value) for value in (mission_context or {}).values())))
    haystack_terms = set(tokenize(" ".join([item.title, raw_content, " ".join(metadata.get("tags") or []), item.content_type, item.memory_scope])))
    lexical = len(query_terms.intersection(haystack_terms)) / max(1, len(query_terms))
    context_overlap = len(context_terms.intersection(haystack_terms)) / max(1, len(context_terms)) if context_terms else 0
    confidence = float(item.confidence or 0.45)
    importance = IMPORTANCE_ORDER.get(metadata.get("importance", "medium"), 2) / 4
    lifecycle = 1.0 if item.lifecycle_status in {"approved", "verified"} else (0.25 if item.lifecycle_status == "archived" else 0.55)
    score = round((lexical * 0.44) + (context_overlap * 0.18) + (confidence * 0.2) + (importance * 0.12) + (lifecycle * 0.06), 4)
    return score, {"lexical": lexical, "context_overlap": context_overlap, "confidence": confidence, "importance": importance, "lifecycle": lifecycle}


def search_memories(items: list[ArceusMemoryItem], payload: dict[str, Any]) -> dict[str, Any]:
    allowed_sensitivities = {normalize_token(item) for item in payload.get("authorized_sensitivities") or []}
    memory_types = {normalize_token(item) for item in payload.get("memory_types") or []}
    memory_scopes = {normalize_scope(item) for item in payload.get("memory_scopes") or []}
    include_archived = bool(payload.get("include_archived", False))
    scored = []
    for item in items:
        raw_content, metadata = decode_content(item)
        memory_type = normalize_token(metadata.get("memory_type") or item.content_type)
        if memory_types and memory_type not in memory_types:
            continue
        if memory_scopes and item.memory_scope not in memory_scopes:
            continue
        if item.sensitivity not in allowed_sensitivities:
            continue
        if item.lifecycle_status == "archived" and not include_archived:
            continue
        score, factors = relevance_score(item, payload["query"], payload.get("mission_context") or {})
        if score <= 0.05:
            continue
        scored.append((score, factors, item))
    scored.sort(key=lambda row: (-row[0], row[2].created_at), reverse=False)
    results = []
    for score, factors, item in scored[: int(payload.get("limit", 10))]:
        results.append(
            {
                "memory": memory_response_payload(item),
                "relevance_score": score,
                "ranking_factors": factors,
                "explanation": recall_explanation(item, score, factors),
            }
        )
    return {
        "query": payload["query"],
        "strategy": ["permission_filter", "scope_filter", "lexical_relevance", "context_overlap", "confidence_importance_ranking"],
        "results": results,
        "context_budget": {"requested_limit": payload.get("limit", 10), "returned": len(results), "estimated_tokens": sum(len(item["memory"]["summary"].split()) for item in results)},
        "events": ["MEMORY_RECALLED"],
    }


def recall_explanation(item: ArceusMemoryItem, score: float, factors: dict[str, Any]) -> str:
    return f"Recalled because it matched query/context terms with confidence {factors['confidence']:.2f} and relevance {score:.2f}."


def summarize_memories(items: list[ArceusMemoryItem], *, query: str | None = None) -> dict[str, Any]:
    payloads = [memory_response_payload(item) for item in items]
    combined = " ".join([item["summary"] or item["content"] for item in payloads])
    themes = extract_themes(" ".join([combined, query or ""]), limit=10)
    patterns = []
    if any(item["memory_type"] == "episodic" for item in payloads) and any(item["memory_type"] == "procedural" for item in payloads):
        patterns.append("experience_to_procedure")
    if any(item["importance"] in {"critical", "high"} for item in payloads):
        patterns.append("high_importance_recall")
    if any(item["memory_type"] == "strategic" for item in payloads):
        patterns.append("strategy_linked_context")
    evidence_ids = sorted({evidence for item in payloads for evidence in item["provenance"].get("evidence_ids", [])})
    summary = summarize_text(combined, max_chars=900) if combined else "No memories matched the requested summary scope."
    return {"summary": summary, "themes": themes, "patterns": patterns, "evidence_ids": evidence_ids, "source_memory_ids": [item["id"] for item in payloads], "events": ["MEMORY_SUMMARIZED", "MEMORY_CONSOLIDATED"]}


def detect_memory_conflicts(items: list[ArceusMemoryItem]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[ArceusMemoryItem]] = defaultdict(list)
    for item in items:
        raw_content, _ = decode_content(item)
        facts = extract_memory_facts(raw_content)["facts"]
        for fact in facts:
            grouped[(normalize_token(fact["subject"]), normalize_token(fact["relation"]))].append(item)
    conflicts: list[dict[str, Any]] = []
    for (subject, relation), rows in grouped.items():
        unique_objects = {}
        for item in rows:
            raw_content, _ = decode_content(item)
            for fact in extract_memory_facts(raw_content)["facts"]:
                if normalize_token(fact["subject"]) == subject and normalize_token(fact["relation"]) == relation:
                    unique_objects.setdefault(normalize_token(fact["object"]), []).append(item)
        if len(unique_objects) < 2:
            continue
        contenders = sorted({item for values in unique_objects.values() for item in values}, key=lambda row: (float(row.confidence or 0), row.created_at), reverse=True)
        conflicts.append(
            {
                "conflict_key": stable_hash({"subject": subject, "relation": relation}).replace("sha256:", "")[:20],
                "title": f"Conflicting memories for {subject.replace('_', ' ')} {relation.replace('_', ' ')}",
                "memory_ids": [item.id for item in contenders],
                "reason": "Multiple verified or proposed memories state different objects for the same subject/relation.",
                "suggested_winner_id": contenders[0].id if contenders else None,
                "resolution_strategy": "newest_highest_confidence_wins",
            }
        )
    return conflicts


def apply_memory_feedback(item: ArceusMemoryItem, *, rating: str, confidence_delta: float | None = None) -> dict[str, Any]:
    previous = item.confidence
    current = float(item.confidence or 0.5)
    default_delta = {"correct": 0.06, "incorrect": -0.22, "outdated": -0.12, "incomplete": -0.06}.get(rating, 0.0)
    delta = confidence_delta if confidence_delta is not None else default_delta
    item.confidence = round(max(0.0, min(1.0, current + float(delta))), 3)
    if rating == "correct" and item.confidence >= 0.72 and item.lifecycle_status == "proposed":
        item.lifecycle_status = "verified"
        item.trust_level = "governed"
    elif rating in {"incorrect", "outdated"} and item.lifecycle_status in {"verified", "approved"}:
        item.lifecycle_status = "disputed"
        item.trust_level = "disputed"
    return {"previous_confidence": previous, "new_confidence": item.confidence, "lifecycle_status": item.lifecycle_status}


def can_forget(item: ArceusMemoryItem) -> tuple[bool, str]:
    raw_content, metadata = decode_content(item)
    importance = metadata.get("importance", "medium")
    retention = metadata.get("retention_policy", "standard")
    if retention in {"legal_hold", "audit_hold"}:
        return False, "Memory is under retention hold and cannot be forgotten."
    if importance == "critical" and item.lifecycle_status in {"approved", "verified"}:
        return False, "Critical verified memory must be archived before deletion."
    return True, "Memory can be forgotten under current policy."
