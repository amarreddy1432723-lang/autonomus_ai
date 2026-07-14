import os
from dataclasses import dataclass
from typing import Any


LOCAL_SECRET_VALUES = {
    "supersecretkeyforlocaldevelopmentonlychangeinprod!",
    "local-dev-field-encryption-key-change-in-prod",
    "mock-openai-key-for-local-dev-only",
    "mock-serper-key-for-local-dev-only",
}


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    severity: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }


def app_environment() -> str:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local")).lower()


def is_production() -> bool:
    return app_environment() in {"prod", "production"}


def _configured(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip() and value not in LOCAL_SECRET_VALUES)


def _check(name: str, ok: bool, severity: str, ok_message: str, fail_message: str) -> ReadinessCheck:
    return ReadinessCheck(
        name=name,
        status="pass" if ok else "fail",
        severity=severity,
        message=ok_message if ok else fail_message,
    )


def production_readiness(service_name: str) -> dict[str, Any]:
    env = app_environment()
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "mock").lower()
    allow_dev_auth = os.getenv("ALLOW_DEV_AUTH_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}
    allow_demo_user = os.getenv("ALLOW_DEMO_USER", "true").lower() in {"1", "true", "yes", "on"}
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    clerk_configured = bool(os.getenv("CLERK_ISSUER") or os.getenv("CLERK_JWKS_URL") or os.getenv("CLERK_SECRET_KEY"))

    checks = [
        _check(
            "app_environment",
            env in {"staging", "prod", "production"},
            "warning",
            f"APP_ENV is set to {env}.",
            "APP_ENV is local/dev; set APP_ENV=production for live users.",
        ),
        _check(
            "jwt_secret",
            _configured("JWT_SECRET") or _configured("JWT_SECRET_KEY"),
            "critical",
            "JWT secret is configured.",
            "Set a strong JWT_SECRET outside the repository.",
        ),
        _check(
            "field_encryption",
            _configured("APP_ENCRYPTION_KEY") or _configured("FIELD_ENCRYPTION_KEY"),
            "critical",
            "Field encryption key is configured.",
            "Set APP_ENCRYPTION_KEY or FIELD_ENCRYPTION_KEY for encrypted tokens/secrets.",
        ),
        _check(
            "database",
            bool(database_url and "localhost" not in database_url and "postgres:postgrespassword" not in database_url),
            "critical",
            "DATABASE_URL points to a non-local database.",
            "Use managed PostgreSQL for live users; local Docker Postgres is development only.",
        ),
        _check(
            "redis",
            bool(redis_url or os.getenv("REDIS_HOST") not in {None, "", "localhost"}),
            "warning",
            "Redis is configured outside local defaults.",
            "Use managed Redis for live session memory and rate limits.",
        ),
        _check(
            "llm_provider",
            llm_provider not in {"", "mock"},
            "critical",
            f"LLM provider is {llm_provider}.",
            "Configure a real LLM provider before inviting users.",
        ),
        _check(
            "embedding_provider",
            embedding_provider not in {"", "mock"},
            "warning",
            f"Embedding provider is {embedding_provider}.",
            "Configure real embeddings before relying on semantic memory quality.",
        ),
        _check(
            "dev_auth_fallback",
            not allow_dev_auth,
            "critical",
            "x-user-id development auth fallback is disabled.",
            "Set ALLOW_DEV_AUTH_FALLBACK=false in production.",
        ),
        _check(
            "clerk_auth",
            not is_production() or clerk_configured,
            "critical",
            "Clerk auth is configured for production.",
            "Configure CLERK_ISSUER or CLERK_JWKS_URL and disable development auth in production.",
        ),
        _check(
            "demo_user",
            not allow_demo_user,
            "critical",
            "Demo user seeding is disabled.",
            "Set ALLOW_DEMO_USER=false in production.",
        ),
        _check(
            "frontend_urls",
            _configured("NEXT_PUBLIC_AUTH_URL") and _configured("NEXT_PUBLIC_GOALS_URL") and _configured("NEXT_PUBLIC_AGENT_URL"),
            "warning",
            "Frontend service URLs are configured.",
            "Set frontend service URLs for hosted deployment.",
        ),
    ]

    failed = [check for check in checks if check.status == "fail"]
    critical_failed = [check for check in failed if check.severity == "critical"]
    status = "ready" if not failed else "blocked" if critical_failed else "needs_attention"

    return {
        "service": service_name,
        "environment": env,
        "status": status,
        "production_mode": is_production(),
        "checks": [check.as_dict() for check in checks],
        "summary": {
            "total": len(checks),
            "failed": len(failed),
            "critical_failed": len(critical_failed),
        },
    }


def enforce_production_startup(service_name: str) -> None:
    """Fail fast when a production service would boot with unsafe config."""
    if not is_production():
        return
    if os.getenv("ARCEUS_STRICT_PRODUCTION_STARTUP", "true").lower() in {"0", "false", "no"}:
        return
    readiness = production_readiness(service_name)
    critical = [
        check for check in readiness["checks"]
        if check["status"] == "fail" and check["severity"] == "critical"
    ]
    if critical:
        detail = "; ".join(f"{check['name']}: {check['message']}" for check in critical)
        raise RuntimeError(f"{service_name} refused unsafe production startup. {detail}")
