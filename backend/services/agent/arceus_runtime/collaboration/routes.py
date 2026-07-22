from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusActivityEvent,
    ArceusCollaborationMessage,
    ArceusCollaborationTask,
    ArceusCollaborationTeam,
    ArceusCollaborationTeamMember,
    ArceusComment,
    ArceusDiscussionThread,
    ArceusKnowledgePage,
    ArceusMemoryItem,
    ArceusNotification,
    ArceusParticipantInboxItem,
    ArceusPresenceSession,
    ArceusProject,
    ArceusProjectMember,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AddTeamMemberRequest,
    CollaborationDecisionResponse,
    CollaborationMessageResponse,
    CompleteReviewRequest,
    CommentResponse,
    CreateCollaborativeProjectRequest,
    CreateCommentRequest,
    CreateDecisionRequest,
    CreateDiscussionThreadRequest,
    CreateMilestoneRequest,
    CreateReviewRequest,
    CreateTeamRequest,
    CreateWorkspaceTaskRequest,
    InboxItemResponse,
    KnowledgePageResponse,
    MemoryItemResponse,
    MemoryProposalRequest,
    NotificationResponse,
    PresenceResponse,
    ProjectMemberRequest,
    ProjectWorkspaceResponse,
    ResolveDecisionRequest,
    ReviewResponse,
    SendCollaborationMessageRequest,
    TeamResponse,
    UpsertKnowledgePageRequest,
    UpsertPresenceRequest,
    WorkspaceHealthResponse,
    WorkspaceTaskResponse,
)
from .service import CollaborationService


router = APIRouter(tags=["collaboration"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _message_response(message) -> CollaborationMessageResponse:
    return CollaborationMessageResponse(
        id=message.id,
        mission_id=message.mission_id,
        task_id=message.task_id,
        decision_id=message.decision_id,
        message_type=message.message_type,
        sender_participant_id=message.sender_participant_id,
        subject=message.subject,
        body=message.body,
        structured_payload=message.structured_payload or {},
        priority=message.priority,
        confidentiality=message.confidentiality,
        requires_acknowledgement=message.requires_acknowledgement,
        body_hash=message.body_hash,
        created_at=message.created_at,
        version_number=message.version_number,
    )


def _inbox_response(item) -> InboxItemResponse:
    return InboxItemResponse(
        id=item.id,
        participant_id=item.participant_id,
        message_id=item.message_id,
        delivery_status=item.delivery_status,
        relevance_score=item.relevance_score,
        delivered_at=item.delivered_at,
        acknowledged_at=item.acknowledged_at,
    )


def _decision_response(decision) -> CollaborationDecisionResponse:
    return CollaborationDecisionResponse(
        id=decision.id,
        mission_id=decision.mission_id,
        decision_key=decision.decision_key,
        title=decision.title,
        summary=decision.summary,
        selected_option=decision.selected_option or {},
        alternatives=decision.alternatives or [],
        rationale=decision.rationale,
        status=decision.status,
        version_number=decision.version_number,
    )


def _review_response(review) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        mission_id=review.mission_id,
        task_id=review.task_id,
        review_type=review.review_type,
        target_type=review.target_type,
        target_id=review.target_id,
        target_hash=review.target_hash,
        requester_participant_id=review.requester_participant_id,
        reviewer_participant_id=review.reviewer_participant_id,
        status=review.status,
        verdict=review.verdict,
    )


def _memory_response(item) -> MemoryItemResponse:
    return MemoryItemResponse(
        id=item.id,
        memory_scope=item.memory_scope,
        scope_reference_id=item.scope_reference_id,
        title=item.title,
        content=item.content,
        lifecycle_status=item.lifecycle_status,
        trust_level=item.trust_level,
        confidence=item.confidence,
        content_hash=item.content_hash,
        created_at=item.created_at,
    )


def _team_response(db: Session, team) -> TeamResponse:
    member_count = db.query(ArceusCollaborationTeamMember).filter(ArceusCollaborationTeamMember.tenant_id == team.tenant_id, ArceusCollaborationTeamMember.team_id == team.id, ArceusCollaborationTeamMember.status == "active").count()
    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        lead_user_id=team.lead_user_id,
        status=team.status,
        member_count=member_count,
        created_at=team.created_at,
    )


