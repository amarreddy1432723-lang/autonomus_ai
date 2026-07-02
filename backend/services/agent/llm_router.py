"""
LLM Router — Centralized provider-agnostic model selector.

Configure in .env:
  LLM_PROVIDER         = autonomus | openai | anthropic | google | groq | ollama | custom | mock
  LLM_MODEL            = autonomus-ai-v1 | gpt-4o-mini | claude-3-5-haiku-20241022 | etc.

Per-role overrides (optional — fallback to LLM_MODEL if unset):
  APPROVAL_LLM_MODEL   = stronger model for risk-gated decisions
  EXTRACTION_LLM_MODEL = cheaper model for memory extraction

Embedding config:
  EMBEDDING_PROVIDER   = openai | google | ollama | huggingface | mock
  EMBEDDING_MODEL      = text-embedding-3-small | nomic-embed-text | mxbai-embed-large | etc.
"""

from langchain_core.language_models import BaseChatModel
from .config import settings

# ─────────────────────────────────────────────────────────────
#  Chat / Reasoning LLM
# ─────────────────────────────────────────────────────────────

def get_chat_llm(role: str = "default", provider: str | None = None, model: str | None = None) -> BaseChatModel:
    """
    Returns the appropriate chat LLM for a given role, or overrides with client-specified provider and model.

    Roles:
      'reasoning'  — brain.py, reflection.py, proactive.py
      'planning'   — planner.py
      'extraction' — memory_agent.py (entity/preference extraction)
      'approval'   — approval.py (risk assessment)
      'default'    — fallback for any uncategorised use

    Provider priority for each call:
      1. Explicit provider/model parameters passed to this function
      2. Read LLM_PROVIDER from .env
      3. Read role-specific model override (APPROVAL_LLM_MODEL, EXTRACTION_LLM_MODEL)
      4. Fallback to LLM_MODEL
      5. Ultimate fallback: MockChatOpenAI for local dev
    """
    is_mock = (
        not settings.OPENAI_API_KEY
        or settings.OPENAI_API_KEY == "mock-openai-key-for-local-dev-only"
    )

    if not provider:
        provider = getattr(settings, "LLM_PROVIDER", "").strip().lower()
    else:
        provider = provider.strip().lower()

    if not model:
        base_model = getattr(settings, "LLM_MODEL", "gpt-4o-mini").strip()

        # Per-role model overrides
        if role == "approval":
            override = getattr(settings, "APPROVAL_LLM_MODEL", None)
            model = (override or base_model).strip()
        elif role == "extraction":
            override = getattr(settings, "EXTRACTION_LLM_MODEL", None)
            model = (override or base_model).strip()
        else:
            model = base_model
    else:
        model = model.strip()

    # If no explicit provider is set, infer from existing key availability
    if not provider:
        if not is_mock:
            provider = "openai"
        else:
            provider = "mock"

    try:
        # ── Autonomus AI (own OpenAI-compatible model endpoint) ──
        if provider in {"autonomus", "autonomous"}:
            from .training_service import get_active_finetuned_model
            active_ft_model = get_active_finetuned_model()
            if active_ft_model:
                from langchain_openai import ChatOpenAI
                openai_key = getattr(settings, "OPENAI_API_KEY", "")
                return ChatOpenAI(
                    model=active_ft_model,
                    openai_api_key=openai_key,
                    temperature=0.2,
                )

            from langchain_openai import ChatOpenAI
            llm_base_url = (
                getattr(settings, "AUTONOMUS_LLM_BASE_URL", None)
                or getattr(settings, "LLM_BASE_URL", None)
            )
            if not llm_base_url:
                fallback_provider = getattr(settings, "FALLBACK_LLM_PROVIDER", None)
                fallback_model = getattr(settings, "FALLBACK_LLM_MODEL", None)
                if fallback_provider:
                    return get_chat_llm(role=role, provider=fallback_provider, model=fallback_model)
                if getattr(settings, "GROQ_API_KEY", None):
                    return get_chat_llm(role=role, provider="groq", model="llama-3.3-70b-versatile")
                if not is_mock:
                    return get_chat_llm(role=role, provider="openai", model="gpt-4o-mini")
                from .mock_llm import MockChatOpenAI
                return MockChatOpenAI()
            llm_api_key = getattr(settings, "AUTONOMUS_LLM_API_KEY", None) or getattr(settings, "LLM_API_KEY", "not-needed")
            return ChatOpenAI(
                model=model or "autonomus-ai-v1",
                base_url=llm_base_url,
                api_key=llm_api_key,
                temperature=0.2,
            )

        # ── OpenAI ────────────────────────────────────────────────
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model or "gpt-4o-mini",
                temperature=0.2,
                api_key=settings.OPENAI_API_KEY,
            )

        # ── Anthropic (Claude) ────────────────────────────────────
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "")
            return ChatAnthropic(
                model=model or "claude-3-5-haiku-20241022",
                anthropic_api_key=anthropic_key,
                temperature=0.2,
            )

        # ── Google Gemini ─────────────────────────────────────────
        elif provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            google_key = getattr(settings, "GOOGLE_API_KEY", "")
            return ChatGoogleGenerativeAI(
                model=model or "gemini-1.5-flash",
                google_api_key=google_key,
                temperature=0.2,
            )

        # ── Groq (ultra-fast hosted inference) ───────────────────
        elif provider == "groq":
            from langchain_groq import ChatGroq
            groq_key = getattr(settings, "GROQ_API_KEY", "")
            return ChatGroq(
                model=model or "llama-3.1-70b-versatile",
                groq_api_key=groq_key,
                temperature=0.2,
            )

        # ── Ollama (local self-hosted) ────────────────────────────
        elif provider == "ollama":
            from langchain_ollama import ChatOllama
            base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOllama(
                model=model or "llama3.1:8b",
                base_url=base_url,
                temperature=0.2,
            )

        # ── Custom / vLLM / LM Studio (OpenAI-compatible) ────────
        elif provider == "custom":
            from langchain_openai import ChatOpenAI
            llm_base_url = getattr(settings, "LLM_BASE_URL", "http://localhost:8000/v1")
            llm_api_key = getattr(settings, "LLM_API_KEY", "not-needed")
            return ChatOpenAI(
                model=model or "autonomus-ai-v1",
                base_url=llm_base_url,
                api_key=llm_api_key,
                temperature=0.2,
            )
    except ImportError as exc:
        print(f"[LLM Router] Provider '{provider}' is not installed ({exc}). Falling back to mock LLM.")

    # ── Mock (local dev, no API keys, or missing optional provider package) ──
    from .mock_llm import MockChatOpenAI
    return MockChatOpenAI()


