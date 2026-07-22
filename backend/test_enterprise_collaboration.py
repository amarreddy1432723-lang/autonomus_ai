from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.agent.arceus_runtime.application.errors import RuntimeStateConflict
from services.agent.arceus_runtime.collaboration.service import CollaborationService
from services.shared.arceus_core_models import (
    ArceusActivityEvent,
    ArceusCollaborationTask,
    ArceusComment,
    ArceusKnowledgePage,
    ArceusKnowledgeRevision,
    ArceusNotification,
)


def test_create_team_generates_slug_and_activity() -> None:
    db = _FakeDb()
    service = CollaborationService(SimpleNamespace(db=db))
    tenant_id = uuid4()

    team = service.create_team(tenant_id=tenant_id, organization_id=None, name="Platform Engineering", description="Core builders")

    assert team.slug == "platform-engineering"
    assert any(isinstance(item, ArceusActivityEvent) and item.event_type == "team.created" for item in db.added)


def test_comment_extracts_mentions_and_blocks_raw_secrets() -> None:
    db = _FakeDb()
    service = CollaborationService(SimpleNamespace(db=db))

    comment = service.add_comment(
        tenant_id=uuid4(),
        project_id=uuid4(),
        resource_type="task",
        resource_id=uuid4(),
        body="@backend-team please review this with @security.",
    )

    assert isinstance(comment, ArceusComment)
    assert comment.mentions == ["backend-team", "security"]
    assert any(isinstance(item, ArceusNotification) and item.notification_type == "mention" for item in db.added)

    with pytest.raises(RuntimeStateConflict):
        service.add_comment(tenant_id=uuid4(), resource_type="task", body="password=supersecret")


def test_task_assignment_creates_activity_and_notification() -> None:
    db = _FakeDb()
    service = CollaborationService(SimpleNamespace(db=db))
    assignee = uuid4()

    task = service.create_workspace_task(
        tenant_id=uuid4(),
        project_id=uuid4(),
        title="Write deployment runbook",
        description="Document rollback path.",
        assignee_user_id=assignee,
        assignee_participant_id=None,
        priority="high",
        milestone_id=None,
        mission_id=None,
        source_type="user",
        source_id=None,
        acceptance_criteria=["Runbook reviewed"],
        due_at=None,
    )

    assert isinstance(task, ArceusCollaborationTask)
    assert task.status == "backlog"
    assert task.dependencies == []
    assert any(isinstance(item, ArceusActivityEvent) and item.event_type == "task.created" for item in db.added)
    assert any(isinstance(item, ArceusNotification) and item.recipient_user_id == assignee for item in db.added)


def test_knowledge_page_writes_revision_and_blocks_secret_content() -> None:
    db = _FakeDb()
    service = CollaborationService(SimpleNamespace(db=db))

    page = service.upsert_knowledge_page(
        tenant_id=uuid4(),
        project_id=uuid4(),
        title="Deployment Runbook",
        markdown="# Deploy\n\nUse staged rollout.",
        page_type="runbook",
        parent_page_id=None,
        author_user_id=None,
        author_participant_id=None,
        source_ids=[],
        change_summary="Initial runbook",
    )

    assert isinstance(page, ArceusKnowledgePage)
    assert page.slug == "deployment-runbook"
    assert any(isinstance(item, ArceusKnowledgeRevision) and item.revision_number == 1 for item in db.added)

    with pytest.raises(RuntimeStateConflict):
        service.upsert_knowledge_page(tenant_id=uuid4(), project_id=uuid4(), title="Secrets", markdown="token=abc123")


class _Query:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def count(self):
        return 0


class _FakeDb:
    def __init__(self) -> None:
        self.added = []

    def add(self, item) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.added.append(item)

    def flush(self) -> None:
        return None

    def query(self, *args, **kwargs):
        return _Query()
