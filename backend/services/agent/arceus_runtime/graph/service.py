from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from ..compiler.utils import stable_hash


ENTITY_LAYERS = {
    "person": "business",
    "organization": "business",
    "workspace": "execution",
    "project": "business",
    "mission": "execution",
    "repository": "application",
    "service": "application",
    "database": "application",
    "infrastructure": "infrastructure",
    "customer": "business",
    "product": "business",
    "api": "application",
    "workflow": "execution",
    "decision": "knowledge",
    "policy": "knowledge",
    "risk": "knowledge",
    "document": "knowledge",
    "artifact": "knowledge",
    "model": "execution",
    "ai_specialist": "learning",
    "capability": "learning",
    "vendor": "business",
}

RELATIONSHIPS = {
    "owns",
    "depends_on",
    "calls",
    "implements",
    "deploys_to",
    "reviews",
    "approves",
    "contains",
    "communicates_with",
    "belongs_to",
    "uses",
    "generates",
    "governs",
    "mitigates",
    "references",
}

SOURCE_RELIABILITY = {
    "github": 0.86,
    "gitlab": 0.84,
    "postgresql": 0.88,
    "monitoring": 0.82,
    "salesforce": 0.78,
    "jira": 0.76,
    "slack": 0.54,
    "manual": 0.62,
    "ai": 0.48,
}


