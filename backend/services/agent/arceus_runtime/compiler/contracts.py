from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RepositoryScope:
    repository_id: UUID
    provider: str
    repository_url: str
    base_ref: str | None = None
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompileMissionInput:
    tenant_id: UUID
    mission_id: UUID
    project_id: UUID
    actor_id: str
    source_mission_version: int
    objective: str
    repository_scopes: tuple[RepositoryScope, ...]
    constraints: tuple[str, ...] = ()
    desired_outcomes: tuple[str, ...] = ()
    budget: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompilerStageResult:
    stage: str
    status: str
    output: dict[str, Any]
    input_hash: str
    output_hash: str
    duration_ms: int
    warning_codes: tuple[str, ...] = ()
    cost_usd: float = 0.0

    def to_record(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "output": self.output,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "duration_ms": self.duration_ms,
            "warning_codes": list(self.warning_codes),
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True)
class CompilerRunResult:
    compiler_run_id: UUID
    status: str
    normalized_objective: str
    primary_intent: str
    secondary_intents: tuple[str, ...]
    boundary_status: str
    warning_codes: tuple[str, ...]
    clarification_questions: tuple[str, ...]
    proposal: dict[str, Any]