def _project_workspace_response(db: Session, project) -> ProjectWorkspaceResponse:
    team_count = db.query(ArceusProjectMember).filter(ArceusProjectMember.tenant_id == project.tenant_id, ArceusProjectMember.project_id == project.id, ArceusProjectMember.team_id.isnot(None), ArceusProjectMember.status == "active").count()
    member_count = db.query(ArceusProjectMember).filter(ArceusProjectMember.tenant_id == project.tenant_id, ArceusProjectMember.project_id == project.id, ArceusProjectMember.status == "active").count()
    open_task_count = db.query(ArceusCollaborationTask).filter(ArceusCollaborationTask.tenant_id == project.tenant_id, ArceusCollaborationTask.project_id == project.id, ArceusCollaborationTask.status != "done").count()
    knowledge_page_count = db.query(ArceusKnowledgePage).filter(ArceusKnowledgePage.tenant_id == project.tenant_id, ArceusKnowledgePage.project_id == project.id, ArceusKnowledgePage.status != "archived").count()
    unresolved_discussion_count = db.query(ArceusDiscussionThread).filter(ArceusDiscussionThread.tenant_id == project.tenant_id, ArceusDiscussionThread.project_id == project.id, ArceusDiscussionThread.status == "open").count()
    return ProjectWorkspaceResponse(
        id=project.id,
        organization_id=(project.settings or {}).get("organization_id"),
        name=project.name,
        slug=project.slug,
        description=project.description,
        status=project.status,
        team_count=team_count,
        member_count=member_count,
        open_task_count=open_task_count,
        knowledge_page_count=knowledge_page_count,
        unresolved_discussion_count=unresolved_discussion_count,
        created_at=project.created_at,
    )


def _task_response(task) -> WorkspaceTaskResponse:
    return WorkspaceTaskResponse(
        id=task.id,
        project_id=task.project_id,
        milestone_id=task.milestone_id,
        mission_id=task.mission_id,
        title=task.title,
        description=task.description,
        assignee_user_id=task.assignee_user_id,
        assignee_participant_id=task.assignee_participant_id,
        priority=task.priority,
        status=task.status,
        dependencies=task.dependencies or [],
        acceptance_criteria=task.acceptance_criteria or [],
        created_at=task.created_at,
    )


def _presence_response(item) -> PresenceResponse:
    return PresenceResponse(
        id=item.id,
        user_id=item.user_id,
        participant_id=item.participant_id,
        project_id=item.project_id,
        mission_id=item.mission_id,
        status=item.status,
        activity=item.activity,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        last_seen_at=item.last_seen_at,
    )


def _comment_response(item) -> CommentResponse:
    return CommentResponse(
        id=item.id,
        thread_id=item.thread_id,
        project_id=item.project_id,
        mission_id=item.mission_id,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        author_user_id=item.author_user_id,
        author_participant_id=item.author_participant_id,
        body=item.body,
        mentions=item.mentions or [],
        body_hash=item.body_hash,
        status=item.status,
        created_at=item.created_at,
    )


def _knowledge_page_response(item) -> KnowledgePageResponse:
    return KnowledgePageResponse(
        id=item.id,
        project_id=item.project_id,
        title=item.title,
        slug=item.slug,
        page_type=item.page_type,
        markdown=item.markdown,
        status=item.status,
        freshness_status=item.freshness_status,
        content_hash=item.content_hash,
        created_at=item.created_at,
    )


def _notification_response(item) -> NotificationResponse:
    return NotificationResponse(
        id=item.id,
        recipient_user_id=item.recipient_user_id,
        recipient_participant_id=item.recipient_participant_id,
        notification_type=item.notification_type,
        title=item.title,
        body=item.body,
        channels=item.channels or [],
        status=item.status,
        resource_type=item.resource_type,
        resource_id=item.resource_id,
        created_at=item.created_at,
    )


@router.post("/api/v1/collaboration/teams", status_code=status.HTTP_201_CREATED)
def create_team(request_body: CreateTeamRequest, request: Request, context: RequestContext = Depends(require_permission("collaboration.manage")), db: Session = Depends(get_db)):
    uow = _uow(db)
    team = CollaborationService(uow).create_team(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_team_response(db, team).model_dump(mode="json"), request)


