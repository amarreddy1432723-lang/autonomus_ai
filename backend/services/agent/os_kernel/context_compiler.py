"""Task-specific context compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .capabilities import CapabilityRegistry
from .missions import OSMission
from .world_model import KnowledgeItem, WorldModel


@dataclass(slots=True)
class ContextRequest:
    tenant_id: str
    agent_role: str
    task_title: str
    task_description: str
    mission: OSMission
    required_output_schema: dict[str, Any] = field(default_factory=dict)
    token_budget: int = 4000
    has_secret_authority: bool = False


class ContextCompiler:
    def __init__(self, world_model: WorldModel, capability_registry: CapabilityRegistry) -> None:
        self.world_model = world_model
        self.capability_registry = capability_registry

    def compile(self, request: ContextRequest) -> dict[str, Any]:
        terms = request.task_title.split() + request.task_description.split() + request.mission.objective.split()
        knowledge: list[KnowledgeItem] = self.world_model.retrieve(
            tenant_id=request.tenant_id,
            query_terms=terms,
            scope="mission",
            has_secret_authority=request.has_secret_authority,
        )
        capabilities = self.capability_registry.discover(domains=["software_engineering"], risk_at_most="medium")
        return {
            "task_summary": {"title": request.task_title, "description": request.task_description},
            "mission_context": request.mission.to_dict(),
            "relevant_requirements": request.mission.success_criteria,
            "relevant_decisions": [item.to_dict() for item in knowledge if item.kind == "DECISION"],
            "known_constraints": [],
            "known_risks": [],
            "supporting_evidence": [item.to_dict() for item in knowledge if item.trusted],
            "related_artifacts": [],
            "previous_attempts": [],
            "available_tools": [capability.to_dict() for capability in capabilities],
            "authority_limits": {"can_read_secret": request.has_secret_authority, "agent_role": request.agent_role},
            "required_output_schema": request.required_output_schema,
            "token_budget": request.token_budget,
        }

