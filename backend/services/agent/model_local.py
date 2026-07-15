from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.models import UserProfile

from .config import settings


MODEL_PREFERENCE_DEFAULTS: dict[str, Any] = {
    "mode": "arceus_local",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "allow_cloud_fallback": False,
    "confirm_before_cloud_transfer": True,
}


def _base_url() -> str:
    return str(getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")


def _ollama_json(path: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def list_local_models() -> dict[str, Any]:
    try:
        data = _ollama_json("/api/tags", timeout=3.0)
        models = [
            {
                "name": item.get("name"),
                "modified_at": item.get("modified_at"),
                "size": item.get("size"),
                "family": ((item.get("details") or {}).get("family")),
                "parameter_size": ((item.get("details") or {}).get("parameter_size")),
                "quantization_level": ((item.get("details") or {}).get("quantization_level")),
            }
            for item in data.get("models", [])
            if item.get("name")
        ]
        return {"running": True, "models": models, "error": None}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"running": False, "models": [], "error": str(exc)}
    except Exception as exc:
        return {"running": False, "models": [], "error": str(exc)}


def get_model_preferences(db: Session, user_id: UUID) -> dict[str, Any]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    preferences = dict(MODEL_PREFERENCE_DEFAULTS)
    if profile:
        stored = (profile.tool_preferences or {}).get("model_preferences") or {}
        preferences.update({key: value for key, value in stored.items() if key in MODEL_PREFERENCE_DEFAULTS})
    return preferences


def update_model_preferences(db: Session, user_id: UUID, updates: dict[str, Any]) -> dict[str, Any]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.flush()

    current = dict(MODEL_PREFERENCE_DEFAULTS)
    current.update((profile.tool_preferences or {}).get("model_preferences") or {})

    clean: dict[str, Any] = {}
    if updates.get("mode") in {"arceus_local", "arceus_cloud", "provider"}:
        clean["mode"] = updates["mode"]
    if updates.get("provider"):
        clean["provider"] = str(updates["provider"]).strip().lower()
    if updates.get("model"):
        clean["model"] = str(updates["model"]).strip()
    if "allow_cloud_fallback" in updates:
        clean["allow_cloud_fallback"] = bool(updates["allow_cloud_fallback"])
    if "confirm_before_cloud_transfer" in updates:
        clean["confirm_before_cloud_transfer"] = bool(updates["confirm_before_cloud_transfer"])

    current.update(clean)
    prefs = dict(profile.tool_preferences or {})
    prefs["model_preferences"] = current
    prefs["model_preferences_updated_at"] = datetime.now(timezone.utc).isoformat()
    profile.tool_preferences = prefs
    db.commit()
    db.refresh(profile)
    return get_model_preferences(db, user_id)


def local_model_status(db: Session, user_id: UUID) -> dict[str, Any]:
    local = list_local_models()
    prefs = get_model_preferences(db, user_id)
    available = [item["name"] for item in local["models"]]
    active_model = prefs.get("model") or settings.LLM_MODEL
    return {
        "provider": "arceus_local",
        "runtime": "ollama",
        "running": local["running"],
        "base_url": _base_url(),
        "active_model": active_model,
        "available_models": available,
        "models": local["models"],
        "requires_api_key": False,
        "supports_offline": True,
        "error": local["error"],
        "setup": {
            "download_url": "https://ollama.com/download",
            "recommended_pull": "ollama pull qwen2.5-coder:7b",
        },
        "preferences": prefs,
    }


def test_local_model(db: Session, user_id: UUID, prompt: str = "Reply with OK.", model: str | None = None) -> dict[str, Any]:
    prefs = get_model_preferences(db, user_id)
    selected_model = model or prefs.get("model") or settings.LLM_MODEL
    try:
        data = _ollama_json(
            "/api/chat",
            {
                "model": selected_model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt[:4000]}],
            },
            timeout=30.0,
        )
        message = data.get("message") or {}
        return {
            "ok": True,
            "provider": "arceus_local",
            "runtime": "ollama",
            "model": selected_model,
            "response": message.get("content") or data.get("response") or "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "arceus_local",
            "runtime": "ollama",
            "model": selected_model,
            "error": str(exc),
            "hint": "Start Ollama and pull a coding model, for example: ollama pull qwen2.5-coder:7b",
        }