# ─────────────────────────────────────────────────────────────
#  Embedding Model
# ─────────────────────────────────────────────────────────────

def get_embedding_vector(text: str) -> list[float]:
    """
    Returns a float embedding vector for the given text.

    Configure via .env:
      EMBEDDING_PROVIDER = openai | google | ollama | huggingface | mock
      EMBEDDING_MODEL    = text-embedding-3-small | nomic-embed-text | etc.

    Dimension guide:
      openai / text-embedding-ada-002    → 1536 dims
      openai / text-embedding-3-small    → 1536 dims
      openai / text-embedding-3-large    → 3072 dims
      google / text-embedding-004        → 768  dims
      ollama / nomic-embed-text          → 768  dims
      ollama / mxbai-embed-large         → 1024 dims
      huggingface / all-MiniLM-L6-v2    → 384  dims
      mock                               → 1536 dims (seeded random, deterministic)

    ⚠️  Changing embedding providers requires:
        1. A database migration to update vector(N) column size
        2. Re-embedding all existing Memory rows
    """
    is_mock = (
        not settings.OPENAI_API_KEY
        or settings.OPENAI_API_KEY == "mock-openai-key-for-local-dev-only"
    )

    emb_provider = getattr(settings, "EMBEDDING_PROVIDER", "").strip().lower()
    emb_model = getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small").strip()

    if not emb_provider:
        emb_provider = "mock" if is_mock else "openai"

    # ── OpenAI ────────────────────────────────────────────────
    if emb_provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text,
            model=emb_model or "text-embedding-3-small",
        )
        return response.data[0].embedding

    # ── Google Gemini ─────────────────────────────────────────
    elif emb_provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        google_key = getattr(settings, "GOOGLE_API_KEY", "")
        embedder = GoogleGenerativeAIEmbeddings(
            model=emb_model or "models/text-embedding-004",
            google_api_key=google_key,
        )
        return embedder.embed_query(text)

    # ── Ollama (local) ────────────────────────────────────────
    elif emb_provider == "ollama":
        import httpx
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        resp = httpx.post(
            f"{base_url}/api/embeddings",
            json={"model": emb_model or "nomic-embed-text", "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    # ── HuggingFace sentence-transformers (local) ─────────────
    elif emb_provider == "huggingface":
        from sentence_transformers import SentenceTransformer
        encoder = SentenceTransformer(emb_model or "all-MiniLM-L6-v2")
        return encoder.encode(text).tolist()

    # ── Mock / deterministic random (local dev) ───────────────
    else:
        import random
        import hashlib
        # Deterministic seed from text content so same text → same vector
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        random.seed(seed)
        return [random.uniform(-1.0, 1.0) for _ in range(1536)]
