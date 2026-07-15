import json
import socket
from uuid import UUID

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import UserProfile


ADMIN_ID = UUID("00000000-0000-0000-0000-000000000000")


def _db_or_skip():
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"Postgres unavailable for model preference integration test: {exc}")

    db = SessionLocal()
    try:
        verify_default_user(db)
        db.execute(text("SELECT 1"))
        return db
    except OperationalError as exc:
        db.close()
        pytest.skip(f"Postgres unavailable for model preference integration test: {exc}")


def test_local_model_status_reads_ollama_tags(monkeypatch):
    from services.agent import model_local

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "models": [
                    {
                        "name": "qwen2.5-coder:7b",
                        "size": 123,
                        "details": {"family": "qwen2", "parameter_size": "7B", "quantization_level": "Q4_K_M"},
                    }
                ]
            }).encode("utf-8")

    monkeypatch.setattr(model_local.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    result = model_local.list_local_models()

    assert result["running"] is True
    assert result["models"][0]["name"] == "qwen2.5-coder:7b"
    assert result["models"][0]["parameter_size"] == "7B"


def test_model_preferences_persist_in_user_profile():
    from services.agent.model_local import get_model_preferences, update_model_preferences

    db = _db_or_skip()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == ADMIN_ID).first()
        if profile:
            prefs = dict(profile.tool_preferences or {})
            prefs.pop("model_preferences", None)
            prefs.pop("model_preferences_updated_at", None)
            profile.tool_preferences = prefs
            db.commit()

        before = get_model_preferences(db, ADMIN_ID)
        assert before["mode"] == "arceus_local"
        assert before["allow_cloud_fallback"] is False

        updated = update_model_preferences(db, ADMIN_ID, {
            "mode": "provider",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allow_cloud_fallback": True,
            "confirm_before_cloud_transfer": True,
        })

        assert updated["mode"] == "provider"
        assert updated["provider"] == "openai"
        assert updated["model"] == "gpt-4o-mini"
        assert updated["allow_cloud_fallback"] is True
    finally:
        db.close()


def test_arceus_provider_aliases_resolve_to_existing_runtime():
    from services.agent.model_access import resolve_model_access_mode

    db = _db_or_skip()
    try:
        local = resolve_model_access_mode(db, ADMIN_ID, "arceus_local", "qwen2.5-coder:7b")
        cloud = resolve_model_access_mode(db, ADMIN_ID, "arceus_cloud", "Arceus-Code")

        assert local["provider"] == "ollama"
        assert local["allowed"] is True
        assert cloud["provider"] == "autonomus"
        assert cloud["mode"] in {"managed", "not_configured"}
    finally:
        db.close()
