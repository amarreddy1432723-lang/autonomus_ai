"""
Arceus AI model registry.

The registry gives the app one internal place to choose a model by task type,
track health, and expose transparent status without leaking provider details
into product UX.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from services.shared.models import ModelPerformanceLog


MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "arceus-codex": {
        "primary": {"provider": "openai", "model": "gpt-5.6-sol"},
        "fallback": [
            {"provider": "anthropic", "model": "claude-opus-4-8"},
            {"provider": "anthropic", "model": "claude-sonnet-5"},
            {"provider": "google", "model": "gemini-3.5-flash"},
            {"provider": "mistral", "model": "devstral-2512"},
            {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        ],
        "capabilities": ["code_generation", "code_review", "debugging", "refactor", "agentic_coding"],
        "quality_tier": "frontier",
        "cost_tier": "premium",
        "privacy_tier": "provider_cloud",
        "auto_update": True,
    },
    "arceus-reasoning": {
        "primary": {"provider": "openai", "model": "gpt-5.6-terra"},
        "fallback": [
            {"provider": "anthropic", "model": "claude-fable-5"},
            {"provider": "anthropic", "model": "claude-sonnet-5"},
            {"provider": "google", "model": "gemini-3.1-pro"},
            {"provider": "mistral", "model": "magistral-medium-2509"},
        ],
        "capabilities": ["reasoning", "planning", "analysis", "architecture", "interview"],
        "quality_tier": "frontier",
        "cost_tier": "balanced",
        "privacy_tier": "provider_cloud",
        "auto_update": True,
    },
    "arceus-fast": {
        "primary": {"provider": "openai", "model": "gpt-5.6-luna"},
        "fallback": [
            {"provider": "anthropic", "model": "claude-haiku-4-5"},
            {"provider": "google", "model": "gemini-3.1-flash-lite"},
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
            {"provider": "ollama", "model": "llama3.1:8b"},
        ],
        "capabilities": ["chat", "quick_answer", "extraction", "scheduling", "summarization"],
        "quality_tier": "standard",
        "cost_tier": "efficient",
        "privacy_tier": "hybrid",
        "auto_update": True,
    },
    "arceus-local-code": {
        "primary": {"provider": "ollama", "model": "qwen2.5-coder:7b"},
        "fallback": [
            {"provider": "ollama", "model": "deepseek-coder-v2:16b"},
            {"provider": "ollama", "model": "codellama:13b"},
        ],
        "capabilities": ["private_code_generation", "offline_debugging", "local_refactor"],
        "quality_tier": "local",
        "cost_tier": "free_local",
        "privacy_tier": "local",
        "auto_update": False,
    },
    "arceus-creative": {
        "primary": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "fallback": [
            {"provider": "openai", "model": "gpt-5.6-terra"},
            {"provider": "google", "model": "gemini-3.5-flash"},
        ],
        "capabilities": ["design", "writing", "ui_generation", "product_copy"],
        "quality_tier": "frontier",
        "cost_tier": "balanced",
        "privacy_tier": "provider_cloud",
        "auto_update": True,
    },
    "arceus-embedding": {
        "primary": {"provider": "openai", "model": "text-embedding-3-small"},
        "fallback": [
            {"provider": "google", "model": "text-embedding-004"},
            {"provider": "ollama", "model": "nomic-embed-text"},
        ],
        "capabilities": ["embedding", "semantic_search", "memory_retrieval"],
        "quality_tier": "standard",
        "cost_tier": "efficient",
        "privacy_tier": "hybrid",
        "auto_update": True,
    },
    # Backward-compatible aliases used by existing frontend and stored settings.
    "nexus-code": {
        "alias_of": "arceus-codex",
        "primary": {"provider": "openai", "model": "gpt-5.6-sol"},
        "fallback": [],
        "capabilities": ["code_generation"],
        "auto_update": True,
    },
    "Arceus-Code": {
        "alias_of": "arceus-codex",
        "primary": {"provider": "openai", "model": "gpt-5.6-sol"},
        "fallback": [],
        "capabilities": ["code_generation"],
        "auto_update": True,
    },
    "nexus-reasoning": {
        "alias_of": "arceus-reasoning",
        "primary": {"provider": "openai", "model": "gpt-5.6-terra"},
        "fallback": [],
        "capabilities": ["reasoning"],
        "auto_update": True,
    },
    "nexus-fast": {
        "alias_of": "arceus-fast",
        "primary": {"provider": "openai", "model": "gpt-5.6-luna"},
        "fallback": [],
        "capabilities": ["chat"],
        "auto_update": True,
    },
    "nexus-creative": {
        "alias_of": "arceus-creative",
        "primary": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "fallback": [],
        "capabilities": ["design"],
        "auto_update": True,
    },
    "nexus-embedding": {
        "alias_of": "arceus-embedding",
        "primary": {"provider": "openai", "model": "text-embedding-3-small"},
        "fallback": [],
        "capabilities": ["embedding"],
        "auto_update": True,
    },
}


TASK_ROUTER: dict[str, str] = {
    "chat": "arceus-fast",
    "code_generation": "arceus-codex",
    "code_review": "arceus-codex",
    "debugging": "arceus-codex",
    "refactor": "arceus-codex",
    "agentic_coding": "arceus-codex",
    "planning": "arceus-reasoning",
    "architecture": "arceus-reasoning",
    "design": "arceus-creative",
    "interview": "arceus-reasoning",
    "research": "arceus-reasoning",
    "extraction": "arceus-fast",
    "scheduling": "arceus-fast",
    "reflection": "arceus-reasoning",
    "meeting_prep": "arceus-fast",
    "embedding": "arceus-embedding",
    "semantic_search": "arceus-embedding",
    "local_code": "arceus-local-code",
}


_HEALTH_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class ModelChoice:
    model_key: str
    provider: str
    model: str
    source: str = "registry"


def model_key_for_task(task_type: str | None) -> str:
    return TASK_ROUTER.get((task_type or "chat").strip().lower(), "nexus-fast")


def choose_model(task_type: str | None = None, model_key: str | None = None) -> ModelChoice:
    key = model_key or model_key_for_task(task_type)
    entry = MODEL_REGISTRY.get(key) or MODEL_REGISTRY["nexus-fast"]
    if entry.get("alias_of"):
        key = str(entry["alias_of"])
        entry = MODEL_REGISTRY.get(key) or entry
    selected = entry["primary"]

    health = _HEALTH_CACHE.get(key)
    if health and health.get("status") == "down":
        fallback = next(iter(entry.get("fallback", [])), None)
        if fallback:
            selected = fallback

    return ModelChoice(key, selected["provider"], selected["model"])


def registry_snapshot() -> dict[str, Any]:
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "task_router": TASK_ROUTER,
        "models": {
            key: {
                "alias_of": value.get("alias_of"),
                "primary": value["primary"],
                "fallback_count": len(value.get("fallback", [])),
                "capabilities": value.get("capabilities", []),
                "quality_tier": value.get("quality_tier"),
                "cost_tier": value.get("cost_tier"),
                "privacy_tier": value.get("privacy_tier"),
                "auto_update": bool(value.get("auto_update")),
                "health": _HEALTH_CACHE.get(key, {"status": "unknown"}),
            }
            for key, value in MODEL_REGISTRY.items()
        },
    }


def mark_model_health(model_key: str, status: str, latency_ms: int | None = None, error: str | None = None) -> None:
    _HEALTH_CACHE[model_key] = {
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def health_check_registry() -> dict[str, Any]:
    # Lightweight v1: expose configured models and mark them unknown/available.
    # Provider pinging is intentionally kept out of request flow to avoid slow pages.
    for key in MODEL_REGISTRY:
        _HEALTH_CACHE.setdefault(key, {"status": "available", "checked_at": datetime.now(timezone.utc).isoformat()})
    return registry_snapshot()


def log_model_performance(
    db: Session | None,
    model_key: str,
    provider: str,
    model_name: str,
    task_type: str,
    started_at: float,
    success: bool,
    error_type: str | None = None,
) -> None:
    latency_ms = max(0, int((perf_counter() - started_at) * 1000))
    mark_model_health(model_key, "available" if success else "degraded", latency_ms, error_type)
    if db is None:
        return
    try:
        db.add(ModelPerformanceLog(
            model_key=model_key,
            provider=provider,
            model_name=model_name,
            task_type=task_type,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
        ))
        db.commit()
    except Exception:
        db.rollback()
