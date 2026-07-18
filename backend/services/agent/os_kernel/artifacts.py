"""Artifact, evidence, and trust contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


ArtifactType = Literal["requirements", "architecture_plan", "implementation_plan", "code_patch", "file_change", "test_report", "build_log", "security_scan", "screenshot", "deployment_report", "research_report", "review_report"]
EvidenceType = Literal["test_success", "build_success", "static_analysis", "security_scan", "code_diff", "command_output", "screenshot", "benchmark", "source_citation", "reviewer_approval", "human_approval"]
TrustLevel = Literal["UNVERIFIED", "PEER_REVIEWED", "TOOL_VERIFIED", "HUMAN_APPROVED", "OBSERVED_IN_ENVIRONMENT"]
VerificationStatus = Literal["unverified", "verified", "failed"]


TRUST_ORDER = ["UNVERIFIED", "PEER_REVIEWED", "TOOL_VERIFIED", "HUMAN_APPROVED", "OBSERVED_IN_ENVIRONMENT"]


def content_hash(content: Any) -> str:
    return hashlib.sha256(repr(content).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class MissionArtifact:
    tenant_id: str
    mission_id: str
    artifact_type: ArtifactType
    creator_id: str
    version: int = 1
    related_task_id: str | None = None
    storage_location: str = ""
    content: Any = None
    trust_level: TrustLevel = "UNVERIFIED"
    verification_status: VerificationStatus = "unverified"
    artifact_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def hash(self) -> str:
        return content_hash(self.content)

    def promote_trust(self, new_level: TrustLevel) -> None:
        if TRUST_ORDER.index(new_level) < TRUST_ORDER.index(self.trust_level):
            raise ValueError("Artifact trust cannot move backwards without superseding.")
        self.trust_level = new_level
        if new_level in {"TOOL_VERIFIED", "HUMAN_APPROVED", "OBSERVED_IN_ENVIRONMENT"}:
            self.verification_status = "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "mission_id": self.mission_id,
            "artifact_type": self.artifact_type,
            "version": self.version,
            "creator_id": self.creator_id,
            "related_task_id": self.related_task_id,
            "storage_location": self.storage_location,
            "content_hash": self.hash,
            "trust_level": self.trust_level,
            "verification_status": self.verification_status,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Evidence:
    tenant_id: str
    mission_id: str
    evidence_type: EvidenceType
    summary: str
    source: str
    artifact_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    evidence_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "tenant_id": self.tenant_id,
            "mission_id": self.mission_id,
            "evidence_type": self.evidence_type,
            "summary": self.summary,
            "source": self.source,
            "artifact_id": self.artifact_id,
            "data": self.data,
            "verified": self.verified,
            "created_at": self.created_at,
        }

