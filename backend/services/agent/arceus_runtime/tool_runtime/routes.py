from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import (
    ToolAuthorizationRequest,
    ToolAuthorizationResponse,
    ToolExecutionReceipt,
    ToolExecutionRequest,
    ToolReceiptVerificationRequest,
    ToolReceiptVerificationResponse,
    ToolRuntimeCatalogResponse,
)
from .service import CATALOG, ToolRuntimeService, verify_tool_receipt


router = APIRouter(prefix="/api/v1/tool-runtime", tags=["tool-runtime"])


def _service(db: Session, context: RequestContext) -> ToolRuntimeService:
    return ToolRuntimeService(db, tenant_id=context.tenant_id, actor_id=context.user_id, correlation_id=context.correlation_id)


@router.get("/catalog", response_model=dict)
def catalog(
    request: Request,
    context: RequestContext = Depends(require_permission("tool_registry.view")),
) -> dict:
    response = ToolRuntimeCatalogResponse(tools=list(CATALOG.values()))
    return api_response(response.model_dump(mode="json"), request)


@router.post("/authorize", response_model=dict)
def authorize_tool(
    payload: ToolAuthorizationRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("tool.authorize")),
) -> dict:
    service = _service(db, context)
    response = service.authorize(payload)
    db.commit()
    return api_response(ToolAuthorizationResponse(**response.model_dump()).model_dump(mode="json"), request)


@router.post("/execute", response_model=dict)
def execute_tool(
    payload: ToolExecutionRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("tool.execute")),
) -> dict:
    service = _service(db, context)
    receipt = service.execute(payload)
    db.commit()
    return api_response(receipt.model_dump(mode="json"), request)


@router.get("/executions", response_model=dict)
def list_executions(
    request: Request,
    mission_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("tool_execution.view")),
) -> dict:
    service = _service(db, context)
    rows = service.executions(mission_id=mission_id, status=status, limit=limit)
    return collection_response([row.model_dump(mode="json") for row in rows], request)


@router.get("/executions/{execution_id}", response_model=dict)
def get_execution(
    execution_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("tool_execution.view")),
) -> dict:
    service = _service(db, context)
    receipt = service.execution(execution_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Tool execution not found.")
    return api_response(receipt.model_dump(mode="json"), request)


@router.post("/receipts/verify", response_model=dict)
def verify_receipt(
    payload: ToolReceiptVerificationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("tool_execution.view")),
) -> dict:
    valid, reasons = verify_tool_receipt(ToolExecutionReceipt(**payload.receipt.model_dump()))
    return api_response(ToolReceiptVerificationResponse(valid=valid, reasons=reasons).model_dump(mode="json"), request)
