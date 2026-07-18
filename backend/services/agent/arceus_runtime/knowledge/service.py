from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from ..compiler.utils import stable_hash


ONTOLOGY_BY_TYPE = {
    "repository": "Development",
    "file": "Development",
    "module": "Development",
    "class": "Development",
    "function": "Development",
    "api": "Architecture",
    "database": "Runtime",
    "workflow": "Operations",
    "decision": "Knowledge",
    "incident": "Operations",
    "policy": "Compliance",
    "standard": "Knowledge",
    "infrastructure": "Infrastructure",
    "documentation": "Knowledge",
    "package": "Development",
}

MEMORY_LAYERS = ["working", "mission", "project", "organization", "global"]
IGNORED_SEGMENTS = {"node_modules", ".git", ".next", "dist", "build", "__pycache__"}


@dataclass(frozen=True)
class KnowledgeNode:
    node_id: str
    type: str
    name: str
    ontology: str
    metadata: dict[str, Any] = field(default_factory=dict)
    owner: str | None = None
    confidence: str = "observed"
    evidence: list[str] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "name": self.name,
            "version": self.version,
            "ontology": self.ontology,
            "metadata": self.metadata,
            "owner": self.owner,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class KnowledgeEdge:
    edge_id: str
    source: str
    destination: str
    relationship: str
    confidence: str = "observed"
    evidence: list[str] = field(default_factory=list)
    version: int = 1

    def to_payload(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source": self.source,
            "destination": self.destination,
            "relationship": self.relationship,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "version": self.version,
        }


def _node_id(*parts: Any) -> str:
    return "kg_" + stable_hash(parts).replace("sha256:", "")[:24]


def _edge_id(source: str, destination: str, relationship: str) -> str:
    return "ke_" + stable_hash({"source": source, "destination": destination, "relationship": relationship}).replace("sha256:", "")[:24]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def should_index_path(path: str) -> bool:
    normalized = normalize_path(path)
    parts = set(PurePosixPath(normalized).parts)
    return bool(normalized) and not parts.intersection(IGNORED_SEGMENTS)


