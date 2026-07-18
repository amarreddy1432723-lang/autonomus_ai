"""Capability registry for specialists, models, tools, plugins, and humans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id


CapabilityOwner = Literal["ai_specialist", "human", "model", "tool", "plugin", "workflow", "environment", "knowledge_source"]
CapabilityStatus = Literal["available", "degraded", "unavailable", "deprecated"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(slots=True)
class Capability:
    name: str
    category: str
    description: str
    owner_type: CapabilityOwner
    provider: str
    version: str = "1.0.0"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_permissions: list[str] = field(default_factory=list)
    supported_domains: list[str] = field(default_factory=list)
    risk_level: RiskLevel = "low"
    cost_profile: dict[str, Any] = field(default_factory=dict)
    latency_profile: dict[str, Any] = field(default_factory=dict)
    reliability_score: float = 0.8
    status: CapabilityStatus = "available"
    capability_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "owner_type": self.owner_type,
            "provider": self.provider,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_permissions": self.required_permissions,
            "supported_domains": self.supported_domains,
            "risk_level": self.risk_level,
            "cost_profile": self.cost_profile,
            "latency_profile": self.latency_profile,
            "reliability_score": self.reliability_score,
            "status": self.status,
        }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> Capability:
        self._capabilities[capability.capability_id] = capability
        return capability

    def discover(self, *, domains: list[str] | None = None, category: str | None = None, risk_at_most: RiskLevel | None = None) -> list[Capability]:
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        results = [capability for capability in self._capabilities.values() if capability.status == "available"]
        if domains:
            domain_set = set(domains)
            results = [capability for capability in results if domain_set.intersection(capability.supported_domains)]
        if category:
            results = [capability for capability in results if capability.category == category]
        if risk_at_most:
            max_risk = risk_order[risk_at_most]
            results = [capability for capability in results if risk_order[capability.risk_level] <= max_risk]
        return sorted(results, key=lambda capability: capability.reliability_score, reverse=True)


def default_software_engineering_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for name, category, owner, provider in [
        ("repository_static_analysis", "engineering", "tool", "local"),
        ("implementation_planning", "planning", "ai_specialist", "arceus"),
        ("secure_code_review", "security", "ai_specialist", "arceus"),
        ("qa_verification", "quality", "ai_specialist", "arceus"),
        ("patch_generation", "engineering", "ai_specialist", "arceus"),
    ]:
        registry.register(
            Capability(
                name=name,
                category=category,
                description=name.replace("_", " ").title(),
                owner_type=owner,  # type: ignore[arg-type]
                provider=provider,
                supported_domains=["software_engineering"],
                risk_level="medium" if category in {"engineering", "security"} else "low",
                reliability_score=0.86,
            )
        )
    return registry

