import os

from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("AGENT_DATABASE_URL", os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgrespassword@localhost:5432/my_ai_db"))
    AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8003"))

    # ── LLM Provider ──────────────────────────────────────────
    # Supported: autonomus | openai | anthropic | google | groq | mistral | openrouter | ollama | custom | mock
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
    MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")       # for Mistral / Devstral / Magistral
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY") # optional unified model marketplace
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "mock-serper-key-for-local-dev-only")
    GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
    GITHUB_APP_ID: Optional[str] = os.getenv("GITHUB_APP_ID")
    GITHUB_APP_PRIVATE_KEY: Optional[str] = os.getenv("GITHUB_APP_PRIVATE_KEY")
    GITHUB_APP_CLIENT_ID: Optional[str] = os.getenv("GITHUB_APP_CLIENT_ID")
    GITHUB_APP_CLIENT_SECRET: Optional[str] = os.getenv("GITHUB_APP_CLIENT_SECRET")
    GITHUB_APP_WEBHOOK_SECRET: Optional[str] = os.getenv("GITHUB_APP_WEBHOOK_SECRET")
    GITHUB_APP_NAME: str = os.getenv("GITHUB_APP_NAME", "Arceus-AI")
    GITHUB_APP_SLUG: Optional[str] = os.getenv("GITHUB_APP_SLUG")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", os.getenv("NEXT_PUBLIC_FRONTEND_URL", "http://localhost:3000"))

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
    CODE_WORKSPACE_LOCAL_DIR: str = os.getenv("CODE_WORKSPACE_LOCAL_DIR", os.path.join("runtime", "code-workspaces"))
    S3_ENDPOINT_URL: Optional[str] = os.getenv("S3_ENDPOINT_URL")
    S3_BUCKET: Optional[str] = os.getenv("S3_BUCKET")
    S3_ACCESS_KEY_ID: Optional[str] = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: Optional[str] = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_REGION: str = os.getenv("S3_REGION", "auto")

    # ── Zero-Knowledge Encryption / Vault ───────────────────
    VAULT_ENABLED: bool = os.getenv("VAULT_ENABLED", "true").lower() == "true"
    ZERO_LOG_PERSONAL_DATA: bool = os.getenv("ZERO_LOG_PERSONAL_DATA", "true").lower() == "true"
    VAULT_KEY_DERIVATION: str = os.getenv("VAULT_KEY_DERIVATION", "pbkdf2")  # pbkdf2 | argon2
    VAULT_PBKDF2_ITERATIONS: int = int(os.getenv("VAULT_PBKDF2_ITERATIONS", "600000"))

    # ── Sandbox Runtime ──────────────────────────────────────
    APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local"))
    SANDBOX_PROVIDER: str = os.getenv("SANDBOX_PROVIDER", "local")
    SANDBOX_DOCKER_IMAGE: str = os.getenv("SANDBOX_DOCKER_IMAGE", "arceus-code-sandbox:local")
    SANDBOX_ALLOW_NETWORK: bool = os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower() == "true"
    SANDBOX_DOCKER_MEMORY: str = os.getenv("SANDBOX_DOCKER_MEMORY", "512m")
    SANDBOX_DOCKER_CPU_PERIOD: int = int(os.getenv("SANDBOX_DOCKER_CPU_PERIOD", "100000"))
    SANDBOX_DOCKER_CPU_QUOTA: int = int(os.getenv("SANDBOX_DOCKER_CPU_QUOTA", "50000"))
    SANDBOX_DOCKER_PIDS_LIMIT: int = int(os.getenv("SANDBOX_DOCKER_PIDS_LIMIT", "64"))
    SANDBOX_DOCKER_CLEANUP_TTL_SECONDS: int = int(os.getenv("SANDBOX_DOCKER_CLEANUP_TTL_SECONDS", "300"))
    E2B_API_KEY: Optional[str] = os.getenv("E2B_API_KEY")
    ALLOW_LOCAL_SANDBOX: bool = os.getenv("ALLOW_LOCAL_SANDBOX", "false").lower() == "true"
    SANDBOX_COMMAND_MAX_OUTPUT_CHARS: int = int(os.getenv("SANDBOX_COMMAND_MAX_OUTPUT_CHARS", "20000"))
    SANDBOX_COMMAND_TIMEOUT_SECONDS: int = int(os.getenv("SANDBOX_COMMAND_TIMEOUT_SECONDS", "120"))
    SANDBOX_INSTALL_TIMEOUT_SECONDS: int = int(os.getenv("SANDBOX_INSTALL_TIMEOUT_SECONDS", "300"))
    AGENT_WORKER_ENABLED: bool = os.getenv("AGENT_WORKER_ENABLED", "true").lower() == "true"
    CELERY_WORKER_ENABLED: bool = os.getenv("CELERY_WORKER_ENABLED", "false").lower() == "true"
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    AGENT_WORKER_POLL_SECONDS: float = float(os.getenv("AGENT_WORKER_POLL_SECONDS", "1.0"))
    AGENT_JOB_TIMEOUT_SECONDS: int = int(os.getenv("AGENT_JOB_TIMEOUT_SECONDS", "900"))
    AGENT_JOB_STALE_SECONDS: int = int(os.getenv("AGENT_JOB_STALE_SECONDS", "600"))
    AGENT_JOB_MAX_RETRIES: int = int(os.getenv("AGENT_JOB_MAX_RETRIES", "3"))
    LOCAL_WORKSPACE_IMPORT_ENABLED: bool = os.getenv("LOCAL_WORKSPACE_IMPORT_ENABLED", "true").lower() == "true"
    LOCAL_WORKSPACE_ALLOWED_ROOTS: str = os.getenv("LOCAL_WORKSPACE_ALLOWED_ROOTS", "")
    LOCAL_WORKSPACE_MAX_FILES: int = int(os.getenv("LOCAL_WORKSPACE_MAX_FILES", "1000"))
    LOCAL_WORKSPACE_MAX_FILE_BYTES: int = int(os.getenv("LOCAL_WORKSPACE_MAX_FILE_BYTES", "1500000"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
