from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .llm_router import get_chat_llm


@dataclass(frozen=True)
class ToolRequest:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResult:
    text: str | None
    tool_requests: list[ToolRequest] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> ModelResult:
        ...


def _to_langchain_message(message: dict[str, Any]):
    role = str(message.get("role") or message.get("type") or "user").lower()
    content = message.get("content") or message.get("output") or ""
    if role in {"system", "developer"}:
        return SystemMessage(content=str(content))
    if role == "assistant":
        return AIMessage(content=str(content))
    if role in {"tool", "function_call_output"}:
        return ToolMessage(content=str(content), tool_call_id=str(message.get("call_id") or message.get("tool_call_id") or "tool"))
    return HumanMessage(content=str(content))


class LangChainModelProvider:
    """Provider-agnostic adapter over the existing LLM router.

    This keeps today's working LangChain integrations while giving the
    orchestrator one stable interface for OpenAI, Anthropic, Gemini, Groq,
    Autonomus/custom, local, and future providers.
    """

    def __init__(self, provider_name: str, role: str = "default") -> None:
        self.provider_name = provider_name
        self.role = role

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None = None,
    ) -> ModelResult:
        llm = get_chat_llm(role=self.role, provider=self.provider_name, model=model)
        if tools and hasattr(llm, "bind_tools"):
            llm = llm.bind_tools(tools)

        response = await llm.ainvoke([_to_langchain_message(message) for message in messages])
        tool_requests: list[ToolRequest] = []
        for index, call in enumerate(getattr(response, "tool_calls", None) or []):
            args = call.get("args") or call.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            tool_requests.append(ToolRequest(
                call_id=str(call.get("id") or f"call_{index}"),
                name=str(call.get("name") or ""),
                arguments=dict(args or {}),
            ))

        return ModelResult(
            text=str(getattr(response, "content", "") or "") or None,
            tool_requests=tool_requests,
            raw_metadata=dict(getattr(response, "response_metadata", {}) or {}),
        )


class ModelGateway:
    def __init__(self) -> None:
        self.providers: dict[str, ModelProvider] = {
            "autonomus": LangChainModelProvider("autonomus"),
            "nexus": LangChainModelProvider("nexus"),
            "openai": LangChainModelProvider("openai"),
            "anthropic": LangChainModelProvider("anthropic"),
            "google": LangChainModelProvider("google"),
            "gemini": LangChainModelProvider("google"),
            "groq": LangChainModelProvider("groq"),
            "custom": LangChainModelProvider("custom"),
            "ollama": LangChainModelProvider("ollama"),
            "mock": LangChainModelProvider("mock"),
        }

    def get_provider(self, provider_name: str | None) -> ModelProvider:
        key = (provider_name or "nexus").strip().lower()
        provider = self.providers.get(key)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' is not configured")
        return provider


model_gateway = ModelGateway()