def normalize_key(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "unknown"


def entity_id(entity_type: str, canonical_name: str) -> str:
    return "dt_" + stable_hash({"type": entity_type.lower(), "name": normalize_key(canonical_name)}).replace("sha256:", "")[:24]


def relationship_id(source_id: str, destination_id: str, relationship_type: str) -> str:
    return "dr_" + stable_hash({"source": source_id, "destination": destination_id, "type": relationship_type.lower()}).replace("sha256:", "")[:24]


def _provenance_payload(provenance: list[dict[str, Any]], *, fallback_source: str, fallback_connector: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    if not provenance:
        provenance = [{"source": fallback_source, "connector": fallback_connector, "observed_at": now, "confidence": 0.62}]
    rows = []
    for item in provenance:
        observed = item.get("observed_at") or now
        if hasattr(observed, "isoformat"):
            observed = observed.isoformat()
        rows.append(
            {
                "source": str(item.get("source") or fallback_source),
                "connector": str(item.get("connector") or fallback_connector),
                "observed_at": observed,
                "confidence": float(item.get("confidence", 0.7)),
                "source_version": item.get("source_version"),
            }
        )
    return rows


def confidence_from_provenance(provenance: list[dict[str, Any]], explicit: float | None = None) -> float:
    if explicit is not None:
        return round(max(0.0, min(1.0, float(explicit))), 3)
    if not provenance:
        return 0.5
    scores = []
    connectors = set()
    for item in provenance:
        connector = str(item.get("connector") or "manual").lower()
        connectors.add(connector)
        base = SOURCE_RELIABILITY.get(connector, 0.6)
        scores.append(base * float(item.get("confidence", 0.7)))
    corroboration = min(0.2, max(0, len(connectors) - 1) * 0.08)
    return round(max(0.1, min(0.98, (sum(scores) / len(scores)) + corroboration)), 3)


def normalize_entity(payload: dict[str, Any], *, source_system: str, connector: str) -> dict[str, Any]:
    entity_type = str(payload["entity_type"]).strip().lower()
    canonical_name = str(payload["canonical_name"]).strip()
    aliases = sorted(set([canonical_name, *[str(alias).strip() for alias in payload.get("aliases", []) if str(alias).strip()]]))
    provenance = _provenance_payload(payload.get("provenance") or [], fallback_source=source_system, fallback_connector=connector)
    return {
        "entity_id": entity_id(entity_type, canonical_name),
        "entity_type": entity_type,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "attributes": normalize_attributes(payload.get("attributes") or {}),
        "version": int(payload.get("version") or 1),
        "provenance": provenance,
        "confidence": confidence_from_provenance(provenance, payload.get("confidence")),
        "layer": ENTITY_LAYERS.get(entity_type, "knowledge"),
    }


def normalize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        norm_key = normalize_key(str(key)).replace("-", "_")
        if isinstance(value, str):
            normalized[norm_key] = value.strip()
        elif isinstance(value, (int, float, bool)) or value is None:
            normalized[norm_key] = value
        else:
            normalized[norm_key] = value
    return normalized


def resolve_entities(entities: list[dict[str, Any]], *, source_system: str, connector: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in entities:
        normalized = normalize_entity(item, source_system=source_system, connector=connector)
        keys = [normalize_key(alias) for alias in normalized["aliases"]]
        grouped[(normalized["entity_type"], sorted(keys)[0])].append(normalized)
    resolved = []
    for items in grouped.values():
        base = max(items, key=lambda item: item["confidence"]).copy()
        aliases = set()
        provenance = []
        attributes = {}
        for item in items:
            aliases.update(item["aliases"])
            provenance.extend(item["provenance"])
            attributes.update(item["attributes"])
        base["aliases"] = sorted(aliases)
        base["provenance"] = provenance
        base["attributes"] = attributes
        base["confidence"] = confidence_from_provenance(provenance)
        base["version"] = max(item["version"] for item in items)
        resolved.append(base)
    return sorted(resolved, key=lambda item: (item["entity_type"], item["canonical_name"]))


def normalize_relationship(payload: dict[str, Any], entities_by_key: dict[str, dict[str, Any]], *, source_system: str, connector: str) -> dict[str, Any]:
    relationship_type = normalize_key(str(payload["relationship_type"])).replace("-", "_")
    source = entities_by_key.get(normalize_key(str(payload["source_key"])))
    destination = entities_by_key.get(normalize_key(str(payload["destination_key"])))
    source_id = source["entity_id"] if source else str(payload["source_key"])
    destination_id = destination["entity_id"] if destination else str(payload["destination_key"])
    provenance = _provenance_payload(payload.get("provenance") or [], fallback_source=source_system, fallback_connector=connector)
    return {
        "relationship_id": relationship_id(source_id, destination_id, relationship_type),
        "source_id": source_id,
        "destination_id": destination_id,
        "relationship_type": relationship_type,
        "attributes": normalize_attributes(payload.get("attributes") or {}),
        "version": int(payload.get("version") or 1),
        "provenance": provenance,
        "confidence": confidence_from_provenance(provenance, payload.get("confidence")),
    }


def build_digital_twin_sync(payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    connector = str(payload["connector"])
    source_system = str(payload["source_system"])
    entities = resolve_entities(payload.get("entities") or [], source_system=source_system, connector=connector)
    entities_by_key: dict[str, dict[str, Any]] = {}
    for entity in entities:
        for alias in entity["aliases"]:
            entities_by_key[normalize_key(alias)] = entity
        entities_by_key[normalize_key(entity["canonical_name"])] = entity
    relationships = [
        normalize_relationship(item, entities_by_key, source_system=source_system, connector=connector)
        for item in payload.get("relationships") or []
    ]
    consistency = validate_graph_consistency(entities, relationships)
    graph_hash = stable_hash({"entities": entities, "relationships": relationships})
    diff = {
        "entity_ids": [item["entity_id"] for item in entities],
        "relationship_ids": [item["relationship_id"] for item in relationships],
        "incremental": bool(payload.get("incremental", True)),
        "provenance_updates": sum(len(item["provenance"]) for item in entities) + sum(len(item["provenance"]) for item in relationships),
    }
    return {
        "graph_hash": graph_hash,
        "synced_at": now,
        "connector": connector,
        "source_system": source_system,
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "resolved_entities": entities,
        "relationships": relationships,
        "diff": diff,
        "consistency": consistency,
        "events": ["CONNECTOR_SYNCED", "ENTITY_RESOLVED", "GRAPH_UPDATED", "DIGITAL_TWIN_REFRESHED"],
    }


def validate_graph_consistency(entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    entity_ids = {item["entity_id"] for item in entities}
    violations = []
    for entity in entities:
        if not entity["provenance"]:
            violations.append({"type": "missing_provenance", "entity_id": entity["entity_id"], "severity": "high"})
        if entity["confidence"] < 0.35:
            violations.append({"type": "low_confidence_entity", "entity_id": entity["entity_id"], "severity": "medium"})
    for relationship in relationships:
        if relationship["source_id"] not in entity_ids:
            violations.append({"type": "orphan_relationship_source", "relationship_id": relationship["relationship_id"], "severity": "high"})
        if relationship["destination_id"] not in entity_ids:
            violations.append({"type": "orphan_relationship_destination", "relationship_id": relationship["relationship_id"], "severity": "high"})
        if relationship["relationship_type"] not in RELATIONSHIPS:
            violations.append({"type": "non_canonical_relationship", "relationship_id": relationship["relationship_id"], "severity": "medium"})
    return {
        "valid": not any(item["severity"] == "high" for item in violations),
        "violations": violations,
        "entity_count": len(entities),
        "relationship_count": len(relationships),
    }


def graph_search(query: str, entities: list[dict[str, Any]], relationships: list[dict[str, Any]], *, entity_types: list[str] | None = None, limit: int = 10) -> dict[str, Any]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_./:-]+", query)]
    allowed_types = {item.lower() for item in (entity_types or [])}
    scored = []
    for entity in entities:
        if allowed_types and entity["entity_type"] not in allowed_types:
            continue
        haystack = " ".join([entity["canonical_name"], entity["entity_type"], entity["layer"], " ".join(entity["aliases"]), str(entity["attributes"])]).lower()
        score = sum(1 for term in terms if term in haystack) + entity["confidence"]
        if score > entity["confidence"]:
            scored.append((score, entity))
    scored.sort(key=lambda item: (-item[0], -item[1]["confidence"], item[1]["canonical_name"]))
    results = [item for _, item in scored[:limit]]
    result_ids = {item["entity_id"] for item in results}
    related = [edge for edge in relationships if edge["source_id"] in result_ids or edge["destination_id"] in result_ids]
    return {"query": query, "strategy": ["keyword", "alias_resolution", "relationship_adjacency", "confidence_ranking"], "results": results, "related_relationships": related[: limit * 2]}


def graph_query(payload: dict[str, Any], entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
    start = payload.get("start_entity")
    relationship_types = {normalize_key(item).replace("-", "_") for item in payload.get("relationship_types") or []}
    max_depth = int(payload.get("max_depth", 2))
    include_low = bool(payload.get("include_low_confidence", False))
    by_id = {item["entity_id"]: item for item in entities}
    by_name = {normalize_key(item["canonical_name"]): item for item in entities}
    start_entity = by_name.get(normalize_key(start)) if start else None
    selected_entities: dict[str, dict[str, Any]] = {}
    selected_relationships: dict[str, dict[str, Any]] = {}
    queue = deque([(start_entity["entity_id"], 0)] if start_entity else [(item["entity_id"], 0) for item in entities[:25]])
    while queue:
        entity_id_value, depth = queue.popleft()
        if entity_id_value in selected_entities or entity_id_value not in by_id or depth > max_depth:
            continue
        entity = by_id[entity_id_value]
        if not include_low and entity["confidence"] < 0.35:
            continue
        selected_entities[entity_id_value] = entity
        if depth == max_depth:
            continue
        for edge in relationships:
            if relationship_types and edge["relationship_type"] not in relationship_types:
                continue
            if edge["source_id"] == entity_id_value or edge["destination_id"] == entity_id_value:
                selected_relationships[edge["relationship_id"]] = edge
                next_id = edge["destination_id"] if edge["source_id"] == entity_id_value else edge["source_id"]
                queue.append((next_id, depth + 1))
    layers = Counter(item["layer"] for item in selected_entities.values())
    return {
        "query": payload,
        "entities": list(selected_entities.values()),
        "relationships": list(selected_relationships.values()),
        "reasoning": {
            "traversal": "bounded_breadth_first",
            "layer_counts": dict(layers),
            "relationship_filter": sorted(relationship_types),
            "impact_ready": bool(selected_relationships),
        },
    }


def history_from_snapshots(entity_id_value: str | None, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = []
    provenance_counter = Counter()
    current_version = None
    for snapshot in snapshots:
        for entity in snapshot.get("resolved_entities", []):
            if entity_id_value and entity["entity_id"] != entity_id_value:
                continue
            current_version = max(current_version or 0, int(entity.get("version", 1)))
            for item in entity.get("provenance", []):
                provenance_counter[str(item.get("connector", "unknown"))] += 1
            timeline.append(
                {
                    "entity_id": entity["entity_id"],
                    "canonical_name": entity["canonical_name"],
                    "version": entity.get("version", 1),
                    "confidence": entity.get("confidence", 0),
                    "sources": sorted({item.get("source") for item in entity.get("provenance", []) if item.get("source")}),
                }
            )
    return {
        "entity_id": entity_id_value,
        "timeline": timeline,
        "current_version": current_version,
        "provenance_summary": dict(provenance_counter),
    }
