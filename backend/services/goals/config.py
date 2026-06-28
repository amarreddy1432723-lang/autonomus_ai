from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/my_ai_db"
    JWT_SECRET_KEY: str = "your-jwt-secret-key-for-local-dev-only-change-in-prod"
    JWT_ALGORITHM: str = "HS256"
    GOALS_PORT: int = 8002

    class Config:
        env_prefix = "GOALS_"
        env_file = ".env"
        extra = "ignore"

settings = Settings()
