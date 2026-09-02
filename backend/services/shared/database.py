import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# When running under pytest without a live Postgres, fall back to SQLite so the
# full test suite can be collected and executed without Docker dependencies.
_is_test = bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TEST_DATABASE_URL"))
_default_pg = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"

DATABASE_URL = os.getenv("DATABASE_URL", _default_pg)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

# Use explicit test URL if provided, otherwise auto-fall back for pytest runs
if os.getenv("TEST_DATABASE_URL"):
    DATABASE_URL = os.getenv("TEST_DATABASE_URL")
elif _is_test and DATABASE_URL == _default_pg:
    DATABASE_URL = "sqlite:///./test_arceus.db"

_using_sqlite = DATABASE_URL.startswith("sqlite")

if _using_sqlite:
    from sqlalchemy import event

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        finally:
            cursor.close()
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))}
        if DATABASE_URL.startswith("postgresql+psycopg")
        else {},
        pool_pre_ping=True,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_default_user(db):
    """Ensure the default test user and profile exist in the database."""
    if os.getenv("ALLOW_DEMO_USER", "true").lower() not in {"1", "true", "yes", "on"}:
        return
    from services.shared.models import User, UserProfile
    from uuid import UUID
    default_id = UUID("00000000-0000-0000-0000-000000000000")
    try:
        user = db.query(User).filter(User.id == default_id).first()
        if not user:
            user = User(
                id=default_id,
                email="user@example.com",
                hashed_password="mockpassword",
                name="Default User"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        profile = db.query(UserProfile).filter(UserProfile.user_id == default_id).first()
        if not profile:
            profile = UserProfile(
                user_id=default_id,
                autonomy_level="observer"
            )
            db.add(profile)
            db.commit()
            print("Successfully seeded default test user and profile.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding default test user: {e}")
