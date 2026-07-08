"""
NEXUS AI model registry.

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
    "nexus-reasoning": {
        "primary": {"provider": "openai", "model": "gpt-4o"},
        "fallback": [
            {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            {"provider": "google", "model": "gemini-2.5-flash"},
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        ],
        "capabilities": ["reasoning", "planning", "code", "analysis", "interview"],
        "auto_update": True,
    },
    "nexus-fast": {
        "primary": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "fallback": [
            {"provider": "openai", "model": "gpt-4o-mini"},
            {"provider": "google", "model": "gemini-2.5-flash"},
        ],
        "capabilities": ["chat", "quick_answer", "extraction", "scheduling"],
        "auto_update": True,
    },
    "nexus-code": {
        "primary": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        "fallback": [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "google", "model": "gemini-2.5-pro"},
        ],
        "capabilities": ["code_generation", "code_review", "debugging"],
        "auto_update": True,
    },
    "nexus-creative": {
        "primary": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        "fallback": [{"provider": "openai", "model": "gpt-4o"}],
        "capabilities": ["design", "writing", "ui_generation"],
        "auto_update": True,
    },
    "nexus-embedding": {
        "primary": {"provider": "openai", "model": "text-embedding-3-small"},
        "fallback": [{"provider": "google", "model": "text-embedding-004"}],
        "capabilities": ["embedding", "semantic_search"],
        "auto_update": True,
    },
}


TASK_ROUTER: dict[str, str] = {
    "chat": "nexus-fast",
    "code_generation": "nexus-code",
    "code_review": "nexus-code",
    "debugging": "nexus-code",
    "planning": "nexus-reasoning",
    "design": "nexus-creative",
    "interview": "nexus-reasoning",
    "research": "nexus-reasoning",
    "extraction": "nexus-fast",
    "scheduling": "nexus-fast",
    "reflection": "nexus-reasoning",
    "meeting_prep": "nexus-fast",
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
                "primary": value["primary"],
                "fallback_count": len(value.get("fallback", [])),
                "capabilities": value.get("capabilities", []),
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
