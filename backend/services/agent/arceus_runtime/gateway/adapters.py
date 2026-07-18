from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from services.shared.arceus_core_models import ArceusModelProfile, ArceusProviderProfile

from .api_schemas import AIExecutionRequest
from .prompting import CompiledPrompt
from .service import estimate_cost, stable_hash


@dataclass(frozen=True)
class ProviderResponse:
    provider_key: str
    model_key: str
    output: dict[str, Any] | str | list[Any]
    finish_reason: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: int
    cost_usd: Any
    raw_response_reference: str | None
    response_hash: str


class ProviderAdapter(Protocol):
    def generate(self, *, provider: ArceusProviderProfile, model: ArceusModelProfile, prompt: CompiledPrompt, request: AIExecutionRequest) -> ProviderResponse:
        ...

    def health_check(self, *, provider: ArceusProviderProfile) -> dict[str, Any]:
        ...


class DeterministicLocalAdapter:
    def generate(self, *, provider: ArceusProviderProfile, model: ArceusModelProfile, prompt: CompiledPrompt, request: AIExecutionRequest) -> ProviderResponse:
        started = time.perf_counter()
        if request.required_output_schema:
            output: dict[str, Any] | str | list[Any] = {
                "status": "completed",
                "task_type": request.task_type,
                "summary": f"Local deterministic gateway response for: {request.objective}",
                "evidence": [{"kind": "routing", "hash": prompt.content_hash}],
            }
        else:
            output = f"Local deterministic gateway response for: {request.objective}"
        latency_ms = int((time.perf_counter() - started) * 1000)
        input_tokens = max(1, len(prompt.system + prompt.user) // 4)
        output_tokens = max(1, len(str(output)) // 4)
        cost = estimate_cost(model, input_tokens, output_tokens)
        return ProviderResponse(
            provider_key=provider.provider_key,
            model_key=model.model_key,
            output=output,
            finish_reason="stop",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=0,
            latency_ms=latency_ms,
            cost_usd=cost,
            raw_response_reference=None,
            response_hash=stable_hash(output),
        )

    def health_check(self, *, provider: ArceusProviderProfile) -> dict[str, Any]:
        return {"status": "healthy", "provider_key": provider.provider_key, "adapter": "local_deterministic"}


class OpenAICompatibleAdapter:
    def _api_key(self, provider: ArceusProviderProfile) -> str:
        reference = (provider.authentication_reference or "").strip()
        if reference.startswith("env:"):
            return os.getenv(reference.removeprefix("env:"), "")
        if reference.startswith("secret:"):
            return ""
        if reference.startswith("sk-"):
            raise RuntimeError("Provider profile contains an inline secret; use an env or secret reference.")
        return os.getenv("OPENAI_API_KEY", "")

    def generate(self, *, provider: ArceusProviderProfile, model: ArceusModelProfile, prompt: CompiledPrompt, request: AIExecutionRequest) -> ProviderResponse:
        api_key = self._api_key(provider)
        if not api_key:
            raise RuntimeError("Provider credentials are not configured.")
        base_url = os.getenv(f"{provider.provider_key.upper()}_BASE_URL", "https://api.openai.com/v1")
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model.provider_model_name,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": 0 if request.deterministic_required else 0.2,
            "max_tokens": request.maximum_output_tokens or model.maximum_output_tokens,
        }
        if request.required_output_schema and model.supports_structured_output:
            payload["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        output = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or max(1, len(prompt.system + prompt.user) // 4))
        output_tokens = int(usage.get("completion_tokens") or max(1, len(str(output)) // 4))
        cost = estimate_cost(model, input_tokens, output_tokens)
        raw_reference = stable_hash({"provider": provider.provider_key, "id": data.get("id")})
        return ProviderResponse(
            provider_key=provider.provider_key,
            model_key=model.model_key,
            output=output,
            finish_reason=data.get("choices", [{}])[0].get("finish_reason") or "unknown",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=0,
            latency_ms=latency_ms,
            cost_usd=cost,
            raw_response_reference=raw_reference,
            response_hash=stable_hash(output),
        )

    def health_check(self, *, provider: ArceusProviderProfile) -> dict[str, Any]:
        try:
            configured = bool(self._api_key(provider))
        except RuntimeError as exc:
            return {"status": "misconfigured", "reason": str(exc)}
        return {"status": "healthy" if configured else "misconfigured", "provider_key": provider.provider_key}


def adapter_for(provider: ArceusProviderProfile) -> ProviderAdapter:
    adapter_type = (provider.adapter_type or "").lower()
    if adapter_type in {"local", "local_deterministic", "mock"}:
        return DeterministicLocalAdapter()
    if adapter_type in {"openai", "openai_compatible", "custom_openai"}:
        return OpenAICompatibleAdapter()
    raise RuntimeError(f"Unsupported provider adapter: {provider.adapter_type}")
