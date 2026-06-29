import os

from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv(
        "GOALS_DATABASE_URL",
        os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/my_ai_db")
    )
    JWT_SECRET_KEY: str = os.getenv(
        "GOALS_JWT_SECRET_KEY",
        os.getenv("JWT_SECRET", "your-jwt-secret-key-for-local-dev-only-change-in-prod")
    )
    JWT_ALGORITHM: str = os.getenv("GOALS_JWT_ALGORITHM", os.getenv("JWT_ALGORITHM", "HS256"))
    GOALS_PORT: int = int(os.getenv("GOALS_PORT", "8002"))

    class Config:
        env_prefix = "GOALS_"
        env_file = ".env"
        extra = "ignore"

settings = Settings()
