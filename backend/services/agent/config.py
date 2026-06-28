from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"
    AGENT_PORT: int = 8006

    # ── LLM Provider ──────────────────────────────────────────
    # Supported: openai | anthropic | google | groq | ollama | custom | mock
    LLM_PROVIDER: str = "mock"
    # Model name for the selected provider (e.g. gpt-4o-mini, claude-3-5-haiku-20241022)
    LLM_MODEL: str = "gpt-4o-mini"

    # Per-role model overrides (optional — falls back to LLM_MODEL if empty)
    APPROVAL_LLM_MODEL: Optional[str] = None     # stronger model for risk decisions
    EXTRACTION_LLM_MODEL: Optional[str] = None   # cheaper model for memory extraction

    # ── Embedding Provider ────────────────────────────────────
    # Supported: openai | google | ollama | huggingface | mock
    EMBEDDING_PROVIDER: str = "mock"
    # Embedding model name (e.g. text-embedding-3-small, nomic-embed-text)
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── API Keys ──────────────────────────────────────────────
    OPENAI_API_KEY: str = "mock-openai-key-for-local-dev-only"
    ANTHROPIC_API_KEY: Optional[str] = None      # for Claude models
    GOOGLE_API_KEY: Optional[str] = None         # for Gemini chat + embeddings
    GROQ_API_KEY: Optional[str] = None           # for Groq hosted inference
    SERPER_API_KEY: str = "mock-serper-key-for-local-dev-only"

    # ── Local / Custom Inference ──────────────────────────────
    # Base URL for Ollama (default) or any OpenAI-compatible server (vLLM, LM Studio, Jan)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_BASE_URL: Optional[str] = None           # only needed for provider=custom
    LLM_API_KEY: str = "not-needed"              # only needed for provider=custom

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
