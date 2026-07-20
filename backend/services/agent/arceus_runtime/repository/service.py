from __future__ import annotations

import ast
import json
import os
import re
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from ..compiler.utils import stable_hash
from .api_schemas import RepositoryArchitectureReport


IGNORED_SEGMENTS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".next",
    ".turbo",
    ".vercel",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "coverage",
    "target",
    "vendor",
}

LANGUAGE_BY_SUFFIX = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".rs": "rust",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".mdx": "markdown",
    ".sql": "sql",
    ".toml": "toml",
    ".xml": "xml",
}

CONFIG_NAMES = {
    "package.json",
    "tsconfig.json",
    "next.config.js",
    "next.config.ts",
    "vite.config.ts",
    "vite.config.js",
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    ".env.example",
    "turbo.json",
    "pnpm-workspace.yaml",
    "nx.json",
    "lerna.json",
}

DOC_NAMES = {"readme.md", "contributing.md", "architecture.md", "adr.md", "license.md", "changelog.md"}

_INDEX_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class SourceFile:
    path: str
    absolute_path: Path
    language: str
    bytes: int
    content_hash: str
    content: str


def _repo_id(root: Path) -> str:
    return "repo_" + stable_hash(str(root.resolve())).replace("sha256:", "")[:24]


def _id(prefix: str, *parts: Any) -> str:
    return prefix + "_" + stable_hash(parts).replace("sha256:", "")[:24]


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _should_skip(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in IGNORED_SEGMENTS for part in rel_parts)


def _language_for(path: Path, content_sample: str = "") -> str:
    suffix = path.suffix.lower()
    if suffix in LANGUAGE_BY_SUFFIX:
        return LANGUAGE_BY_SUFFIX[suffix]
    if path.name.lower() == "dockerfile":
        return "dockerfile"
    if content_sample.startswith("#!/") and "python" in content_sample[:80]:
        return "python"
    if content_sample.startswith("#!/") and ("bash" in content_sample[:80] or "sh" in content_sample[:80]):
        return "shell"
    return "text"


def _read_source_file(path: Path, root: Path, max_file_bytes: int) -> SourceFile | None:
    size = path.stat().st_size
    if size > max_file_bytes:
        return None
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return None
    content = data.decode("utf-8", errors="replace")
    rel = _normalize(str(path.relative_to(root)))
    return SourceFile(
        path=rel,
        absolute_path=path,
        language=_language_for(path, content[:200]),
        bytes=size,
        content_hash=stable_hash(data),
        content=content,
    )


def discover_source_files(root_path: str, *, max_files: int, max_file_bytes: int) -> tuple[Path, list[SourceFile], int]:
    root = Path(root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Repository root does not exist or is not a directory.")

    files: list[SourceFile] = []
    skipped = 0
    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)
        dirnames[:] = [name for name in dirnames if name not in IGNORED_SEGMENTS and not name.startswith(".cache")]
        if _should_skip(current, root):
            skipped += len(filenames)
            continue
        for filename in filenames:
            if len(files) >= max_files:
                skipped += 1
                continue
            path = current / filename
            try:
                source = _read_source_file(path, root, max_file_bytes)
            except OSError:
                skipped += 1
                continue
            if source is None:
                skipped += 1
                continue
            files.append(source)
    return root, files, skipped


