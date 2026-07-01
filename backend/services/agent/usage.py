from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.models import UsageEvent
from .file_service import estimate_tokens


PRICE_PER_1K = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "llama-3.3-70b-versatile": (0.00059, 0.00079),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "autonomus-ai-v1": (0.0, 0.0),
}


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> Decimal:
    input_price, output_price = PRICE_PER_1K.get(model or "", (0.0, 0.0))
    value = (prompt_tokens / 1000 * input_price) + (completion_tokens / 1000 * output_price)
    return Decimal(str(round(value, 6)))


def record_usage(
    db: Session,
    user_id: UUID,
    route: str,
    provider: str | None,
    model: str | None,
    session_id: str | None,
    prompt_text: str,
    completion_text: str,
    file_ids: list[str] | None = None,
    metadata: dict | None = None,
) -> UsageEvent:
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    event = UsageEvent(
        user_id=user_id,
        route=route,
        provider=provider,
        model=model,
        session_id=session_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
        file_ids=file_ids or [],
        metadata_json=metadata or {},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def usage_summary(db: Session, user_id: UUID) -> dict:
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)
    rows = db.query(
        func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
        func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
        func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0),
    ).filter(UsageEvent.user_id == user_id, UsageEvent.created_at >= day_start).one()

    all_rows = db.query(
        func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0),
        func.count(UsageEvent.id),
    ).filter(UsageEvent.user_id == user_id).one()

    return {
        "last_24h": {
            "prompt_tokens": int(rows[0] or 0),
            "completion_tokens": int(rows[1] or 0),
            "total_tokens": int(rows[2] or 0),
            "estimated_cost_usd": float(rows[3] or 0),
        },
        "all_time": {
            "total_tokens": int(all_rows[0] or 0),
            "estimated_cost_usd": float(all_rows[1] or 0),
            "events": int(all_rows[2] or 0),
        },
    }
