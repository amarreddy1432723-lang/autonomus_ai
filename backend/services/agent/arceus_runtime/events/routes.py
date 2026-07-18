from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..application.unit_of_work import SqlAlchemyUnitOfWork


router = APIRouter(prefix="/api/v1/events", tags=["mission-events"])


def sse_event(*, event_id: int | str, event_name: str, data: dict[str, Any]) -> str:
    safe_name = event_name.lower().replace("_", ".")
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"id: {event_id}\nevent: {safe_name}\ndata: {payload}\n\n"


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"


@router.get("/stream")
async def stream_events(
    request: Request,
    mission_id: UUID = Query(...),
    after_sequence: int = Query(default=0, ge=0),
    context: RequestContext = Depends(require_permission("mission.view")),
    db: Session = Depends(get_db),
):
    uow = SqlAlchemyUnitOfWork(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)

    async def event_generator():
        last_sequence = after_sequence
        while True:
            if await request.is_disconnected():
                break

            events = uow.events.list_for_mission_after(
                tenant_id=context.tenant_id,
                mission_id=mission_id,
                after_version=last_sequence,
                limit=50,
            )
            if events:
                for event in events:
                    last_sequence = max(last_sequence, int(event.aggregate_version))
                    yield sse_event(
                        event_id=last_sequence,
                        event_name=event.event_type,
                        data={
                            "mission_id": str(mission_id),
                            "event_id": str(event.id),
                            "sequence": event.aggregate_version,
                            "event_type": event.event_type,
                            "payload": event.payload,
                            "occurred_at": event.occurred_at.isoformat(),
                        },
                    )
            else:
                yield sse_heartbeat()
                await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