def infer_language(path: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower()
    suffix = PurePosixPath(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".kt": "kotlin",
        ".swift": "swift",
        ".php": "php",
        ".rb": "ruby",
        ".sql": "sql",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
    }.get(suffix, "text")


def classify_file_node_type(path: str, language: str) -> str:
    lower = path.lower()
    name = PurePosixPath(lower).name
    if language == "markdown" or name in {"readme", "readme.md"} or "docs/" in lower or "/adr" in lower:
        return "documentation"
    if name.startswith("dockerfile") or ".github/workflows/" in lower or "docker-compose" in lower or "terraform" in lower:
        return "infrastructure"
    if language == "sql" or "migration" in lower or "schema" in lower:
        return "database"
    return "file"


def extract_symbols(path: str, language: str, content: str) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    if language == "python":
        for match in re.finditer(r"^\s*class\s+([A-Za-z_][\w]*)", content, re.MULTILINE):
            symbols.append({"type": "class", "name": match.group(1), "line": content[: match.start()].count("\n") + 1})
        for match in re.finditer(r"^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)", content, re.MULTILINE):
            symbols.append({"type": "function", "name": match.group(1), "line": content[: match.start()].count("\n") + 1})
    elif language in {"typescript", "javascript"}:
        for match in re.finditer(r"\b(?:class|interface|type)\s+([A-Za-z_$][\w$]*)", content):
            symbols.append({"type": "class", "name": match.group(1), "line": content[: match.start()].count("\n") + 1})
        for match in re.finditer(r"\b(?:function\s+|const\s+|let\s+|var\s+)([A-Za-z_$][\w$]*)\s*(?:=|\()", content):
            symbols.append({"type": "function", "name": match.group(1), "line": content[: match.start()].count("\n") + 1})
    elif language == "sql":
        for match in re.finditer(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)", content, re.IGNORECASE):
            symbols.append({"type": "database", "name": match.group(1), "line": content[: match.start()].count("\n") + 1})
    return symbols[:100]


def extract_dependencies(path: str, language: str, content: str) -> list[str]:
    dependencies: list[str] = []
    if language == "python":
        patterns = [r"^\s*import\s+([\w.]+)", r"^\s*from\s+([\w.]+)\s+import\s+"]
        for pattern in patterns:
            dependencies.extend(match.group(1) for match in re.finditer(pattern, content, re.MULTILINE))
    elif language in {"typescript", "javascript"}:
        for match in re.finditer(r"\bfrom\s+['\"]([^'\"]+)['\"]|import\(['\"]([^'\"]+)['\"]\)", content):
            dependencies.append(match.group(1) or match.group(2))
    elif language in {"yaml", "json"} and "redis" in content.lower():
        dependencies.append("redis")
    if "postgres" in content.lower() or "postgresql" in content.lower():
        dependencies.append("postgresql")
    if "redis" in content.lower():
        dependencies.append("redis")
    return sorted(set(dep for dep in dependencies if dep))[:80]


def extract_api_nodes(path: str, content: str) -> list[dict[str, Any]]:
    api_nodes: list[dict[str, Any]] = []
    patterns = [
        r"@(?:app|router)\.(get|post|put|patch|delete|websocket)\(['\"]([^'\"]+)['\"]",
        r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_./{}:-]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            api_nodes.append({"method": match.group(1).upper(), "path": match.group(2), "source_path": path})
    return api_nodes[:100]


def index_repository(payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    repository_id = str(payload["repository_id"])
    repository_name = str(payload["repository_name"])
    nodes: dict[str, KnowledgeNode] = {}
    edges: dict[str, KnowledgeEdge] = {}

    repo_node = KnowledgeNode(
        node_id=_node_id("repository", repository_id),
        type="repository",
        name=repository_name,
        ontology=ONTOLOGY_BY_TYPE["repository"],
        metadata={
            "repository_id": repository_id,
            "repository_url": payload.get("repository_url"),
            "default_branch": payload.get("default_branch", "main"),
        },
        confidence="verified",
        evidence=[repository_id],
        created_at=now,
    )
    nodes[repo_node.node_id] = repo_node

    changed_paths: list[str] = []
    for source_file in payload.get("files") or []:
        path = normalize_path(source_file["path"])
        if not should_index_path(path):
            continue
        content = source_file.get("content") or ""
        content_hash = source_file.get("content_hash") or stable_hash(content)
        language = infer_language(path, source_file.get("language"))
        file_type = classify_file_node_type(path, language)
        changed_paths.append(path)

        file_node = KnowledgeNode(
            node_id=_node_id("file", repository_id, path),
            type=file_type,
            name=PurePosixPath(path).name,
            ontology=ONTOLOGY_BY_TYPE[file_type],
            metadata={"path": path, "language": language, "content_hash": content_hash, "size": len(content)},
            confidence="observed",
            evidence=[content_hash],
            created_at=now,
        )
        nodes[file_node.node_id] = file_node
        edges[_edge_id(repo_node.node_id, file_node.node_id, "CONTAINS")] = KnowledgeEdge(
            edge_id=_edge_id(repo_node.node_id, file_node.node_id, "CONTAINS"),
            source=repo_node.node_id,
            destination=file_node.node_id,
            relationship="CONTAINS",
            evidence=[content_hash],
        )

        module_name = path.removesuffix(PurePosixPath(path).suffix).replace("/", ".")
        module_node = KnowledgeNode(
            node_id=_node_id("module", repository_id, module_name),
            type="module",
            name=module_name,
            ontology=ONTOLOGY_BY_TYPE["module"],
            metadata={"path": path, "language": language},
            confidence="observed",
            evidence=[content_hash],
            created_at=now,
        )
        nodes[module_node.node_id] = module_node
        edges[_edge_id(file_node.node_id, module_node.node_id, "CONTAINS")] = KnowledgeEdge(
            edge_id=_edge_id(file_node.node_id, module_node.node_id, "CONTAINS"),
            source=file_node.node_id,
            destination=module_node.node_id,
            relationship="CONTAINS",
            evidence=[content_hash],
        )

        for dependency in extract_dependencies(path, language, content):
            dep_node = KnowledgeNode(
                node_id=_node_id("package", dependency),
                type="package",
                name=dependency,
                ontology=ONTOLOGY_BY_TYPE["package"],
                metadata={"source_path": path},
                confidence="inferred" if dependency.startswith(".") else "observed",
                evidence=[content_hash],
                created_at=now,
            )
            nodes.setdefault(dep_node.node_id, dep_node)
            edges[_edge_id(module_node.node_id, dep_node.node_id, "DEPENDS_ON")] = KnowledgeEdge(
                edge_id=_edge_id(module_node.node_id, dep_node.node_id, "DEPENDS_ON"),
                source=module_node.node_id,
                destination=dep_node.node_id,
                relationship="DEPENDS_ON",
                confidence=dep_node.confidence,
                evidence=[content_hash],
            )

        for symbol in extract_symbols(path, language, content):
            symbol_node = KnowledgeNode(
                node_id=_node_id(symbol["type"], repository_id, path, symbol["name"]),
                type=symbol["type"],
                name=symbol["name"],
                ontology=ONTOLOGY_BY_TYPE[symbol["type"]],
                metadata={"path": path, "language": language, "line": symbol["line"]},
                confidence="observed",
                evidence=[content_hash],
                created_at=now,
            )
            nodes[symbol_node.node_id] = symbol_node
            edges[_edge_id(module_node.node_id, symbol_node.node_id, "CONTAINS")] = KnowledgeEdge(
                edge_id=_edge_id(module_node.node_id, symbol_node.node_id, "CONTAINS"),
                source=module_node.node_id,
                destination=symbol_node.node_id,
                relationship="CONTAINS",
                evidence=[content_hash],
            )
            if "test" in path.lower() or "spec" in path.lower():
                edges[_edge_id(symbol_node.node_id, module_node.node_id, "VERIFIES")] = KnowledgeEdge(
                    edge_id=_edge_id(symbol_node.node_id, module_node.node_id, "VERIFIES"),
                    source=symbol_node.node_id,
                    destination=module_node.node_id,
                    relationship="VERIFIES",
                    confidence="inferred",
                    evidence=[content_hash],
                )

        for api in extract_api_nodes(path, content):
            api_node = KnowledgeNode(
                node_id=_node_id("api", repository_id, api["method"], api["path"]),
                type="api",
                name=f"{api['method']} {api['path']}",
                ontology=ONTOLOGY_BY_TYPE["api"],
                metadata=api,
                confidence="observed",
                evidence=[content_hash],
                created_at=now,
            )
            nodes[api_node.node_id] = api_node
            edges[_edge_id(module_node.node_id, api_node.node_id, "IMPLEMENTS")] = KnowledgeEdge(
                edge_id=_edge_id(module_node.node_id, api_node.node_id, "IMPLEMENTS"),
                source=module_node.node_id,
                destination=api_node.node_id,
                relationship="IMPLEMENTS",
                evidence=[content_hash],
            )

    graph_payload = {
        "repository_id": repository_id,
        "nodes": sorted((node.to_payload() | {"created_at": node.created_at.isoformat()} for node in nodes.values()), key=lambda item: item["node_id"]),
        "edges": sorted((edge.to_payload() for edge in edges.values()), key=lambda item: item["edge_id"]),
    }
    ontology_counts = Counter(node.ontology for node in nodes.values())
    confidence_counts = Counter(node.confidence for node in nodes.values())
    return {
        "repository_id": repository_id,
        "repository_name": repository_name,
        "indexed_at": now,
        "incremental": bool(payload.get("incremental", True)),
        "graph_hash": stable_hash(graph_payload),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "ontology_counts": dict(sorted(ontology_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "changed_paths": changed_paths,
        "nodes": [node.to_payload() for node in nodes.values()],
        "edges": [edge.to_payload() for edge in edges.values()],
        "events": ["REPOSITORY_INDEXED", "GRAPH_UPDATED"],
    }


def base_knowledge_graph() -> dict[str, Any]:
    payload = {
        "repository_id": "arceus-reference",
        "repository_name": "Arceus Reference Graph",
        "repository_url": None,
        "default_branch": "main",
        "incremental": False,
        "files": [
            {
                "path": "README.md",
                "language": "markdown",
                "content": "# Arceus Code\nAI engineering organization with missions, policies, evidence, and knowledge.",
            },
            {
                "path": "services/auth/main.py",
                "language": "python",
                "content": "@router.post('/api/v1/auth/login')\ndef login():\n    pass\n",
            },
            {
                "path": "docker-compose.yml",
                "language": "yaml",
                "content": "services:\n  redis:\n    image: redis\n  postgres:\n    image: postgres\n",
            },
        ],
    }
    return index_repository(payload)


def search_graph(query: str, graph: dict[str, Any] | None = None, limit: int = 10) -> dict[str, Any]:
    graph = graph or base_knowledge_graph()
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_./:-]+", query)]
    scored: list[tuple[int, dict[str, Any]]] = []
    for node in graph["nodes"]:
        haystack = " ".join([node["name"], node["type"], node["ontology"], str(node.get("metadata", {}))]).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, node))
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    results = [node for _, node in scored[:limit]]
    result_ids = {node["node_id"] for node in results}
    related_edges = [edge for edge in graph["edges"] if edge["source"] in result_ids or edge["destination"] in result_ids]
    return {"query": query, "strategy": ["keyword", "graph_adjacency", "confidence_ranking"], "results": results, "related_edges": related_edges[: limit * 2]}


def get_node(node_id: str, graph: dict[str, Any] | None = None) -> dict[str, Any] | None:
    graph = graph or base_knowledge_graph()
    for node in graph["nodes"]:
        if node["node_id"] == node_id:
            return node
    return None


def analyze_impact(changed_entity: str, graph: dict[str, Any] | None = None) -> dict[str, Any]:
    graph = graph or base_knowledge_graph()
    search = search_graph(changed_entity, graph=graph, limit=20)
    affected = {node["node_id"]: node for node in search["results"]}
    affected_edges: list[dict[str, Any]] = []
    frontier = set(affected)
    for edge in graph["edges"]:
        if edge["source"] in frontier or edge["destination"] in frontier:
            affected_edges.append(edge)
            for node in graph["nodes"]:
                if node["node_id"] in {edge["source"], edge["destination"]}:
                    affected.setdefault(node["node_id"], node)
    node_types = Counter(node["type"] for node in affected.values())
    risk_level = "high" if node_types.get("api", 0) or node_types.get("database", 0) else "medium" if len(affected) > 4 else "low"
    verification_plan = ["run_unit_tests", "run_static_analysis"]
    if node_types.get("api", 0):
        verification_plan.append("run_api_contract_tests")
    if node_types.get("database", 0):
        verification_plan.append("verify_database_migration")
    if risk_level == "high":
        verification_plan.append("require_human_architecture_review")
    migration_notes = []
    if node_types.get("database", 0):
        migration_notes.append("prepare_forward_and_rollback_database_migration")
    if node_types.get("api", 0):
        migration_notes.append("notify_or_validate_external_api_consumers")
    return {
        "changed_entity": changed_entity,
        "risk_level": risk_level,
        "affected_nodes": list(affected.values()),
        "affected_edges": affected_edges,
        "verification_plan": verification_plan,
        "migration_notes": migration_notes,
        "confidence": "observed" if affected else "hypothesized",
    }
