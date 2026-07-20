from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.agent.plugins import (
    list_extensions,
    list_marketplace_plugins,
    sdk_manifest,
    set_plugin_status,
    install_plugin,
    validate_manifest,
)
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Integration


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


def test_plugin_manifest_accepts_part19_nested_schema():
    manifest = validate_manifest({
        "plugin": {
            "id": "acme.sap",
            "name": "SAP Connector",
            "version": "1.0.0",
            "author": "Acme",
            "permissions": ["connectors.invoke", "knowledge.read"],
            "runtime": {"min_version": "2.0.0"},
        },
        "type": "connector",
        "entry": "connectors/sap.py",
        "capabilities": ["sap.quarterly_financial_summary"],
        "signature": "sha256:abc123",
    })

    assert manifest["id"] == "acme.sap"
    assert manifest["type"] == "connector"
    assert manifest["verification"]["verified"] is True
    assert manifest["capabilities"][0]["id"] == "sap.quarterly_financial_summary"


def test_plugin_manifest_rejects_unknown_permissions_and_future_runtime():
    with pytest.raises(HTTPException):
        validate_manifest({"id": "bad", "name": "Bad", "version": "1.0.0", "permissions": ["root"]})

    with pytest.raises(HTTPException):
        validate_manifest({
            "id": "future",
            "name": "Future Runtime",
            "version": "1.0.0",
            "permissions": [],
            "runtime": {"min_version": "99.0.0"},
        })


def test_marketplace_plugins_are_verified_and_sdk_contract_is_stable():
    marketplace = list_marketplace_plugins()
    assert marketplace
    assert all(item["verification"]["verified"] for item in marketplace)

    sdk = sdk_manifest()
    assert "python" in sdk["languages"]
    assert "typescript" in sdk["languages"]
    assert "missions" in sdk["modules"]
    assert "plugins" in sdk["modules"]
    assert sdk["security"]["signature_required_for_execution"] is True


def test_unsigned_plugin_installs_but_cannot_activate_and_verified_plugin_exports_capabilities():
    db = SessionLocal()
    created_ids: list[UUID] = []
    try:
      try:
          db.execute(text("SELECT 1"))
          verify_default_user(db)
      except SQLAlchemyError as exc:
          pytest.skip(f"Database unavailable for plugin platform test: {exc}")

      unsigned = install_plugin(db, USER_ID, {
          "id": "local.unsigned",
          "name": "Unsigned Local Tool",
          "version": "0.1.0",
          "type": "tool",
          "permissions": ["agent:tool"],
          "capabilities": ["local.unsafe_tool"],
      })
      created_ids.append(UUID(unsigned["id"]))
      assert unsigned["status"] == "installed"
      assert unsigned["executable"] is False

      with pytest.raises(HTTPException):
          set_plugin_status(db, USER_ID, UUID(unsigned["id"]), "active")

      verified = install_plugin(db, USER_ID, {
          "id": "local.verified",
          "name": "Verified Local Tool",
          "version": "0.1.0",
          "publisher": "Partner",
          "type": "tool",
          "permissions": ["agent:tool", "events.publish"],
          "capabilities": [{"id": "local.safe_tool", "version": "0.1.0", "kind": "tool", "health": "healthy"}],
          "signature": "sha256:testsignature",
      })
      created_ids.append(UUID(verified["id"]))
      active = set_plugin_status(db, USER_ID, UUID(verified["id"]), "active")
      assert active["executable"] is True

      extensions = list_extensions(db, USER_ID)
      capability_ids = {item["id"] for item in extensions["capabilities"]}
      assert "local.safe_tool" in capability_ids
      assert "local.unsafe_tool" not in capability_ids
    finally:
      try:
          for plugin_id in created_ids:
              row = db.query(Integration).filter(Integration.id == plugin_id).first()
              if row:
                  db.delete(row)
          db.commit()
      except SQLAlchemyError:
          db.rollback()
      finally:
          db.close()
