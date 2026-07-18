"""Model and tool gateway contracts for controlled execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


ToolExecutionState = Literal["REQUESTED", "POLICY_CHECKED", "APPROVAL_REQUIRED", "APPROVED", "EXECUTING", "SUCCEEDED", "FAILED", "REJECTED"]
ToolCategory = Literal["repository_reader", "file_search", "file_reader", "scoped_file_writer", "git_status", "git_diff", "branch_creator", "test_runner", "build_runner", "static_analyzer", "dependency_scanner", "terminal_command_runner", "artifact_uploader"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    category: ToolCategory
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_requirements: list[str]
    risk_level: RiskLevel
    timeout_seconds: int = 60
    retry_limit: int = 1
    allowed_environments: list[str] = field(default_factory=lambda: ["local", "development"])
    audit_required: bool = True
    approval_required: bool = False
    tool_id: str = field(default_factory=new_id)


@dataclass(slots=True)
class ToolExecution:
    tenant_id: str
    mission_id: str
    tool_id: str
    requested_by: str
    input: dict[str, Any]
    state: ToolExecutionState = "REQUESTED"
    output: dict[str, Any] | None = None
    error: str | None = None
    execution_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def transition(self, state: ToolExecutionState) -> None:
        allowed = {
            "REQUESTED": {"POLICY_CHECKED", "REJECTED"},
            "POLICY_CHECKED": {"APPROVAL_REQUIRED", "APPROVED", "REJECTED"},
            "APPROVAL_REQUIRED": {"APPROVED", "REJECTED"},
            "APPROVED": {"EXECUTING", "REJECTED"},
            "EXECUTING": {"SUCCEEDED", "FAILED"},
            "SUCCEEDED": set(),
            "FAILED": set(),
            "REJECTED": set(),
        }
        if state not in allowed[self.state]:
            raise ValueError(f"Invalid tool execution transition {self.state} -> {state}")
        self.state = state


@dataclass(slots=True)
class ModelExecutionMetric:
    tenant_id: str
    mission_id: str
    provider: str
    model: str
    role: str
    task_type: str
    tokens: int
    cost: float
    latency_ms: int
    outcome: Literal["success", "failed", "invalid_output"]
    retry_count: int = 0
    validation_result: str = "not_checked"
    metric_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "tenant_id": self.tenant_id,
            "mission_id": self.mission_id,
            "provider": self.provider,
            "model": self.model,
            "role": self.role,
            "task_type": self.task_type,
            "tokens": self.tokens,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "outcome": self.outcome,
            "retry_count": self.retry_count,
            "validation_result": self.validation_result,
            "created_at": self.created_at,
        }

