from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusBudget, ArceusCostReservation


class BudgetExceededError(RuntimeError):
    def __init__(self, message: str, *, budget_id: UUID, requested: Decimal, remaining: Decimal) -> None:
        super().__init__(message)
        self.budget_id = budget_id
        self.requested = requested
        self.remaining = remaining


def remaining_budget(budget: ArceusBudget) -> Decimal:
    return Decimal(budget.limit_amount or 0) - Decimal(budget.reserved_amount or 0) - Decimal(budget.actual_amount or 0)


def budget_status(budget: ArceusBudget) -> str:
    remaining = remaining_budget(budget)
    if remaining <= 0:
        return "exhausted"
    spent = Decimal(budget.reserved_amount or 0) + Decimal(budget.actual_amount or 0)
    percent = (spent / max(Decimal(budget.limit_amount or 0), Decimal("0.00000001"))) * Decimal(100)
    return "warning" if percent >= Decimal(budget.warning_threshold_percent or 80) else "active"


def find_budget_for_execution(*, db: Session, tenant_id: UUID, mission_id: UUID, task_id: UUID | None) -> ArceusBudget | None:
    scopes = []
    if task_id:
        scopes.append(("task", task_id))
    scopes.extend([("mission", mission_id), ("tenant", tenant_id)])
    for scope_type, scope_id in scopes:
        budget = (
            db.query(ArceusBudget)
            .filter(ArceusBudget.tenant_id == tenant_id, ArceusBudget.scope_type == scope_type, ArceusBudget.scope_id == scope_id, ArceusBudget.status != "disabled")
            .with_for_update()
            .first()
        )
        if budget is not None:
            return budget
    return None


def reserve_budget(
    *,
    db: Session,
    tenant_id: UUID,
    mission_id: UUID,
    task_id: UUID | None,
    amount: Decimal,
    idempotency_key: str,
) -> ArceusCostReservation | None:
    if amount <= 0:
        return None
    existing = db.query(ArceusCostReservation).filter(ArceusCostReservation.tenant_id == tenant_id, ArceusCostReservation.idempotency_key == idempotency_key).first()
    if existing is not None:
        return existing
    budget = find_budget_for_execution(db=db, tenant_id=tenant_id, mission_id=mission_id, task_id=task_id)
    if budget is None:
        return None
    remaining = remaining_budget(budget)
    if amount > remaining:
        budget.status = "exhausted"
        raise BudgetExceededError("Budget limit reached.", budget_id=budget.id, requested=amount, remaining=remaining)
    budget.reserved_amount = Decimal(budget.reserved_amount or 0) + amount
    budget.status = budget_status(budget)
    reservation = ArceusCostReservation(
        tenant_id=tenant_id,
        budget_id=budget.id,
        mission_id=mission_id,
        task_id=task_id,
        amount=amount,
        currency=budget.currency,
        status="reserved",
        idempotency_key=idempotency_key,
    )
    db.add(reservation)
    db.flush()
    return reservation


def settle_budget(
    *,
    db: Session,
    reservation: ArceusCostReservation | None,
    actual_amount: Decimal,
) -> None:
    if reservation is None or reservation.status == "settled":
        return
    budget = db.query(ArceusBudget).filter(ArceusBudget.id == reservation.budget_id).with_for_update().first()
    if budget is None:
        reservation.status = "failed"
        return
    reserved = Decimal(reservation.amount or 0)
    actual = max(Decimal("0"), actual_amount)
    budget.reserved_amount = max(Decimal("0"), Decimal(budget.reserved_amount or 0) - reserved)
    budget.actual_amount = Decimal(budget.actual_amount or 0) + actual
    budget.status = budget_status(budget)
    reservation.amount = actual
    reservation.status = "settled"
    reservation.settled_at = datetime.now(timezone.utc)


def release_budget(*, db: Session, reservation: ArceusCostReservation | None) -> None:
    if reservation is None or reservation.status != "reserved":
        return
    budget = db.query(ArceusBudget).filter(ArceusBudget.id == reservation.budget_id).with_for_update().first()
    if budget is not None:
        budget.reserved_amount = max(Decimal("0"), Decimal(budget.reserved_amount or 0) - Decimal(reservation.amount or 0))
        budget.status = budget_status(budget)
    reservation.status = "released"
    reservation.released_at = datetime.now(timezone.utc)

