"""Durable workflow contracts with idempotent steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


StepState = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "PAUSED", "CANCELLED", "COMPENSATED"]


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: int = 5


@dataclass(slots=True)
class WorkflowStep:
    name: str
    owner: str
    input: dict[str, Any]
    expected_output: dict[str, Any]
    timeout_seconds: int
    idempotency_key: str
    required_permissions: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    failure_handler: str | None = None
    compensation_action: str | None = None
    verification_policy: dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    output: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    attempt_count: int = 0
    state: StepState = "PENDING"
    step_id: str = field(default_factory=new_id)
    updated_at: str = field(default_factory=utc_now)

    def start(self, completed_keys: set[str]) -> None:
        if self.idempotency_key in completed_keys:
            raise ValueError(f"Step already completed for idempotency key {self.idempotency_key}")
        if self.state not in {"PENDING", "FAILED", "PAUSED"}:
            raise ValueError(f"Cannot start step from {self.state}")
        self.state = "RUNNING"
        self.attempt_count += 1
        self.updated_at = utc_now()

    def complete(self, output: dict[str, Any], evidence: dict[str, Any]) -> None:
        if self.state != "RUNNING":
            raise ValueError("Only running steps can complete")
        if not evidence or evidence.get("status") in {"failed", "error"}:
            raise ValueError("Workflow step completion requires passing evidence")
        self.output = output
        self.evidence.append(evidence)
        self.state = "COMPLETED"
        self.updated_at = utc_now()


@dataclass(slots=True)
class WorkflowRun:
    mission_id: str
    steps: list[WorkflowStep]
    run_id: str = field(default_factory=new_id)
    state: Literal["PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"] = "PENDING"
    completed_idempotency_keys: set[str] = field(default_factory=set)

    def next_ready_step(self) -> WorkflowStep | None:
        for step in self.steps:
            if step.state in {"PENDING", "FAILED", "PAUSED"}:
                return step
        return None

    def execute_step(self, step_id: str, output: dict[str, Any], evidence: dict[str, Any]) -> WorkflowStep:
        step = next(item for item in self.steps if item.step_id == step_id)
        if not evidence or evidence.get("status") in {"failed", "error"}:
            raise ValueError("Workflow step completion requires passing evidence")
        step.start(self.completed_idempotency_keys)
        step.complete(output, evidence)
        self.completed_idempotency_keys.add(step.idempotency_key)
        if all(item.state == "COMPLETED" for item in self.steps):
            self.state = "COMPLETED"
        else:
            self.state = "RUNNING"
        return step

    def pause(self) -> None:
        self.state = "PAUSED"

    def resume(self) -> None:
        if self.state != "PAUSED":
            raise ValueError("Only paused workflows can resume")
        self.state = "RUNNING"
