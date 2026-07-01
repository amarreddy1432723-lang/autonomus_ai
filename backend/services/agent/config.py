import os

from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("AGENT_DATABASE_URL", os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"))
    AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8003"))

    # ── LLM Provider ──────────────────────────────────────────
    # Supported: autonomus | openai | anthropic | google | groq | ollama | custom | mock
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    # Model name for the selected provider (e.g. autonomus-ai-v1, gpt-4o-mini)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Per-role model overrides (optional — falls back to LLM_MODEL if empty)
    APPROVAL_LLM_MODEL: Optional[str] = os.getenv("APPROVAL_LLM_MODEL")     # stronger model for risk decisions
    EXTRACTION_LLM_MODEL: Optional[str] = os.getenv("EXTRACTION_LLM_MODEL")   # cheaper model for memory extraction
    FALLBACK_LLM_PROVIDER: Optional[str] = os.getenv("FALLBACK_LLM_PROVIDER")
    FALLBACK_LLM_MODEL: Optional[str] = os.getenv("FALLBACK_LLM_MODEL")

    # ── Embedding Provider ────────────────────────────────────
    # Supported: openai | google | ollama | huggingface | mock
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "mock")
    # Embedding model name (e.g. text-embedding-3-small, nomic-embed-text)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # ── API Keys ──────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "mock-openai-key-for-local-dev-only")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")      # for Claude models
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")         # for Gemini chat + embeddings
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")           # for Groq hosted inference
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "mock-serper-key-for-local-dev-only")

    # ── Phase 4 Memory System ───────────────────────────────────
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    SHORT_TERM_MEMORY_TTL_SECONDS: int = int(os.getenv("SHORT_TERM_MEMORY_TTL_SECONDS", "86400"))
    SHORT_TERM_MEMORY_MAX_EVENTS: int = int(os.getenv("SHORT_TERM_MEMORY_MAX_EVENTS", "50"))
    SHORT_TERM_MEMORY_COMPRESS_AT: int = int(os.getenv("SHORT_TERM_MEMORY_COMPRESS_AT", "45"))

    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_HOST: Optional[str] = os.getenv("PINECONE_HOST")
    PINECONE_INDEX: Optional[str] = os.getenv("PINECONE_INDEX")

    NEO4J_URI: Optional[str] = os.getenv("NEO4J_URI")
    NEO4J_USERNAME: Optional[str] = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD: Optional[str] = os.getenv("NEO4J_PASSWORD")

    # ── Local / Custom Inference ──────────────────────────────
    # Base URL for Ollama (default) or any OpenAI-compatible server (vLLM, LM Studio, Jan)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")           # only needed for provider=custom
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "not-needed")              # only needed for provider=custom
    AUTONOMUS_LLM_BASE_URL: Optional[str] = os.getenv("AUTONOMUS_LLM_BASE_URL")
    AUTONOMUS_LLM_API_KEY: str = os.getenv("AUTONOMUS_LLM_API_KEY", os.getenv("LLM_API_KEY", "not-needed"))

    # ── Files / object storage ───────────────────────────────
    FILE_STORAGE_PROVIDER: str = os.getenv("FILE_STORAGE_PROVIDER", "local")  # local | s3
    FILE_STORAGE_LOCAL_DIR: str = os.getenv("FILE_STORAGE_LOCAL_DIR", "uploads")
    S3_ENDPOINT_URL: Optional[str] = os.getenv("S3_ENDPOINT_URL")
    S3_BUCKET: Optional[str] = os.getenv("S3_BUCKET")
    S3_ACCESS_KEY_ID: Optional[str] = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: Optional[str] = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_REGION: str = os.getenv("S3_REGION", "auto")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
