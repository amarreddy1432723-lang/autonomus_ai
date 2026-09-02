"""
Root pytest configuration for the Arceus backend test suite.

When no explicit DATABASE_URL is set, this conftest activates the SQLite
fallback so all tests can run without a live PostgreSQL / Docker instance.

  - Sets PYTEST_CURRENT_TEST so database.py picks up the SQLite path.
  - Creates all tables from SQLAlchemy models at session start.
  - Provides a `db` fixture with rollback-after-test isolation.
  - Seeds the default demo user so auth-dependent tests have a known user.
"""
import os
import pytest

# Force SQLite mode before any service modules are imported.
# database.py reads PYTEST_CURRENT_TEST at import time.
os.environ.setdefault("PYTEST_CURRENT_TEST", "true")
os.environ.setdefault("ALLOW_DEMO_USER", "true")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    """Create all ORM tables in the SQLite test database once per session."""
    from services.shared.database import engine, Base
    # Import all models so they register themselves on Base.metadata
    import services.shared.models  # noqa: F401
    import services.shared.arceus_core_models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield
    # Tear down — drop all tables and dispose engine so file locks are released
    try:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
    except Exception:
        pass
    db_path = "test_arceus.db"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


@pytest.fixture(scope="function")
def db(_create_test_schema):
    """
    Provide a database session with per-test rollback isolation.

    Usage in a test:
        def test_something(db):
            user = User(email="test@example.com", ...)
            db.add(user)
            db.flush()
            ...  # session is rolled back automatically after the test
    """
    from services.shared.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def demo_user(_create_test_schema):
    """Ensure the default demo user exists and return it."""
    from services.shared.database import SessionLocal
    from services.shared.database import verify_default_user
    session = SessionLocal()
    try:
        verify_default_user(session)
        from services.shared.models import User
        from uuid import UUID
        user = session.query(User).filter(
            User.id == UUID("00000000-0000-0000-0000-000000000000")
        ).first()
        return user
    finally:
        session.close()
