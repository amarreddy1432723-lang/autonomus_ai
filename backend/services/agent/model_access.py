from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.models import Integration

from .billing import check_entitlement, get_or_create_subscription
from .config import settings


MODEL_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "supports_byok": True,
        "supports_zero_retention_contract": True,
    },
    "anthropic": {
        "label": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "supports_byok": True,
        "supports_zero_retention_contract": True,
    },
    "google": {
        "label": "Google Gemini",
        "env_key": "GOOGLE_API_KEY",
        "supports_byok": True,
        "supports_zero_retention_contract": False,
    },
    "groq": {
        "label": "Groq",
        "env_key": "GROQ_API_KEY",
        "supports_byok": True,
        "supports_zero_retention_contract": False,
    },
    "custom": {
        "label": "Custom OpenAI-compatible",
        "env_key": "LLM_API_KEY",
        "supports_byok": True,
        "supports_zero_retention_contract": False,
    },
    "autonomus": {
        "label": "Autonomus AI",
        "env_key": "AUTONOMUS_LLM_API_KEY",
        "supports_byok": False,
        "supports_zero_retention_contract": True,
    },
    "ollama": {
        "label": "Ollama / Local",
        "env_key": None,
        "supports_byok": False,
        "supports_zero_retention_contract": True,
    },
}


def _platform_key_configured(provider: str) -> bool:
    meta = MODEL_PROVIDERS.get(provider) or {}
    env_key = meta.get("env_key")
    if provider == "ollama":
        return True
    if not env_key:
        return False
    value = getattr(settings, env_key, None) or os.getenv(env_key)
    if not value:
        return False
    lowered = str(value).lower()
    return "mock" not in lowered and "not-needed" not in lowered


def _byok_integration(db: Session, user_id: UUID, provider: str) -> Integration | None:
    return (
        db.query(Integration)
        .filter(
            Integration.user_id == user_id,
            Integration.provider == f"model:{provider}",
            Integration.status == "active",
        )
        .order_by(Integration.updated_at.desc(), Integration.created_at.desc())
        .first()
    )


def model_access_summary(db: Session, user_id: UUID) -> dict[str, Any]:
    subscription = get_or_create_subscription(db, user_id)
    byok_access = check_entitlement(db, user_id, "code_generation").get("allowed", False)
    providers = []
    for provider, meta in MODEL_PROVIDERS.items():
        byok = _byok_integration(db, user_id, provider)
        providers.append({
            "provider": provider,
            "label": meta["label"],
            "managed_configured": _platform_key_configured(provider),
            "byok_supported": bool(meta.get("supports_byok")),
            "byok_connected": bool(byok),
            "byok_status": byok.status if byok else "not_connected",
            "privacy": {
                "platform_zero_log_personal_data": bool(settings.ZERO_LOG_PERSONAL_DATA),
                "provider_zero_retention_contract_possible": bool(meta.get("supports_zero_retention_contract")),
                "notes": "Enterprise provider contract required for guaranteed zero-data-retention terms.",
            },
            "recommended_use": _recommended_use(provider),
        })
    return {
        "mode": "hybrid_managed_and_byok",
        "plan": subscription.plan_type or "free",
        "byok_allowed": bool(byok_access),
        "managed_access": {
            "enabled": True,
            "billing": "Platform pays provider APIs and deducts credits/plan usage.",
        },
        "byok_access": {
            "enabled": True,
            "billing": "User provider account is charged directly when a BYOK key is connected.",
            "storage_policy": "Do not store raw model API keys in normal database columns; use vault/envelope encryption.",
        },
        "providers": providers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _recommended_use(provider: str) -> list[str]:
    return {
        "openai": ["general reasoning", "tool calling", "fast coding fallback"],
        "anthropic": ["large codebase reasoning", "review", "complex edits"],
        "google": ["long context", "low-cost fast answers", "multimodal later"],
        "groq": ["low-latency chat", "quick interview answers", "cheap extraction"],
        "custom": ["hosted Autonomus AI", "vLLM/LM Studio compatible deployments"],
        "autonomus": ["first-party NEXUS identity", "fine-tuned product behavior"],
        "ollama": ["local/private workloads", "offline development"],
    }.get(provider, ["general use"])


def resolve_model_access_mode(db: Session, user_id: UUID, provider: str | None, model: str | None = None) -> dict[str, Any]:
    normalized = (provider or settings.LLM_PROVIDER or "nexus").strip().lower()
    if normalized == "gemini":
        normalized = "google"
    if normalized == "nexus":
        normalized = "autonomus"
    if normalized not in MODEL_PROVIDERS:
        return {
            "provider": normalized,
            "model": model,
            "mode": "unsupported",
            "allowed": False,
            "reason": "Provider is not registered in model access policy.",
        }

    byok = _byok_integration(db, user_id, normalized)
    if byok:
        return {
            "provider": normalized,
            "model": model,
            "mode": "byok",
            "allowed": True,
            "credential_source": "user_vault_or_integration",
            "integration_id": str(byok.id),
            "billing": "user_provider_account",
        }

    if _platform_key_configured(normalized):
        entitlement = check_entitlement(db, user_id, "code_generation")
        return {
            "provider": normalized,
            "model": model,
            "mode": "managed",
            "allowed": bool(entitlement.get("allowed")),
            "credential_source": "platform",
            "billing": "platform_credits_or_plan",
            "entitlement": entitlement,
        }

    return {
        "provider": normalized,
        "model": model,
        "mode": "not_configured",
        "allowed": False,
        "reason": "No BYOK key or platform key is configured for this provider.",
    }


def register_byok_placeholder(db: Session, user_id: UUID, provider: str, label: str = "") -> dict[str, Any]:
    normalized = provider.strip().lower()
    if normalized == "gemini":
        normalized = "google"
    if normalized not in MODEL_PROVIDERS or not MODEL_PROVIDERS[normalized].get("supports_byok"):
        raise ValueError("Provider does not support BYOK in this workspace.")

    existing = _byok_integration(db, user_id, normalized)
    metadata = {
        "label": label or f"{MODEL_PROVIDERS[normalized]['label']} BYOK",
        "credential_policy": "key_required_in_vault_or_envelope_encryption",
        "raw_key_stored": False,
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        existing.metadata_json = {**(existing.metadata_json or {}), **metadata}
        existing.status = "needs_secret"
        db.commit()
        db.refresh(existing)
        return {"id": str(existing.id), "provider": normalized, "status": existing.status, "metadata": existing.metadata_json}

    integration = Integration(
        user_id=user_id,
        provider=f"model:{normalized}",
        provider_user_id="byok",
        status="needs_secret",
        scopes=["model.generate"],
        metadata_json=metadata,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return {"id": str(integration.id), "provider": normalized, "status": integration.status, "metadata": integration.metadata_json}
