"""Append-only event store for Arceus OS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .core import new_id, utc_now


ActorType = Literal["human", "agent", "system", "tool"]
AggregateType = Literal["mission", "organization", "agent", "task", "workflow", "decision", "approval", "artifact", "system"]
EventType = Literal[
    "MISSION_CREATED",
    "MISSION_UPDATED",
    "MISSION_APPROVED",
    "MISSION_PAUSED",
    "MISSION_RESUMED",
    "MISSION_CANCELLED",
    "MISSION_COMPLETED",
    "ORGANIZATION_FORMED",
    "AGENT_CREATED",
    "TASK_CREATED",
    "TASK_ASSIGNED",
    "TASK_STARTED",
    "TASK_BLOCKED",
    "TASK_COMPLETED",
    "DECISION_PROPOSED",
    "DECISION_APPROVED",
    "APPROVAL_REQUESTED",
    "APPROVAL_GRANTED",
    "TOOL_REQUESTED",
    "TOOL_EXECUTED",
    "MODEL_CALLED",
    "ARTIFACT_CREATED",
    "REVIEW_COMPLETED",
    "VERIFICATION_PASSED",
    "VERIFICATION_FAILED",
    "LESSON_RECORDED",
    "POLICY_VIOLATION",
    "RECOVERY_ACTION_STARTED",
    "RECOVERY_ACTION_COMPLETED",
]


@dataclass(frozen=True, slots=True)
class Actor:
    type: ActorType
    id: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id}

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "Actor":
        return Actor(type=value["type"], id=value["id"])


@dataclass(frozen=True, slots=True)
class EventMetadata:
    correlation_id: str
    causation_id: str | None = None
    idempotency_key: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "idempotency_key": self.idempotency_key,
            "schema_version": self.schema_version,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "EventMetadata":
        return EventMetadata(
            correlation_id=value["correlation_id"],
            causation_id=value.get("causation_id"),
            idempotency_key=value.get("idempotency_key"),
            schema_version=int(value.get("schema_version") or 1),
        )


@dataclass(frozen=True, slots=True)
class KernelEvent:
    event_type: EventType
    aggregate_type: AggregateType
    aggregate_id: str
    actor: Actor
    payload: dict[str, Any] = field(default_factory=dict)
    mission_id: str | None = None
    organization_id: str | None = None
    metadata: EventMetadata = field(default_factory=lambda: EventMetadata(correlation_id=new_id()))
    event_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "mission_id": self.mission_id,
            "organization_id": self.organization_id,
            "actor": self.actor.to_dict(),
            "payload": self.payload,
            "metadata": self.metadata.to_dict(),
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "KernelEvent":
        return KernelEvent(
            event_type=value["event_type"],
            aggregate_type=value["aggregate_type"],
            aggregate_id=value["aggregate_id"],
            mission_id=value.get("mission_id"),
            organization_id=value.get("organization_id"),
            actor=Actor.from_dict(value["actor"]),
            payload=dict(value.get("payload") or {}),
            metadata=EventMetadata.from_dict(value.get("metadata") or {"correlation_id": value.get("event_id") or new_id()}),
            event_id=value.get("event_id") or new_id(),
            created_at=value.get("created_at") or utc_now(),
        )


class AppendOnlyEventStore:
    """In-memory append-only event store.

    This is the deterministic contract used by tests and early runtime wiring.
    Production persistence can later back this with PostgreSQL without changing
    callers.
    """

    def __init__(self) -> None:
        self._events: list[KernelEvent] = []
        self._idempotency_index: set[str] = set()

    def append(self, event: KernelEvent) -> KernelEvent:
        key = event.metadata.idempotency_key
        if key:
            if key in self._idempotency_index:
                raise ValueError(f"Duplicate event idempotency key: {key}")
            self._idempotency_index.add(key)
        self._events.append(event)
        return event

    def all(self) -> list[KernelEvent]:
        return list(self._events)

    def by_mission(self, mission_id: str) -> list[KernelEvent]:
        return [event for event in self._events if event.mission_id == mission_id]

    def replay(self, aggregate_type: AggregateType | None = None, aggregate_id: str | None = None) -> list[dict[str, Any]]:
        events = self._events
        if aggregate_type:
            events = [event for event in events if event.aggregate_type == aggregate_type]
        if aggregate_id:
            events = [event for event in events if event.aggregate_id == aggregate_id]
        return [event.to_dict() for event in events]


class JsonlEventStore(AppendOnlyEventStore):
    """Append-only JSONL-backed store for local durable Generation 1 runtime."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            for raw_line in self.path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                event = KernelEvent.from_dict(json.loads(raw_line))
                key = event.metadata.idempotency_key
                if key:
                    self._idempotency_index.add(key)
                self._events.append(event)

    def append(self, event: KernelEvent) -> KernelEvent:
        persisted = super().append(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(persisted.to_dict(), sort_keys=True) + "\n")
        return persisted
