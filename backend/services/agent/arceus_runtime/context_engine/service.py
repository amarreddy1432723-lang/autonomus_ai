from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..compiler.utils import stable_hash
from ..repository.service import get_index, index_repository_path
from .api_schemas import Citation, ContextBuildRequest, ContextItem, ContextPackage, IntentAnalysis, ModelContextProfile


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)((?:password|token|secret|api[_-]?key)\s*[:=]\s*)[^\s'\"]+"),
]
_PACKAGE_CACHE: dict[str, ContextPackage] = {}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def redact_sensitive(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", redacted)
    return redacted


def analyze_intent(prompt: str) -> IntentAnalysis:
    lowered = prompt.lower()
    task_type = "question"
    if any(word in lowered for word in ["refactor", "rename", "simplify"]):
        task_type = "refactor"
    elif any(word in lowered for word in ["fix", "bug", "error", "failing", "failure"]):
        task_type = "debug"
    elif any(word in lowered for word in ["test", "coverage", "spec"]):
        task_type = "test"
    elif any(word in lowered for word in ["build", "implement", "create", "add"]):
        task_type = "implementation"
    elif any(word in lowered for word in ["review", "security", "audit"]):
        task_type = "review"

    requested_files = sorted(set(re.findall(r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|json|ya?ml|md|sql)", prompt, re.IGNORECASE)))[:20]
    requested_symbols = sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-zA-Z_][\w]*Service\b|\b[a-zA-Z_][\w]*Controller\b", prompt)))[:20]
    language_words = {
        "python": ["python", "fastapi", "django", ".py"],
        "typescript": ["typescript", "next", "react", ".ts", ".tsx"],
        "javascript": ["javascript", "node", ".js", ".jsx"],
        "go": ["golang", "go.mod", ".go"],
        "rust": ["rust", "cargo", ".rs"],
        "sql": ["sql", "postgres", "database"],
    }
    languages = [language for language, hints in language_words.items() if any(hint in lowered for hint in hints)]
    frameworks = [name for name, hints in {"FastAPI": ["fastapi"], "Next.js": ["next.js", "nextjs", "next "], "React": ["react"], "Stripe": ["stripe"]}.items() if any(hint in lowered for hint in hints)]
    risk_level = "high" if any(word in lowered for word in ["delete", "drop", "production", "security", "payment", "auth", "migration"]) else "medium" if task_type in {"implementation", "refactor"} else "low"
    expected_output = "patch" if task_type in {"implementation", "refactor", "debug", "test"} else "answer"
    keywords = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", lowered)) - {"the", "and", "for", "with", "this", "that", "into", "from"})[:30]
    return IntentAnalysis(
        task_type=task_type,
        requested_files=requested_files,
        requested_symbols=requested_symbols,
        languages=languages,
        frameworks=frameworks,
        risk_level=risk_level,
        expected_output=expected_output,
        keywords=keywords,
    )


def _score_text(text: str, intent: IntentAnalysis, *, base: float, source_weight: float) -> float:
    lowered = text.lower()
    hits = 0
    for keyword in intent.keywords:
        if keyword.lower() in lowered:
            hits += 1
    for symbol in intent.requested_symbols:
        if symbol.lower() in lowered:
            hits += 3
    for path in intent.requested_files:
        if path.lower().replace("\\", "/") in lowered:
            hits += 4
    score = base + min(0.35, hits * 0.035) + source_weight
    return round(min(1.0, score), 4)


def _line_snippet(root: str, path: str, line: int | None = None, *, max_chars: int = 2_400) -> tuple[str, tuple[int, int] | None]:
    try:
        full_path = (Path(root) / path).resolve()
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", None
    if line:
        lines = content.splitlines()
        start = max(1, line - 8)
        end = min(len(lines), line + 18)
        snippet = "\n".join(lines[start - 1 : end])
        return redact_sensitive(snippet[:max_chars]), (start, end)
    return redact_sensitive(content[:max_chars]), (1, min(len(content.splitlines()), 80))


def _repository_candidates(index: dict[str, Any], intent: IntentAnalysis) -> list[ContextItem]:
    profile = index["profile"]
    root = profile["root"]
    candidates: list[ContextItem] = []
    for symbol in index["symbols"]:
        text = f"{symbol['kind']} {symbol['name']} {symbol['file']} {symbol['signature']}"
        score = _score_text(text, intent, base=0.34, source_weight=0.2)
        if score < 0.44 and symbol["file"] not in intent.requested_files:
            continue
        content, lines = _line_snippet(root, symbol["file"], symbol["range"]["start_line"])
        if not content:
            content = symbol["signature"]
        citation = Citation(source="repository", file=symbol["file"], symbol=symbol["name"], lines=lines, reference_id=symbol["id"], confidence=0.86)
        candidates.append(
            ContextItem(
                item_id=symbol["id"],
                source="repository",
                title=f"{symbol['kind']}: {symbol['name']}",
                content=content,
                score=score,
                estimated_tokens=estimate_tokens(content),
                citation=citation,
                metadata={"kind": symbol["kind"], "visibility": symbol["visibility"]},
            )
        )
    for file in index["files"]:
        text = f"{file['path']} {file['language']} {file['kind']} {' '.join(file['symbols'])}"
        score = _score_text(text, intent, base=0.28, source_weight=0.13)
        if file["path"] in intent.requested_files:
            score = max(score, 0.94)
        if score < 0.42 and file["kind"] not in {"documentation", "test", "configuration"}:
            continue
        content, lines = _line_snippet(root, file["path"], None, max_chars=1_800 if file["kind"] != "source" else 2_600)
        if not content:
            continue
        source = "documentation" if file["kind"] == "documentation" else "tests" if file["kind"] == "test" else "repository"
        citation = Citation(source=source, file=file["path"], lines=lines, reference_id=file["content_hash"], confidence=0.78)
        candidates.append(
            ContextItem(
                item_id=f"file:{file['path']}",
                source=source,
                title=file["path"],
                content=content,
                score=score,
                estimated_tokens=estimate_tokens(content),
                citation=citation,
                metadata={"language": file["language"], "kind": file["kind"], "imports": file["imports"]},
            )
        )
    architecture = index["architecture"]
    arch_content = "\n".join(
        [
            f"Architecture style: {architecture['style']} ({architecture['confidence']:.0%} confidence)",
            "Signals: " + ", ".join(architecture["signals"]),
            "Modules: " + ", ".join(architecture["modules"]),
            "Risks: " + ", ".join(architecture["risks"]),
            "Recommendations: " + ", ".join(architecture["recommendations"]),
        ]
    )
    candidates.append(
        ContextItem(
            item_id=f"architecture:{profile['id']}:{profile['graph_hash']}",
            source="architecture",
            title="Repository architecture report",
            content=arch_content,
            score=0.72 if intent.task_type in {"implementation", "refactor", "review"} else 0.55,
            estimated_tokens=estimate_tokens(arch_content),
            citation=Citation(source="architecture", reference_id=profile["graph_hash"], confidence=architecture["confidence"]),
            metadata={"style": architecture["style"]},
        )
    )
    return candidates


def _list_candidates(items: list[str], source: str, intent: IntentAnalysis, *, base: float) -> list[ContextItem]:
    candidates: list[ContextItem] = []
    for index, item in enumerate(items):
        content = redact_sensitive(item.strip())
        if not content:
            continue
        score = _score_text(content, intent, base=base, source_weight=0.05)
        candidates.append(
            ContextItem(
                item_id=f"{source}:{index}:{stable_hash(content).replace('sha256:', '')[:12]}",
                source=source,  # type: ignore[arg-type]
                title=f"{source.replace('_', ' ').title()} {index + 1}",
                content=content,
                score=score,
                estimated_tokens=estimate_tokens(content),
                citation=Citation(source=source, reference_id=f"{source}:{index}", confidence=0.62),  # type: ignore[arg-type]
                metadata={},
            )
        )
    return candidates


def rank_candidates(candidates: list[ContextItem], intent: IntentAnalysis) -> list[ContextItem]:
    source_boost = {
        "mission": 0.18,
        "repository": 0.16,
        "architecture": 0.14,
        "tests": 0.12,
        "documentation": 0.08,
        "memory": 0.07,
        "conversation": 0.05,
        "execution_state": 0.05,
        "git": 0.03,
    }
    reranked: list[ContextItem] = []
    for candidate in candidates:
        adjusted = min(1.0, candidate.score + source_boost.get(candidate.source, 0.0))
        if intent.task_type == "debug" and candidate.source in {"tests", "execution_state", "git"}:
            adjusted = min(1.0, adjusted + 0.08)
        if intent.task_type == "review" and candidate.source in {"architecture", "memory"}:
            adjusted = min(1.0, adjusted + 0.08)
        reranked.append(candidate.model_copy(update={"score": round(adjusted, 4)}))
    return sorted(reranked, key=lambda item: (item.score, -item.estimated_tokens), reverse=True)


def _cache_key(request: ContextBuildRequest, repo_graph_hash: str | None) -> str:
    return stable_hash(
        {
            "mission_id": request.mission_id,
            "prompt": request.prompt,
            "repo": request.repository_id,
            "root": request.root_path,
            "graph_hash": repo_graph_hash,
            "model": request.model.model_profile,
            "max_context": request.model.max_context_tokens,
            "sources": request.include_sources,
            "conversation": request.conversation[-10:],
            "memories": request.memories[-20:],
        }
    )


def _context_budget(model: ModelContextProfile) -> int:
    system_budget = int(model.max_context_tokens * 0.05)
    mission_budget = int(model.max_context_tokens * 0.10)
    safety_budget = int(model.max_context_tokens * 0.03)
    remaining = model.max_context_tokens - model.reserve_output_tokens - system_budget - mission_budget - safety_budget
    return max(1_000, remaining)


def build_context_package(request: ContextBuildRequest) -> tuple[ContextPackage, IntentAnalysis, bool]:
    started = time.perf_counter()
    intent = analyze_intent(request.prompt)
    index = None
    if request.repository_id:
        index = get_index(request.repository_id)
    if index is None and request.root_path:
        index = index_repository_path(request.root_path, repository_id=request.repository_id)
    repo_graph_hash = index["profile"]["graph_hash"] if index else None
    cache_key = _cache_key(request, repo_graph_hash)
    package_id = "ctx_" + cache_key.replace("sha256:", "")[:24]
    if not request.force_rebuild and package_id in _PACKAGE_CACHE:
        return _PACKAGE_CACHE[package_id], intent, True

    candidates: list[ContextItem] = [
        ContextItem(
            item_id=f"mission:{request.mission_id}",
            source="mission",
            title="Current mission request",
            content=redact_sensitive(request.prompt),
            score=1.0,
            estimated_tokens=estimate_tokens(request.prompt),
            citation=Citation(source="mission", reference_id=request.mission_id, confidence=1.0),
            metadata={"task_type": intent.task_type, "risk_level": intent.risk_level},
        )
    ]
    if index:
        candidates.extend(_repository_candidates(index, intent))
    candidates.extend(_list_candidates(request.conversation[-12:], "conversation", intent, base=0.32))
    candidates.extend(_list_candidates(request.memories[-20:], "memory", intent, base=0.38))
    candidates.extend(_list_candidates(request.git_history[-12:], "git", intent, base=0.3))
    candidates.extend(_list_candidates(request.execution_state[-12:], "execution_state", intent, base=0.34))
    if request.include_sources:
        allowed = set(request.include_sources)
        candidates = [item for item in candidates if item.source in allowed or item.source == "mission"]

    ranked = rank_candidates(candidates, intent)
    token_budget = _context_budget(request.model)
    selected: list[ContextItem] = []
    used_tokens = 0
    seen: set[str] = set()
    for item in ranked:
        if item.item_id in seen:
            continue
        if used_tokens + item.estimated_tokens > token_budget and selected:
            continue
        selected.append(item)
        seen.add(item.item_id)
        used_tokens += item.estimated_tokens
        if used_tokens >= token_budget:
            break

    assembled_prompt = assemble_prompt(request, intent, selected)
    citations = [item.citation for item in selected]
    confidence = _confidence(selected, candidates)
    metadata = {
        "retrieval_ms": int((time.perf_counter() - started) * 1000),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "token_budget": token_budget,
        "cache_key": cache_key,
        "repository_id": index["profile"]["id"] if index else request.repository_id,
        "repository_graph_hash": repo_graph_hash,
        "retrieval_sources": sorted(set(item.source for item in selected)),
        "reserved_output_tokens": request.model.reserve_output_tokens,
    }
    package = ContextPackage(
        package_id=package_id,
        mission_id=request.mission_id,
        prompt=assembled_prompt,
        items=selected,
        citations=citations,
        estimated_tokens=estimate_tokens(assembled_prompt),
        confidence=confidence,
        model_profile=request.model.model_profile,
        metadata=metadata,
        generated_at=datetime.now(timezone.utc),
    )
    _PACKAGE_CACHE[package_id] = package
    return package, intent, False


def assemble_prompt(request: ContextBuildRequest, intent: IntentAnalysis, items: list[ContextItem]) -> str:
    sections = [
        "# Mission",
        redact_sensitive(request.prompt),
        "",
        "# Intent",
        f"task_type={intent.task_type}; risk={intent.risk_level}; expected_output={intent.expected_output}",
        "",
        "# Context",
    ]
    for item in items:
        sections.extend(
            [
                f"## [{item.source}] {item.title}",
                f"citation={item.citation.reference_id}; score={item.score}",
                item.content,
                "",
            ]
        )
    sections.append("# Instruction\nUse only the cited context as evidence. If context is missing, ask for expansion instead of inventing details.")
    return "\n".join(sections)


def _confidence(selected: list[ContextItem], candidates: list[ContextItem]) -> float:
    if not selected:
        return 0.0
    average_score = sum(item.score for item in selected) / len(selected)
    source_diversity = len(set(item.source for item in selected)) / max(1, min(6, len(set(item.source for item in candidates))))
    return round(min(1.0, average_score * 0.82 + source_diversity * 0.18), 4)


def expand_context(package_id: str, query: str, additional_tokens: int) -> ContextPackage | None:
    package = _PACKAGE_CACHE.get(package_id)
    if package is None:
        return None
    intent = analyze_intent(query)
    existing_ids = {item.item_id for item in package.items}
    repository_id = package.metadata.get("repository_id")
    index = get_index(repository_id) if repository_id else None
    extra: list[ContextItem] = []
    if index:
        extra = [item for item in rank_candidates(_repository_candidates(index, intent), intent) if item.item_id not in existing_ids]
    used = 0
    additions: list[ContextItem] = []
    for item in extra:
        if used + item.estimated_tokens > additional_tokens:
            continue
        additions.append(item)
        used += item.estimated_tokens
    if not additions:
        return package
    updated_items = [*package.items, *additions]
    updated = package.model_copy(
        update={
            "items": updated_items,
            "citations": [item.citation for item in updated_items],
            "prompt": package.prompt + "\n\n# Expanded Context\n" + "\n\n".join(f"## [{item.source}] {item.title}\n{item.content}" for item in additions),
            "estimated_tokens": package.estimated_tokens + used,
            "metadata": {**package.metadata, "expanded_by": query, "expanded_item_count": len(additions)},
            "generated_at": datetime.now(timezone.utc),
        }
    )
    _PACKAGE_CACHE[package_id] = updated
    return updated


def cache_entries() -> list[dict[str, Any]]:
    return [
        {
            "package_id": package.package_id,
            "mission_id": package.mission_id,
            "model_profile": package.model_profile,
            "repository_id": package.metadata.get("repository_id"),
            "graph_hash": package.metadata.get("repository_graph_hash"),
            "estimated_tokens": package.estimated_tokens,
            "confidence": package.confidence,
            "generated_at": package.generated_at,
        }
        for package in sorted(_PACKAGE_CACHE.values(), key=lambda item: item.generated_at, reverse=True)
    ]


def clear_cache(package_id: str | None = None) -> int:
    if package_id:
        existed = package_id in _PACKAGE_CACHE
        _PACKAGE_CACHE.pop(package_id, None)
        return 1 if existed else 0
    count = len(_PACKAGE_CACHE)
    _PACKAGE_CACHE.clear()
    return count
