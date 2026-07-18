from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompilerRunSummaryResponse(BaseModel):
    id: UUID
    mission_id: UUID
    source_mission_version: int
    status: str
    current_stage: str | None
    warning_codes: list[str]
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class CompilerRunDetailResponse(CompilerRunSummaryResponse):
    model_config = ConfigDict(protected_namespaces=())

    stage_results: dict
    source_manifest_id: UUID | None
    compiled_mission_version_id: UUID | None
    model_execution_ids: list[str]
