from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusEvent, ArceusMission, ArceusProject

from ..api.dependencies import RequestContext


SURFACE_PROJECTS = {
    "automation": ("automation-missions", "Automation Missions"),
    "product": ("product-missions", "Product Missions"),
    "experience": ("experience-missions", "Experience Missions"),
}


def mission_project_for_surface(db: Session, context: RequestContext, *, surface: str) -> ArceusProject:
    slug, name = SURFACE_PROJECTS.get(surface, (f"{surface}-missions", f"{surface.title()} Missions"))
    project = (
        db.query(ArceusProject)
        .filter(ArceusProject.tenant_id == context.tenant_id, ArceusProject.slug == slug)
        .first()
    )
    if project is not None:
        return project
    project = ArceusProject(
        tenant_id=context.tenant_id,
        name=name,
        slug=slug,
        description=f"System project for missions created by the {surface} surface.",
        status="active",
        settings={"system": True, "source_surface": surface},
        created_by=context.user_id,
    )
    db.add(project)
    db.flush()
    return project


def _next_event_version(db: Session, tenant_id: UUID, mission_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def create_surface_mission(
    db: Session,
    context: RequestContext,
    *,
    surface: str,
    title: str,
    objective: str,
    status: str = "draft",
    priority: int = 3,
    risk_level: str = "medium",
    budget_amount: Decimal | float | int | None = None,
    budget_currency: str = "USD",
    source: dict[str, Any] | None = None,
    desired_outcomes: list[str] | None = None,
    constraints: list[str] | None = None,
) -> ArceusMission:
    project = mission_project_for_surface(db, context, surface=surface)
    mission = ArceusMission(
        tenant_id=context.tenant_id,
        project_id=project.id,
        created_by=context.user_id,
        title=title[:300],
        objective=objective,
        status=status,
        risk_level=risk_level,
        priority=max(0, min(5, int(priority))),
        maximum_budget_amount=budget_amount,
        budget_currency=budget_currency,
        metadata_json={
            "created_from": surface,
            "source": source or {},
            "desired_outcomes": desired_outcomes or [],
            "constraints": constraints or [],
        },
    )
    db.add(mission)
    db.flush()
    db.add(
        ArceusEvent(
            tenant_id=context.tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=_next_event_version(db, context.tenant_id, mission.id),
            event_type=f"arceus.{surface}.mission.created",
            actor_type="human",
            actor_id=str(context.user_id),
            payload={
                "mission_id": str(mission.id),
                "project_id": str(project.id),
                "surface": surface,
                "title": title,
                "status": status,
                "risk_level": risk_level,
            },
            metadata_json={"correlation_id": str(context.correlation_id), "source_surface": surface},
        )
    )
    return mission