@router.get("/api/v1/collaboration/teams")
def list_teams(request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusCollaborationTeam).filter(ArceusCollaborationTeam.tenant_id == context.tenant_id).order_by(ArceusCollaborationTeam.created_at.desc()).all()
    return collection_response([_team_response(db, row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/collaboration/teams/{team_id}/members", status_code=status.HTTP_201_CREATED)
def add_team_member(team_id: UUID, request_body: AddTeamMemberRequest, request: Request, context: RequestContext = Depends(require_permission("collaboration.manage")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).add_team_member(tenant_id=context.tenant_id, team_id=team_id, **request_body.model_dump())
    uow.commit()
    return api_response({"id": str(item.id), "team_id": str(item.team_id), "role_key": item.role_key, "status": item.status}, request)


@router.post("/api/v1/projects", status_code=status.HTTP_201_CREATED)
def create_collaborative_project(request_body: CreateCollaborativeProjectRequest, request: Request, context: RequestContext = Depends(require_permission("project.create")), db: Session = Depends(get_db)):
    uow = _uow(db)
    created_by = request_body.created_by or context.user_id
    payload = request_body.model_dump()
    payload["created_by"] = created_by
    project = CollaborationService(uow).create_project_workspace(tenant_id=context.tenant_id, **payload)
    uow.commit()
    return api_response(_project_workspace_response(db, project).model_dump(mode="json"), request)


@router.get("/api/v1/projects")
def list_collaborative_projects(request: Request, context: RequestContext = Depends(require_permission("project.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusProject).filter(ArceusProject.tenant_id == context.tenant_id, ArceusProject.status != "archived").order_by(ArceusProject.updated_at.desc()).limit(100).all()
    return collection_response([_project_workspace_response(db, row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/projects/{project_id}/members", status_code=status.HTTP_201_CREATED)
def add_project_member(project_id: UUID, request_body: ProjectMemberRequest, request: Request, context: RequestContext = Depends(require_permission("project.manage")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).add_project_member(tenant_id=context.tenant_id, project_id=project_id, **request_body.model_dump())
    uow.commit()
    return api_response({"id": str(item.id), "project_id": str(item.project_id), "role_key": item.role_key, "status": item.status}, request)


@router.post("/api/v1/milestones", status_code=status.HTTP_201_CREATED)
def create_milestone(request_body: CreateMilestoneRequest, request: Request, context: RequestContext = Depends(require_permission("project.manage")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).create_milestone(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response({"id": str(item.id), "project_id": str(item.project_id), "title": item.title, "status": item.status}, request)


@router.post("/api/v1/tasks", status_code=status.HTTP_201_CREATED)
def create_workspace_task(request_body: CreateWorkspaceTaskRequest, request: Request, context: RequestContext = Depends(require_permission("task.create")), db: Session = Depends(get_db)):
    uow = _uow(db)
    task = CollaborationService(uow).create_workspace_task(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_task_response(task).model_dump(mode="json"), request)


@router.get("/api/v1/tasks")
def list_workspace_tasks(request: Request, context: RequestContext = Depends(require_permission("task.view")), project_id: UUID | None = Query(default=None), status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db)):
    query = db.query(ArceusCollaborationTask).filter(ArceusCollaborationTask.tenant_id == context.tenant_id)
    if project_id:
        query = query.filter(ArceusCollaborationTask.project_id == project_id)
    if status_filter:
        query = query.filter(ArceusCollaborationTask.status == status_filter)
    rows = query.order_by(ArceusCollaborationTask.created_at.desc()).limit(200).all()
    return collection_response([_task_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/presence")
def upsert_presence(request_body: UpsertPresenceRequest, request: Request, context: RequestContext = Depends(require_permission("collaboration.presence")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).upsert_presence(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_presence_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/presence")
def list_presence(request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), project_id: UUID | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(ArceusPresenceSession).filter(ArceusPresenceSession.tenant_id == context.tenant_id, ArceusPresenceSession.status != "offline")
    if project_id:
        query = query.filter(ArceusPresenceSession.project_id == project_id)
    rows = query.order_by(ArceusPresenceSession.last_seen_at.desc()).limit(100).all()
    return collection_response([_presence_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/discussions", status_code=status.HTTP_201_CREATED)
def create_discussion(request_body: CreateDiscussionThreadRequest, request: Request, context: RequestContext = Depends(require_permission("collaboration.message")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).create_thread(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response({"id": str(item.id), "title": item.title, "status": item.status, "resource_type": item.resource_type, "resource_id": str(item.resource_id) if item.resource_id else None}, request)


@router.post("/api/v1/comments", status_code=status.HTTP_201_CREATED)
def add_comment(request_body: CreateCommentRequest, request: Request, context: RequestContext = Depends(require_permission("collaboration.message")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).add_comment(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_comment_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/comments")
def list_comments(request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), resource_type: str | None = None, resource_id: UUID | None = None, db: Session = Depends(get_db)):
    query = db.query(ArceusComment).filter(ArceusComment.tenant_id == context.tenant_id, ArceusComment.status != "deleted")
    if resource_type:
        query = query.filter(ArceusComment.resource_type == resource_type)
    if resource_id:
        query = query.filter(ArceusComment.resource_id == resource_id)
    rows = query.order_by(ArceusComment.created_at.desc()).limit(100).all()
    return collection_response([_comment_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/knowledge", status_code=status.HTTP_201_CREATED)
def upsert_knowledge_page(request_body: UpsertKnowledgePageRequest, request: Request, context: RequestContext = Depends(require_permission("knowledge.create")), db: Session = Depends(get_db)):
    uow = _uow(db)
    item = CollaborationService(uow).upsert_knowledge_page(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_knowledge_page_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/knowledge")
def list_knowledge_pages(request: Request, context: RequestContext = Depends(require_permission("knowledge.view")), project_id: UUID | None = Query(default=None), q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(ArceusKnowledgePage).filter(ArceusKnowledgePage.tenant_id == context.tenant_id, ArceusKnowledgePage.status != "archived")
    if project_id:
        query = query.filter(ArceusKnowledgePage.project_id == project_id)
    if q:
        query = query.filter(ArceusKnowledgePage.title.ilike(f"%{q}%"))
    rows = query.order_by(ArceusKnowledgePage.updated_at.desc()).limit(100).all()
    return collection_response([_knowledge_page_response(row).model_dump(mode="json") for row in rows], request)


@router.get("/api/v1/activity")
def list_activity(request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), project_id: UUID | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(ArceusActivityEvent).filter(ArceusActivityEvent.tenant_id == context.tenant_id)
    if project_id:
        query = query.filter(ArceusActivityEvent.project_id == project_id)
    rows = query.order_by(ArceusActivityEvent.occurred_at.desc()).limit(100).all()
    return collection_response([{"id": str(row.id), "event_type": row.event_type, "resource_type": row.resource_type, "resource_id": str(row.resource_id) if row.resource_id else None, "message": row.message, "occurred_at": row.occurred_at.isoformat()} for row in rows], request)


@router.get("/api/v1/notifications")
def list_notifications(request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), status_filter: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db)):
    query = db.query(ArceusNotification).filter(ArceusNotification.tenant_id == context.tenant_id)
    if status_filter:
        query = query.filter(ArceusNotification.status == status_filter)
    rows = query.order_by(ArceusNotification.created_at.desc()).limit(100).all()
    return collection_response([_notification_response(row).model_dump(mode="json") for row in rows], request)


@router.get("/api/v1/projects/{project_id}/health")
def workspace_health(project_id: UUID, request: Request, context: RequestContext = Depends(require_permission("collaboration.view")), db: Session = Depends(get_db)):
    uow = _uow(db)
    health = CollaborationService(uow).workspace_health(tenant_id=context.tenant_id, project_id=project_id)
    return api_response(WorkspaceHealthResponse(**health).model_dump(mode="json"), request)


@router.post("/api/v1/missions/{mission_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    mission_id: UUID,
    request_body: SendCollaborationMessageRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.message")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    message = CollaborationService(uow).send_message(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        sender_participant_id=request_body.sender_participant_id,
        message_type=request_body.message_type,
        subject=request_body.subject,
        body=request_body.body,
        structured_payload=request_body.structured_payload,
        recipient_participant_ids=request_body.recipient_participant_ids,
        topic_keys=request_body.topic_keys,
        workflow_id=request_body.workflow_id,
        task_id=request_body.task_id,
        decision_id=request_body.decision_id,
        priority=request_body.priority,
        confidentiality=request_body.confidentiality,
        requires_acknowledgement=request_body.requires_acknowledgement,
        response_required_by=request_body.response_required_by,
        correlation_id=context.correlation_id,
        causation_id=request_body.causation_id,
    )
    uow.commit()
    return api_response(_message_response(message).model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/messages")
def list_messages(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.view")),
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusCollaborationMessage).filter(
        ArceusCollaborationMessage.tenant_id == context.tenant_id,
        ArceusCollaborationMessage.mission_id == mission_id,
    )
    if task_id:
        query = query.filter(ArceusCollaborationMessage.task_id == task_id)
    rows = query.order_by(ArceusCollaborationMessage.created_at.desc()).limit(limit).all()
    return collection_response([_message_response(item).model_dump(mode="json") for item in rows], request)


@router.get("/api/v1/participants/{participant_id}/inbox")
def list_participant_inbox(
    participant_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.view")),
    delivery_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusParticipantInboxItem).filter(
        ArceusParticipantInboxItem.tenant_id == context.tenant_id,
        ArceusParticipantInboxItem.participant_id == participant_id,
    )
    if delivery_status:
        query = query.filter(ArceusParticipantInboxItem.delivery_status == delivery_status)
    rows = query.order_by(ArceusParticipantInboxItem.delivered_at.desc()).limit(limit).all()
    return collection_response([_inbox_response(item).model_dump(mode="json") for item in rows], request)


@router.post("/api/v1/inbox/{item_id}/acknowledge")
def acknowledge_inbox_item(
    item_id: UUID,
    request: Request,
    participant_id: UUID = Query(),
    context: RequestContext = Depends(require_permission("collaboration.message")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).acknowledge_inbox_item(tenant_id=context.tenant_id, item_id=item_id, participant_id=participant_id)
    uow.commit()
    return api_response(_inbox_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/missions/{mission_id}/collaboration-decisions", status_code=status.HTTP_201_CREATED)
def create_decision(
    mission_id: UUID,
    request_body: CreateDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    decision = CollaborationService(uow).create_decision(tenant_id=context.tenant_id, mission_id=mission_id, **request_body.model_dump())
    uow.commit()
    return api_response(_decision_response(decision).model_dump(mode="json"), request)


@router.post("/api/v1/collaboration-decisions/{decision_id}/resolve")
def resolve_decision(
    decision_id: UUID,
    request_body: ResolveDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.approve")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    decision = CollaborationService(uow).resolve_decision(tenant_id=context.tenant_id, decision_id=decision_id, **request_body.model_dump())
    uow.commit()
    return api_response(_decision_response(decision).model_dump(mode="json"), request)


@router.post("/api/v1/reviews", status_code=status.HTTP_201_CREATED)
def request_review(
    request_body: CreateReviewRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("review.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    payload = request_body.model_dump()
    mission_id = payload.pop("mission_id")
    review = CollaborationService(uow).request_review(tenant_id=context.tenant_id, mission_id=mission_id, **payload)
    uow.commit()
    return api_response(_review_response(review).model_dump(mode="json"), request)


@router.post("/api/v1/reviews/{review_id}/complete")
def complete_review(
    review_id: UUID,
    request_body: CompleteReviewRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("review.complete")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    review = CollaborationService(uow).complete_review(tenant_id=context.tenant_id, review_id=review_id, **request_body.model_dump())
    uow.commit()
    return api_response(_review_response(review).model_dump(mode="json"), request)


@router.post("/api/v1/memory/proposals", status_code=status.HTTP_201_CREATED)
def propose_memory(
    request_body: MemoryProposalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).propose_memory(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_memory_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/memory/{memory_id}/approve")
def approve_memory(
    memory_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.approve")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).approve_memory(tenant_id=context.tenant_id, memory_id=memory_id)
    uow.commit()
    return api_response(_memory_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/memory/search")
def search_memory(
    request: Request,
    context: RequestContext = Depends(require_permission("memory.view")),
    q: str = Query(default="", max_length=240),
    memory_scope: str | None = Query(default=None),
    authoritative_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusMemoryItem).filter(ArceusMemoryItem.tenant_id == context.tenant_id)
    if memory_scope:
        query = query.filter(ArceusMemoryItem.memory_scope == memory_scope)
    if authoritative_only:
        query = query.filter(ArceusMemoryItem.lifecycle_status == "approved")
    if q:
        query = query.filter(ArceusMemoryItem.title.ilike(f"%{q}%"))
    rows = query.order_by(ArceusMemoryItem.created_at.desc()).limit(limit).all()
    return collection_response([_memory_response(item).model_dump(mode="json") for item in rows], request)
