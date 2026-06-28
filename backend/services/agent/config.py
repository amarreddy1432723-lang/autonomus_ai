from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"
    OPENAI_API_KEY: str = "mock-openai-key-for-local-dev-only"
    SERPER_API_KEY: str = "mock-serper-key-for-local-dev-only"
    AGENT_PORT: int = 8006
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
