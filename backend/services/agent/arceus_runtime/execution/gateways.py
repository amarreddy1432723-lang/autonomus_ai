from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TaskContextPackage:
    task_id: str
    task_key: str
    title: str
    task_type: str
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    acceptance_criteria: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    previous_checkpoint: dict[str, Any] | None = None


@dataclass(frozen=True)
class GatewayResult:
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    retryable: bool = False


class ModelGateway(Protocol):
    def run(self, context: TaskContextPackage) -> GatewayResult:
        ...


class ToolGateway(Protocol):
    def run(self, context: TaskContextPackage) -> GatewayResult:
        ...


class DeterministicModelGateway:
    """Local deterministic model stand-in for durable workflow tests and dev mode."""

    def run(self, context: TaskContextPackage) -> GatewayResult:
        return GatewayResult(
            status="succeeded",
            outputs={
                "summary": f"Prepared {context.task_type} result for {context.task_key}.",
                "accepted": True,
            },
            evidence=[
                {
                    "kind": "model_reasoning_stub",
                    "task_key": context.task_key,
                    "confidence": 0.82,
                }
            ],
        )


class DeterministicToolGateway:
    """Local deterministic tool stand-in for repository/check execution."""

    def run(self, context: TaskContextPackage) -> GatewayResult:
        forced = context.input_contract.get("force_tool_status") or context.output_contract.get("force_tool_status")
        if forced == "failed":
            return GatewayResult(status="failed", error="Deterministic tool failure requested.", retryable=True)
        return GatewayResult(
            status="succeeded",
            outputs={"tool_calls": [{"tool": "deterministic_runtime", "status": "passed"}]},
            evidence=[{"kind": "tool_result", "tool": "deterministic_runtime", "status": "passed"}],
        )


class VerificationEngine:
    def verify(self, context: TaskContextPackage, result: GatewayResult) -> GatewayResult:
        forced = context.output_contract.get("force_verification_status")
        if forced == "failed":
            return GatewayResult(
                status="failed",
                outputs=result.outputs,
                evidence=result.evidence + [{"kind": "verification", "status": "failed"}],
                error="Verification failed by task contract.",
                retryable=False,
            )
        if result.status != "succeeded":
            return result
        missing = [item for item in context.acceptance_criteria if not str(item).strip()]
        if missing:
            return GatewayResult(status="failed", outputs=result.outputs, evidence=result.evidence, error="Acceptance criteria are incomplete.")
        return GatewayResult(
            status="succeeded",
            outputs={**result.outputs, "verification": {"status": "passed", "criteria_count": len(context.acceptance_criteria)}},
            evidence=result.evidence + [{"kind": "verification", "status": "passed", "criteria_count": len(context.acceptance_criteria)}],
        )