def _read_json(root: Path, rel_path: str) -> dict[str, Any]:
    try:
        return json.loads((root / rel_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def detect_package_managers(paths: set[str]) -> list[dict[str, Any]]:
    managers: list[dict[str, Any]] = []
    checks = {
        "npm": ["package-lock.json", "package.json"],
        "pnpm": ["pnpm-lock.yaml", "pnpm-workspace.yaml"],
        "yarn": ["yarn.lock"],
        "pip": ["requirements.txt"],
        "poetry": ["poetry.lock", "pyproject.toml"],
        "cargo": ["Cargo.toml", "Cargo.lock"],
        "go": ["go.mod", "go.sum"],
        "maven": ["pom.xml"],
        "gradle": ["build.gradle", "settings.gradle"],
    }
    lower_paths = {item.lower(): item for item in paths}
    for name, candidates in checks.items():
        found = [lower_paths[item.lower()] for item in candidates if item.lower() in lower_paths]
        if found:
            managers.append({"name": name, "files": sorted(found)})
    return managers


def detect_build_systems(paths: set[str]) -> list[dict[str, Any]]:
    checks = {
        "next": ["next.config.js", "next.config.ts"],
        "vite": ["vite.config.js", "vite.config.ts"],
        "turbo": ["turbo.json"],
        "nx": ["nx.json"],
        "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
        "pytest": ["pytest.ini", "pyproject.toml"],
        "cargo": ["Cargo.toml"],
        "go": ["go.mod"],
        "maven": ["pom.xml"],
        "gradle": ["build.gradle"],
    }
    lower_paths = {item.lower(): item for item in paths}
    systems: list[dict[str, Any]] = []
    for name, candidates in checks.items():
        found = [lower_paths[item.lower()] for item in candidates if item.lower() in lower_paths]
        if found:
            systems.append({"name": name, "files": sorted(found)})
    return systems


def detect_frameworks(root: Path, paths: set[str], files: list[SourceFile]) -> list[dict[str, Any]]:
    evidence: dict[str, set[str]] = defaultdict(set)
    package_json = _read_json(root, "package.json") if "package.json" in paths else {}
    deps = {}
    deps.update(package_json.get("dependencies") or {})
    deps.update(package_json.get("devDependencies") or {})
    dep_names = set(deps)
    framework_deps = {
        "Next.js": {"next"},
        "React": {"react", "react-dom"},
        "Vue": {"vue", "nuxt"},
        "Angular": {"@angular/core"},
        "Express": {"express"},
        "NestJS": {"@nestjs/core"},
    }
    for framework, names in framework_deps.items():
        if dep_names.intersection(names):
            evidence[framework].add("package.json")
    if "pyproject.toml" in paths or "requirements.txt" in paths:
        combined = "\n".join(file.content[:8000] for file in files if PurePosixPath(file.path).name.lower() in {"pyproject.toml", "requirements.txt"})
        lowered = combined.lower()
        if "fastapi" in lowered:
            evidence["FastAPI"].add("pyproject.toml/requirements.txt")
        if "django" in lowered:
            evidence["Django"].add("pyproject.toml/requirements.txt")
    if any(path.startswith("app/") for path in paths) and "next.config.ts" in paths.union({"next.config.js"}):
        evidence["Next.js"].add("app/ directory")
    if any("router." in file.content or "@app." in file.content for file in files if file.language == "python"):
        evidence["FastAPI"].add("route decorators")
    return [
        {"name": name, "confidence": min(1.0, 0.55 + len(items) * 0.2), "evidence": sorted(items)}
        for name, items in sorted(evidence.items())
    ]


def repository_type(paths: set[str], frameworks: list[dict[str, Any]]) -> str:
    if {"pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json"}.intersection(paths):
        return "monorepo"
    if any(path.startswith("backend/") for path in paths) and any(path.startswith("frontend/") for path in paths):
        return "monorepo"
    if any(item["name"] in {"FastAPI", "Express", "NestJS", "Django"} for item in frameworks):
        return "service"
    if {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}.intersection(paths):
        return "application"
    return "library"


def _visibility(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("_") or " private " in f" {stripped} ":
        return "private"
    if " protected " in f" {stripped} ":
        return "protected"
    if " public " in f" {stripped} " or stripped.startswith("export "):
        return "public"
    return "unknown"


def extract_symbols(file: SourceFile) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    content = file.content
    if file.language == "python":
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(_symbol(file, node.name, "class", node.lineno, f"class {node.name}", "unknown"))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(_symbol(file, node.name, "function", node.lineno, f"def {node.name}", "private" if node.name.startswith("_") else "public"))
        except SyntaxError:
            return symbols
    elif file.language in {"typescript", "javascript"}:
        patterns = [
            (r"^\s*export\s+interface\s+([A-Za-z_$][\w$]*)", "interface"),
            (r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", "class"),
            (r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)", "type_alias"),
            (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", "function"),
            (r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=", "variable"),
        ]
        lines = content.splitlines()
        for pattern, kind in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_number = content[: match.start()].count("\n") + 1
                line = lines[line_number - 1] if 0 <= line_number - 1 < len(lines) else ""
                symbols.append(_symbol(file, match.group(1), kind, line_number, line.strip()[:240], _visibility(line)))
    elif file.language == "go":
        for pattern, kind in [(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)", "function"), (r"^\s*type\s+([A-Za-z_]\w*)\s+struct", "class"), (r"^\s*type\s+([A-Za-z_]\w*)\s+interface", "interface")]:
            for match in re.finditer(pattern, content, re.MULTILINE):
                symbols.append(_symbol(file, match.group(1), kind, content[: match.start()].count("\n") + 1, match.group(0), "public" if match.group(1)[:1].isupper() else "private"))
    elif file.language in {"java", "csharp", "rust"}:
        for pattern, kind in [(r"\b(?:class|struct)\s+([A-Za-z_]\w*)", "class"), (r"\binterface\s+([A-Za-z_]\w*)", "interface"), (r"\benum\s+([A-Za-z_]\w*)", "enum"), (r"\bfn\s+([A-Za-z_]\w*)", "function")]:
            for match in re.finditer(pattern, content):
                symbols.append(_symbol(file, match.group(1), kind, content[: match.start()].count("\n") + 1, match.group(0), "unknown"))
    return symbols[:300]


def _symbol(file: SourceFile, name: str, kind: str, line: int, signature: str, visibility: str) -> dict[str, Any]:
    return {
        "id": _id("sym", file.path, name, kind, line),
        "name": name,
        "kind": kind,
        "file": file.path,
        "range": {"start_line": line, "start_column": 1, "end_line": line, "end_column": max(1, len(signature))},
        "signature": signature,
        "visibility": visibility,
        "documentation": None,
    }


def extract_imports(file: SourceFile) -> list[str]:
    content = file.content
    imports: list[str] = []
    if file.language == "python":
        for pattern in (r"^\s*import\s+([\w.]+)", r"^\s*from\s+([\w.]+)\s+import\s+"):
            imports.extend(match.group(1) for match in re.finditer(pattern, content, re.MULTILINE))
    elif file.language in {"typescript", "javascript"}:
        for match in re.finditer(r"\bfrom\s+['\"]([^'\"]+)['\"]|import\(['\"]([^'\"]+)['\"]\)", content):
            imports.append(match.group(1) or match.group(2))
    elif file.language == "go":
        imports.extend(match.group(1) for match in re.finditer(r"import\s+(?:\(\s*)?[`\"]([^`\"]+)[`\"]", content))
    elif file.language in {"java", "csharp"}:
        imports.extend(match.group(1) for match in re.finditer(r"^\s*(?:import|using)\s+([\w.]+)", content, re.MULTILINE))
    elif file.language == "rust":
        imports.extend(match.group(1) for match in re.finditer(r"^\s*use\s+([^;]+);", content, re.MULTILINE))
    return sorted(set(item.strip() for item in imports if item.strip()))[:100]


def detect_tests(files: list[SourceFile], production_paths: set[str]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    for file in files:
        lower = file.path.lower()
        name = PurePosixPath(lower).name
        if not any(marker in lower for marker in ["test", "spec", "__tests__", "tests/"]):
            continue
        stem = re.sub(r"(\.test|\.spec|_test|test_)", "", PurePosixPath(file.path).stem, flags=re.IGNORECASE)
        candidates = [path for path in production_paths if PurePosixPath(path).stem.lower() == stem.lower()]
        if not candidates:
            candidates = [path for path in production_paths if stem.lower() in PurePosixPath(path).stem.lower()][:5]
        kind = "e2e" if "e2e" in lower else "integration" if "integration" in lower else "unit"
        mappings.append({"test_path": file.path, "target_paths": sorted(candidates)[:10], "test_kind": kind, "confidence": 0.82 if candidates else 0.35})
    return mappings


def architecture_report(paths: set[str], frameworks: list[dict[str, Any]], files: list[SourceFile]) -> dict[str, Any]:
    signals: list[str] = []
    modules: set[str] = set()
    top_dirs = {PurePosixPath(path).parts[0] for path in paths if len(PurePosixPath(path).parts) > 1}
    for dirname in sorted(top_dirs):
        if dirname in {"backend", "frontend", "apps", "packages", "services", "src", "docs", "desktop"}:
            modules.add(dirname)
    if {"backend", "frontend"}.issubset(top_dirs) or {"apps", "packages"}.intersection(top_dirs):
        signals.append("Multiple workspace/module roots detected.")
    if any(item["name"] == "FastAPI" for item in frameworks):
        signals.append("FastAPI routes/services detected.")
    if any(item["name"] == "Next.js" for item in frameworks):
        signals.append("Next.js application conventions detected.")
    if any("/routes" in path or path.endswith("routes.py") for path in paths):
        signals.append("Route layer detected.")
    if any("/service" in path or path.endswith("service.py") for path in paths):
        signals.append("Service layer detected.")
    if any("worker" in path.lower() or "celery" in path.lower() for path in paths):
        signals.append("Background worker/runtime components detected.")
    if {"docker-compose.yml", "docker-compose.yaml"}.intersection(paths):
        signals.append("Containerized deployment detected.")

    if {"apps", "packages"}.intersection(top_dirs) or "turbo.json" in paths or "pnpm-workspace.yaml" in paths:
        style = "Monorepo"
        confidence = 0.88
    elif any("events" in path or "queue" in path or "worker" in path for path in paths):
        style = "Event Driven Service Architecture"
        confidence = 0.74
    elif any(item["name"] == "FastAPI" for item in frameworks) and any(item["name"] in {"Next.js", "React"} for item in frameworks):
        style = "Layered Full-Stack Application"
        confidence = 0.82
    elif any("/domain" in path or "/application" in path or "/infrastructure" in path for path in paths):
        style = "Clean Architecture"
        confidence = 0.72
    else:
        style = "Layered Application"
        confidence = 0.58

    risks = []
    if len(files) >= 1900:
        risks.append("Index may be partial because max_files was reached.")
    if not any(path.lower().startswith(("tests/", "test/")) or "test" in path.lower() for path in paths):
        risks.append("Few or no tests detected.")
    if not {"readme.md"}.intersection({path.lower() for path in paths}):
        risks.append("README not detected.")

    recommendations = [
        "Use repository graph retrieval before asking agents to modify shared modules.",
        "Refresh the index after file watcher batches or Git branch changes.",
    ]
    return RepositoryArchitectureReport(
        style=style,
        confidence=confidence,
        signals=signals,
        modules=sorted(modules),
        risks=risks,
        recommendations=recommendations,
    ).model_dump(mode="json")


def _resolve_local_import(source_path: str, import_name: str, indexed_paths: set[str]) -> str | None:
    if not import_name.startswith("."):
        return None
    base = PurePosixPath(source_path).parent
    target = base.joinpath(import_name).as_posix()
    target = re.sub(r"/+", "/", target)
    candidates = []
    for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".py", "/index.ts", "/index.tsx", "/__init__.py"):
        candidates.append(_normalize(target + suffix))
    for candidate in candidates:
        if candidate in indexed_paths:
            return candidate
    return None


def index_repository_path(root_path: str, *, repository_id: str | None = None, max_files: int = 2_000, max_file_bytes: int = 250_000) -> dict[str, Any]:
    root, files, skipped = discover_source_files(root_path, max_files=max_files, max_file_bytes=max_file_bytes)
    paths = {file.path for file in files}
    repo_id = repository_id or _repo_id(root)
    now = datetime.now(timezone.utc)
    language_counts = Counter(file.language for file in files)
    language_bytes = Counter({language: sum(file.bytes for file in files if file.language == language) for language in language_counts})
    total_bytes = sum(file.bytes for file in files) or 1
    language_summary = [
        {"language": language, "file_count": language_counts[language], "bytes": language_bytes[language], "percentage": round(language_bytes[language] / total_bytes, 4)}
        for language in sorted(language_counts)
    ]

    frameworks = detect_frameworks(root, paths, files)
    package_managers = detect_package_managers(paths)
    build_systems = detect_build_systems(paths)
    file_payloads: list[dict[str, Any]] = []
    symbol_payloads: list[dict[str, Any]] = []
    relationship_payloads: list[dict[str, Any]] = []
    production_paths: set[str] = set()

    for file in files:
        imports = extract_imports(file)
        symbols = extract_symbols(file)
        if not any(marker in file.path.lower() for marker in ["test", "spec", "__tests__", "tests/"]):
            production_paths.add(file.path)
        file_payloads.append(
            {
                "path": file.path,
                "language": file.language,
                "kind": _file_kind(file.path, file.language),
                "bytes": file.bytes,
                "content_hash": file.content_hash,
                "imports": imports,
                "symbols": [symbol["name"] for symbol in symbols],
            }
        )
        symbol_payloads.extend(symbols)
        file_node_id = _id("file", repo_id, file.path)
        for item in imports:
            target = _resolve_local_import(file.path, item, paths) or item
            relationship_payloads.append(
                {
                    "id": _id("rel", file.path, "imports", target),
                    "source": file_node_id,
                    "target": _id("file", repo_id, target) if target in paths else target,
                    "kind": "imports",
                    "file": file.path,
                    "evidence": [item],
                }
            )
        for symbol in symbols:
            relationship_payloads.append(
                {
                    "id": _id("rel", file.path, "owns", symbol["id"]),
                    "source": file_node_id,
                    "target": symbol["id"],
                    "kind": "owns",
                    "file": file.path,
                    "evidence": [symbol["signature"]],
                }
            )

    tests = detect_tests(files, production_paths)
    for mapping in tests:
        for target in mapping["target_paths"]:
            relationship_payloads.append(
                {
                    "id": _id("rel", mapping["test_path"], "tests", target),
                    "source": _id("file", repo_id, mapping["test_path"]),
                    "target": _id("file", repo_id, target),
                    "kind": "tests",
                    "file": mapping["test_path"],
                    "evidence": [mapping["test_kind"]],
                }
            )

    config_paths = sorted(path for path in paths if PurePosixPath(path).name.lower() in CONFIG_NAMES or path.startswith(".github/workflows/"))
    documentation_paths = sorted(path for path in paths if PurePosixPath(path).name.lower() in DOC_NAMES or path.startswith("docs/"))
    graph_hash = stable_hash(
        {
            "root": str(root),
            "files": [(file.path, file.content_hash) for file in files],
            "symbols": [(symbol["file"], symbol["name"], symbol["kind"]) for symbol in symbol_payloads],
            "relationships": [(rel["source"], rel["target"], rel["kind"]) for rel in relationship_payloads],
        }
    )
    profile = {
        "id": repo_id,
        "root": str(root),
        "name": root.name,
        "git_repository": (root / ".git").exists(),
        "default_branch": _git_default_branch(root),
        "languages": language_summary,
        "frameworks": frameworks,
        "package_managers": package_managers,
        "build_systems": build_systems,
        "repository_type": repository_type(paths, frameworks),
        "estimated_size": total_bytes,
        "indexed_file_count": len(files),
        "skipped_file_count": skipped,
        "generated_at": now,
        "graph_hash": graph_hash,
    }
    result = {
        "profile": profile,
        "files": file_payloads,
        "symbols": symbol_payloads,
        "relationships": relationship_payloads,
        "tests": tests,
        "documentation_paths": documentation_paths,
        "configuration_paths": config_paths,
        "architecture": architecture_report(paths, frameworks, files),
    }
    _INDEX_CACHE[repo_id] = result
    return result


def _file_kind(path: str, language: str) -> str:
    lower = path.lower()
    name = PurePosixPath(lower).name
    if language == "markdown" or lower.startswith("docs/") or name in DOC_NAMES:
        return "documentation"
    if name in CONFIG_NAMES or lower.startswith(".github/workflows/"):
        return "configuration"
    if any(marker in lower for marker in ["test", "spec", "__tests__", "tests/"]):
        return "test"
    return "source"


def _git_default_branch(root: Path) -> str | None:
    head = root / ".git" / "HEAD"
    try:
        content = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    match = re.match(r"ref:\s+refs/heads/(.+)", content)
    return match.group(1) if match else None


def get_index(repository_id: str) -> dict[str, Any] | None:
    return _INDEX_CACHE.get(repository_id)


def search_index(repository_id: str, query: str, *, limit: int = 20) -> dict[str, Any]:
    index = _INDEX_CACHE.get(repository_id)
    if not index:
        return {"repository_id": repository_id, "query": query, "results": []}
    needle = query.lower()
    results: list[dict[str, Any]] = []
    for symbol in index["symbols"]:
        haystack = " ".join([symbol["name"], symbol["kind"], symbol["file"], symbol["signature"]]).lower()
        if needle in haystack:
            results.append({"type": "symbol", "score": 0.95 if needle == symbol["name"].lower() else 0.75, "item": symbol})
    for file in index["files"]:
        haystack = " ".join([file["path"], file["language"], file["kind"], " ".join(file["symbols"])]).lower()
        if needle in haystack:
            results.append({"type": "file", "score": 0.7, "item": file})
    results.sort(key=lambda item: item["score"], reverse=True)
    return {"repository_id": repository_id, "query": query, "results": results[:limit]}


def dependency_graph(repository_id: str) -> dict[str, Any]:
    index = _INDEX_CACHE.get(repository_id)
    if not index:
        return {"repository_id": repository_id, "relationships": [], "cycles": []}
    relationships = [item for item in index["relationships"] if item["kind"] in {"imports", "depends_on"}]
    return {"repository_id": repository_id, "relationships": relationships, "cycles": _find_cycles(relationships)}


def _find_cycles(relationships: list[dict[str, Any]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for rel in relationships:
        target = str(rel["target"])
        if target.startswith("file_"):
            graph[str(rel["source"])].add(target)
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in visiting:
            cycle = stack[stack.index(node) :] if node in stack else stack
            if len(cycle) > 1:
                cycles.append(cycle)
            return
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, set()):
            visit(child, [*stack, child])
        visiting.remove(node)
        visited.add(node)

    for source in list(graph):
        visit(source, [source])
    return cycles[:20]
