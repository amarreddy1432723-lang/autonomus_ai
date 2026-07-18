from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusOutboxMessage

from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..execution.service import RuntimeSchedulerService
from .compiler import MissionCompilationWorker


MAX_OUTBOX_ATTEMPTS = 3


class EventPublisher(Protocol):
    def publish(self, *, topic: str, key: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
        ...


class NoopEventPublisher:
    def publish(self, *, topic: str, key: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
        return None


@dataclass(frozen=True)
class WorkerMessage:
    message_id: UUID
    tenant_id: UUID
    topic: str
    aggregate_id: UUID | None
    correlation_id: UUID | None
    causation_id: UUID | None
    payload: dict[str, Any]
    attempt_number: int
    occurred_at: datetime


def calculate_backoff_seconds(attempt_number: int) -> int:
    return min((2 ** max(attempt_number - 1, 0)) * 5, 60)


class OutboxWorker:
    def __init__(self, db: Session, *, worker_id: str, publisher: EventPublisher | None = None) -> None:
        self.db = db
        self.worker_id = worker_id
        self.publisher = publisher or NoopEventPublisher()

    def process_batch(self, *, limit: int = 50) -> dict[str, int]:
        uow = SqlAlchemyUnitOfWork(self.db)
        messages = uow.outbox.claim_batch(worker_id=self.worker_id, limit=limit)
        uow.commit()

        processed = 0
        sent = 0
        failed = 0
        dead_lettered = 0
        for message in messages:
            processed += 1
            try:
                self._process_message(message)
            except Exception as exc:
                failure_uow = SqlAlchemyUnitOfWork(self.db)
                current = self._reload_message(failure_uow, message.id)
                if int(current.attempts or 0) >= MAX_OUTBOX_ATTEMPTS:
                    failure_uow.outbox.move_to_dead_letter(current, error=str(exc))
                    dead_lettered += 1
                else:
                    failure_uow.outbox.mark_failed(
                        current,
                        error=str(exc),
                        retry_delay_seconds=calculate_backoff_seconds(int(current.attempts or 1)),
                    )
                    failed += 1
                failure_uow.commit()
            else:
                sent_uow = SqlAlchemyUnitOfWork(self.db)
                current = self._reload_message(sent_uow, message.id)
                sent_uow.outbox.mark_sent(current)
                sent_uow.commit()
                sent += 1
        return {"processed": processed, "sent": sent, "failed": failed, "dead_lettered": dead_lettered}

    def _process_message(self, message: ArceusOutboxMessage) -> None:
        worker_message = self._to_worker_message(message)
        if worker_message.topic == "arceus.mission.compilation.requested":
            mission_id = worker_message.aggregate_id
            if mission_id is None:
                raise ValueError("Compilation request is missing aggregate_id.")
            MissionCompilationWorker(self.db).process(
                tenant_id=worker_message.tenant_id,
                mission_id=mission_id,
                started_version=None,
            )
        elif worker_message.topic == "arceus.workflow.ready":
            mission_id = worker_message.aggregate_id
            if mission_id is None:
                raise ValueError("Workflow ready event is missing aggregate_id.")
            scheduler_uow = SqlAlchemyUnitOfWork(self.db)
            RuntimeSchedulerService(scheduler_uow).schedule(
                tenant_id=worker_message.tenant_id,
                mission_id=mission_id,
                limit=50,
            )
            scheduler_uow.commit()

        self.publisher.publish(
            topic=worker_message.topic,
            key=str(worker_message.aggregate_id or worker_message.message_id),
            payload=worker_message.payload,
            headers={
                "message_id": str(worker_message.message_id),
                "tenant_id": str(worker_message.tenant_id),
                "attempt_number": str(worker_message.attempt_number),
            },
        )

    def _to_worker_message(self, message: ArceusOutboxMessage) -> WorkerMessage:
        aggregate_id = None
        payload = message.payload or {}
        aggregate_id_raw = payload.get("aggregate_id")
        if aggregate_id_raw:
            aggregate_id = UUID(str(aggregate_id_raw))
        return WorkerMessage(
            message_id=message.id,
            tenant_id=message.tenant_id,
            topic=message.topic,
            aggregate_id=aggregate_id,
            correlation_id=None,
            causation_id=message.event_id,
            payload=payload,
            attempt_number=int(message.attempts or 1),
            occurred_at=message.created_at,
        )

    def _reload_message(self, uow: SqlAlchemyUnitOfWork, message_id: UUID) -> ArceusOutboxMessage:
        message = uow.db.query(ArceusOutboxMessage).filter(ArceusOutboxMessage.id == message_id).first()
        if message is None:
            raise ValueError(f"Outbox message disappeared: {message_id}")
        return message
