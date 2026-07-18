"""Structured specialist communication with duplicate and loop controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


RecipientType = Literal["agent", "team", "council", "human", "broadcast"]
MessageType = Literal["request", "response", "proposal", "finding", "objection", "review", "decision", "escalation", "status_update", "approval_request"]
Priority = Literal["low", "medium", "high", "critical"]
MessageStatus = Literal["created", "delivered", "read", "responded", "expired"]


@dataclass(slots=True)
class SpecialistMessage:
    tenant_id: str
    project_id: str
    mission_id: str
    organization_id: str
    sender_id: str
    recipient_type: RecipientType
    recipient_ids: list[str]
    message_type: MessageType
    topic: str
    summary: str
    content: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    related_task_ids: list[str] = field(default_factory=list)
    related_decision_ids: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.75
    priority: Priority = "medium"
    requires_response: bool = False
    correlation_id: str | None = None
    status: MessageStatus = "created"
    message_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def fingerprint(self) -> str:
        return f"{self.sender_id}:{self.recipient_type}:{','.join(self.recipient_ids)}:{self.message_type}:{self.topic}:{self.summary}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "organization_id": self.organization_id,
            "sender_id": self.sender_id,
            "recipient_type": self.recipient_type,
            "recipient_ids": self.recipient_ids,
            "message_type": self.message_type,
            "topic": self.topic,
            "summary": self.summary,
            "content": self.content,
            "evidence_ids": self.evidence_ids,
            "artifact_ids": self.artifact_ids,
            "related_task_ids": self.related_task_ids,
            "related_decision_ids": self.related_decision_ids,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "confidence": self.confidence,
            "priority": self.priority,
            "requires_response": self.requires_response,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "created_at": self.created_at,
        }


class MessageBus:
    def __init__(self, *, per_sender_limit: int = 50, loop_threshold: int = 4) -> None:
        self.messages: list[SpecialistMessage] = []
        self._fingerprints: set[str] = set()
        self.per_sender_limit = per_sender_limit
        self.loop_threshold = loop_threshold

    def send(self, message: SpecialistMessage) -> SpecialistMessage:
        sender_count = sum(1 for item in self.messages if item.sender_id == message.sender_id)
        if sender_count >= self.per_sender_limit:
            raise ValueError("Message rate limit exceeded for sender.")
        fingerprint = message.fingerprint()
        if fingerprint in self._fingerprints:
            raise ValueError("Duplicate specialist message blocked.")
        if message.correlation_id:
            correlated = [item for item in self.messages if item.correlation_id == message.correlation_id]
            if len(correlated) >= self.loop_threshold:
                raise ValueError("Potential agent message loop blocked.")
        self._fingerprints.add(fingerprint)
        message.status = "delivered"
        self.messages.append(message)
        return message

    def mission_messages(self, mission_id: str) -> list[SpecialistMessage]:
        return [message for message in self.messages if message.mission_id == mission_id]

