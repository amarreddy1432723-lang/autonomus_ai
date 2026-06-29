import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"
)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL)
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

