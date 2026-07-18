from __future__ import annotations

from services.shared.arceus_core_models import ArceusProviderProfile


AUTH_FAILURE_MARKERS = ("credential", "authentication", "unauthorized", "api key", "inline secret")
TRANSIENT_FAILURE_MARKERS = ("timeout", "rate limit", "temporarily", "503", "502", "connection")


def record_provider_success(provider: ArceusProviderProfile) -> None:
    provider.health_status = "healthy"
    provider.circuit_state = "closed"
    provider.version = int(provider.version or 1) + 1


def record_provider_failure(provider: ArceusProviderProfile, message: str) -> None:
    normalized = message.lower()
    if any(marker in normalized for marker in AUTH_FAILURE_MARKERS):
        provider.health_status = "misconfigured"
        provider.circuit_state = "open"
    elif "rate limit" in normalized:
        provider.health_status = "rate_limited"
        provider.circuit_state = "half_open"
    elif any(marker in normalized for marker in TRANSIENT_FAILURE_MARKERS):
        provider.health_status = "degraded"
        provider.circuit_state = "half_open"
    else:
        provider.health_status = "degraded"
    provider.version = int(provider.version or 1) + 1
