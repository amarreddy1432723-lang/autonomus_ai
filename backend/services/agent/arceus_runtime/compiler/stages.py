from __future__ import annotations

import time
from typing import Protocol

from .contracts import CompileMissionInput, CompilerStageResult
from .utils import stable_hash


class CompilerStage(Protocol):
    stage_key: str

    def run(self, payload: dict) -> dict:
        ...


def run_stage(stage: CompilerStage, payload: dict) -> CompilerStageResult:
    started = time.perf_counter()
    output = stage.run(payload)
    duration_ms = int((time.perf_counter() - started) * 1000)
    status = str(output.get("status") or "passed")
    warnings = tuple(str(item) for item in output.get("warning_codes", []) or [])
    return CompilerStageResult(
        stage=stage.stage_key,
        status=status,
        output=output,
        input_hash=stable_hash(payload),
        output_hash=stable_hash(output),
        duration_ms=duration_ms,
        warning_codes=warnings,
        cost_usd=float(output.get("cost_usd") or 0.0),
    )


def compiler_input_payload(command: CompileMissionInput) -> dict:
    return {
        "tenant_id": str(command.tenant_id),
        "mission_id": str(command.mission_id),
        "project_id": str(command.project_id),
        "actor_id": command.actor_id,
        "source_mission_version": command.source_mission_version,
        "objective": command.objective,
        "repository_scopes": [
            {
                "repository_id": str(item.repository_id),
                "provider": item.provider,
                "repository_url": item.repository_url,
                "base_ref": item.base_ref,
                "allowed_paths": list(item.allowed_paths),
                "denied_paths": list(item.denied_paths),
            }
            for item in command.repository_scopes
        ],
        "constraints": list(command.constraints),
        "desired_outcomes": list(command.desired_outcomes),
        "budget": command.budget,
    }

