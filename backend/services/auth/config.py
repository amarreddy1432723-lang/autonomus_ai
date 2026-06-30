import os

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv(
        "AUTH_DATABASE_URL",
        os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db")
    )
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        os.getenv("JWT_SECRET_KEY", "supersecretkeyforlocaldevelopmentonlychangeinprod!")
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
