from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ..application.errors import DomainError


def response_meta(request: Request) -> dict[str, str]:
    return {
        "request_id": str(getattr(request.state, "request_id", "")),
        "correlation_id": str(getattr(request.state, "correlation_id", "")),
    }


def api_response(data: Any, request: Request, **extra: Any) -> dict[str, Any]:
    body = {"data": data, "meta": response_meta(request)}
    body.update(extra)
    return body


def collection_response(data: list[Any], request: Request, *, next_cursor: str | None = None, has_more: bool = False) -> dict[str, Any]:
    return {
        "data": data,
        "pagination": {"next_cursor": next_cursor, "has_more": has_more},
        "meta": response_meta(request),
    }


async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=error.http_status,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "retryable": error.retryable,
            },
            "meta": response_meta(request),
        },
    )
