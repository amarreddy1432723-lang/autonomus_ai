from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..execution.service import RuntimeTaskExecutor


@dataclass(frozen=True)
class RuntimeWorkerTick:
    status: str
    task_id: str | None = None
    attempt_id: str | None = None
    checkpoint_id: str | None = None
    expired_leases: int = 0
    retryable: bool = False


class RuntimeWorkerLoop:
    """Durable task worker loop for Arceus mission runtime.

    The loop is intentionally small: a process manager, Celery task, or local
    dev command can call `run_once` or `run_until_idle` without duplicating
    scheduling, leasing, execution, checkpoint, retry, and verification logic.
    """

    def __init__(self, session_factory: Callable[[], Session], *, worker_id: str, ttl_seconds: int = 120) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.ttl_seconds = ttl_seconds

    def run_once(self, *, tenant_id: UUID, mission_id: UUID) -> RuntimeWorkerTick:
        db = self.session_factory()
        try:
            uow = SqlAlchemyUnitOfWork(db)
            result = RuntimeTaskExecutor(uow).run_next(
                tenant_id=tenant_id,
                mission_id=mission_id,
                worker_id=self.worker_id,
                ttl_seconds=self.ttl_seconds,
            )
            uow.commit()
            return RuntimeWorkerTick(
                status=result["status"],
                task_id=result.get("task_id"),
                attempt_id=result.get("attempt_id"),
                checkpoint_id=result.get("checkpoint_id"),
                expired_leases=int(result.get("expired_leases", 0)),
                retryable=bool(result.get("retryable", False)),
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def run_until_idle(self, *, tenant_id: UUID, mission_id: UUID, max_ticks: int = 25, sleep_seconds: float = 0.0) -> list[RuntimeWorkerTick]:
        ticks: list[RuntimeWorkerTick] = []
        for _ in range(max(1, max_ticks)):
            tick = self.run_once(tenant_id=tenant_id, mission_id=mission_id)
            ticks.append(tick)
            if tick.status == "idle":
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        return ticks
