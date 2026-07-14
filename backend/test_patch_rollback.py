import hashlib
import json
import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.agent.code_workspace import apply_patch_payload, get_file_text, rollback_last_apply
from services.agent.file_service import delete_object, put_object, storage_provider
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import CodeProject, CodeSession, FileReference


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


def _create_file(db, session, filename: str, content: str, metadata: dict | None = None) -> FileReference:
    data = content.encode("utf-8")
    record = FileReference(
        user_id=USER_ID,
        owner_type="code_workspace",
        owner_id=session.id,
        storage_provider=storage_provider(),
        bucket="",
        object_key=f"tests/{USER_ID}/rollback/{uuid.uuid4()}/{filename.replace('/', '-')}",
        filename=filename,
        content_type="text/plain",
        size_bytes=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        status="active",
        metadata_json=metadata or {"source": "test"},
    )
    put_object(record.object_key, data, "text/plain")
    db.add(record)
    db.flush()
    return record


def test_mixed_patch_apply_and_rollback_restores_all_operation_types(tmp_path):
    db = SessionLocal()
    created_object_keys: list[str] = []
    project = None
    session = None
    try:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            pytest.skip(f"Postgres is not reachable for rollback stress test: {exc}")
        verify_default_user(db)
        project = CodeProject(user_id=USER_ID, name="rollback-stress", status="active")
        db.add(project)
        db.flush()
        local_root = tmp_path / "local-workspace"
        local_root.mkdir()
        session = CodeSession(
            user_id=USER_ID,
            project_id=project.id,
            title="rollback stress",
            file_ids=[],
            status="active",
            metadata_json={
                "local_workspace_path": str(local_root),
                "activity_log": [],
                "file_tree": [],
                "patch_preview": [],
                "rollback_snapshots": [],
            },
        )
        db.add(session)
        db.flush()

        modify_file = _create_file(db, session, "src/modify.txt", "alpha\nbeta\n", {"role": "modify-original"})
        delete_file = _create_file(db, session, "src/delete.txt", "delete me\n", {"role": "delete-original"})
        rename_file = _create_file(db, session, "src/old-name.txt", "old name\n", {"role": "rename-original"})
        created_object_keys.extend([modify_file.object_key, delete_file.object_key, rename_file.object_key])
        session.file_ids = [str(modify_file.id), str(delete_file.id), str(rename_file.id)]
        project.file_ids = list(session.file_ids)
        db.commit()

        patch_payload = {
            "summary": "Mixed operation rollback stress patch",
            "operations": [
                {
                    "type": "modify",
                    "file_id": str(modify_file.id),
                    "filename": modify_file.filename,
                    "content": "alpha\nbeta changed\n",
                },
                {
                    "type": "create",
                    "filename": "src/new-file.txt",
                    "content": "new file\n",
                },
                {
                    "type": "delete",
                    "file_id": str(delete_file.id),
                    "filename": delete_file.filename,
                },
                {
                    "type": "rename",
                    "file_id": str(rename_file.id),
                    "filename": rename_file.filename,
                    "new_filename": "src/new-name.txt",
                    "content": "renamed content\n",
                },
                {
                    "type": "folder",
                    "filename": "src/generated-folder",
                },
            ],
        }
        session.patch_text = json.dumps(patch_payload)
        db.commit()

        applied = apply_patch_payload(db, USER_ID, session)
        assert len(applied["changed"]) == 5
        assert applied["remaining"] == []
        assert applied["impact"]["created_files"] == ["src/new-file.txt"]
        assert applied["impact"]["deleted_files"] == ["src/delete.txt"]
        assert applied["impact"]["renamed_files"] == [{"from": "src/old-name.txt", "to": "src/new-name.txt"}]
        assert applied["impact"]["folders_created"] == ["src/generated-folder"]

        db.refresh(modify_file)
        db.refresh(delete_file)
        db.refresh(rename_file)
        created_file = (
            db.query(FileReference)
            .filter(FileReference.owner_id == session.id, FileReference.filename == "src/new-file.txt")
            .first()
        )
        assert created_file is not None
        created_object_keys.append(created_file.object_key)
        assert get_file_text(db, USER_ID, modify_file.id) == "alpha\nbeta changed\n"
        assert delete_file.status == "deleted"
        assert rename_file.filename == "src/new-name.txt"
        assert rename_file.metadata_json["role"] == "rename-original"
        assert "last_code_session_id" in rename_file.metadata_json

        rolled_back = rollback_last_apply(db, USER_ID, session)
        assert rolled_back["status"] == "rolled_back"
        restored_operations = {item["operation"] for item in rolled_back["restored"]}
        assert {"modify", "delete", "rename", "remove_created", "folder"}.issubset(restored_operations)

        db.refresh(modify_file)
        db.refresh(delete_file)
        db.refresh(rename_file)
        db.refresh(created_file)
        assert get_file_text(db, USER_ID, modify_file.id) == "alpha\nbeta\n"
        assert delete_file.status == "active"
        assert get_file_text(db, USER_ID, delete_file.id) == "delete me\n"
        assert rename_file.filename == "src/old-name.txt"
        assert rename_file.metadata_json == {"role": "rename-original"}
        assert get_file_text(db, USER_ID, rename_file.id) == "old name\n"
        assert created_file.status == "deleted"
        assert str(created_file.id) not in [str(value) for value in (session.file_ids or [])]
        assert "src/generated-folder" not in (session.metadata_json or {}).get("workspace_folders", [])
    finally:
        if session is not None and getattr(session, "id", None):
            for record in db.query(FileReference).filter(FileReference.owner_id == session.id).all():
                try:
                    delete_object(record.object_key)
                except Exception:
                    pass
                db.delete(record)
            db.delete(session)
        if project is not None and getattr(project, "id", None):
            db.delete(project)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        db.close()
        for key in created_object_keys:
            try:
                delete_object(key)
            except Exception:
                pass
