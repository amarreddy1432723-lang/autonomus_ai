from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError

from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import AuditLog, FileReference, Subscription, UserSession


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    session.query(FileReference).filter(FileReference.user_id == USER_ID, FileReference.filename.like("phase6-test%")).delete()
    session.query(Subscription).filter(Subscription.user_id == USER_ID, Subscription.provider_subscription_id.like("phase6-test%")).delete()
    session.query(UserSession).filter(UserSession.user_id == USER_ID, UserSession.token_hash.like("phase6-test%")).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(FileReference).filter(FileReference.user_id == USER_ID, FileReference.filename.like("phase6-test%")).delete()
        session.query(Subscription).filter(Subscription.user_id == USER_ID, Subscription.provider_subscription_id.like("phase6-test%")).delete()
        session.query(UserSession).filter(UserSession.user_id == USER_ID, UserSession.token_hash.like("phase6-test%")).delete()
        session.commit()
        session.close()


def test_phase6_core_database_tables_persist_user_scoped_records(db):
    session_record = UserSession(
        user_id=USER_ID,
        token_hash="phase6-test-token",
        device_info={"platform": "pytest"},
        ip_address="127.0.0.1",
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    subscription = Subscription(
        user_id=USER_ID,
        plan_type="pro",
        status="active",
        provider="pytest",
        provider_subscription_id="phase6-test-subscription",
        entitlements={"memory": "enabled"},
    )
    file_reference = FileReference(
        user_id=USER_ID,
        owner_type="memory",
        storage_provider="local",
        object_key="phase6/test-object.txt",
        filename="phase6-test-object.txt",
        content_type="text/plain",
        size_bytes=128,
        checksum_sha256="0" * 64,
    )

    db.add_all([session_record, subscription, file_reference])
    db.commit()

    assert db.query(UserSession).filter_by(user_id=USER_ID, token_hash="phase6-test-token").count() == 1
    assert db.query(Subscription).filter_by(user_id=USER_ID, provider_subscription_id="phase6-test-subscription").count() == 1
    assert db.query(FileReference).filter_by(user_id=USER_ID, filename="phase6-test-object.txt").count() == 1


def test_audit_logs_are_append_only():
    session = SessionLocal()
    verify_default_user(session)
    audit = AuditLog(
        user_id=USER_ID,
        event_type="phase6_test",
        actor_type="system",
        action="verify append-only trigger",
    )
    session.add(audit)
    session.flush()

    audit.action = "mutation should fail"
    with pytest.raises(DBAPIError):
        session.flush()

    session.rollback()
    session.close()
