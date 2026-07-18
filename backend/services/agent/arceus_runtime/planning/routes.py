from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_idempotency_key, require_permission
from ..api.responses import api_response
from ..application.idempotency import calculate_request_hash
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from services.shared.arceus_core_models import ArceusTask, ArceusWorkflowDefinition, ArceusWorkflowEdge, ArceusWorkflowNode

from .api_schemas import PlanMissionRequest, PlanMissionResponse, WorkflowGraphEdgeResponse, WorkflowGraphNodeResponse, WorkflowGraphResponse
from .contracts import PlanMissionCommand
from .service import PlanMissionService


router = APIRouter(tags=["planning"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


@router.post("/api/v1/missions/{mission_id}/plan", status_code=status.HTTP_202_ACCEPTED)
def plan_mission(
    mission_id: UUID,
    request_body: PlanMissionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.plan")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    payload = {"mission_id": str(mission_id), "expected_version": request_body.expected_version}
    result = PlanMissionService(_uow(db)).plan(
        PlanMissionCommand(
            tenant_id=context.tenant_id,
            mission_id=mission_id,
            expected_version=request_body.expected_version,
            actor_id=context.user_id,
            idempotency_key=idempotency_key,
            request_hash=calculate_request_hash("mission.plan", payload),
            correlation_id=context.correlation_id,
        )
    )
    response = PlanMissionResponse(
        mission_id=result.mission_id,
        organization_id=result.organization_id,
        workflow_id=result.workflow_id,
        plan_artifact_id=result.plan_artifact_id,
        approval_id=result.approval_id,
        status=result.status,
        organization_size=result.organization_size,
        task_count=result.task_count,
        graph_hash=result.graph_hash,
        critical_path=list(result.critical_path),
        capability_gaps=list(result.capability_gaps),
        metrics=result.metrics,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/workflows/{workflow_id}/graph")
def get_workflow_graph(
    workflow_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.view")),
    db: Session = Depends(get_db),
):
    workflow = (
        db.query(ArceusWorkflowDefinition)
        .filter(ArceusWorkflowDefinition.tenant_id == context.tenant_id, ArceusWorkflowDefinition.id == workflow_id)
        .first()
    )
    if workflow is None:
        from ..application.errors import RuntimeStateConflict

        raise RuntimeStateConflict("Workflow was not found.", details={"workflow_id": str(workflow_id)})

    nodes = (
        db.query(ArceusWorkflowNode)
        .filter(ArceusWorkflowNode.tenant_id == context.tenant_id, ArceusWorkflowNode.workflow_id == workflow.id)
        .order_by(ArceusWorkflowNode.created_at.asc(), ArceusWorkflowNode.node_key.asc())
        .all()
    )
    tasks_by_node = {
        task.workflow_node_id: task
        for task in db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == workflow.mission_id)
        .all()
    }
    edges = (
        db.query(ArceusWorkflowEdge)
        .filter(ArceusWorkflowEdge.tenant_id == context.tenant_id, ArceusWorkflowEdge.workflow_id == workflow.id)
        .order_by(ArceusWorkflowEdge.created_at.asc(), ArceusWorkflowEdge.id.asc())
        .all()
    )
    metadata = workflow.metadata_json or {}
    response = WorkflowGraphResponse(
        workflow_id=workflow.id,
        mission_id=workflow.mission_id,
        status=workflow.status,
        graph_hash=workflow.graph_hash,
        workflow_version=int(metadata.get("workflow_version", 1)),
        selected_proposal=metadata.get("selected_proposal"),
        metrics=metadata.get("metrics") or {},
        nodes=[
            WorkflowGraphNodeResponse(
                id=node.id,
                node_key=node.node_key,
                node_type=node.node_type,
                title=node.title,
                owner_role_key=(node.config or {}).get("owner_role_key"),
                status=getattr(tasks_by_node.get(node.id), "status", None),
                estimates=(node.config or {}).get("estimates") or {},
                config=node.config or {},
            )
            for node in nodes
        ],
        edges=[
            WorkflowGraphEdgeResponse(
                id=edge.id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                condition=edge.condition or {},
            )
            for edge in edges
        ],
    )
    return api_response(response.model_dump(mode="json"), request)
