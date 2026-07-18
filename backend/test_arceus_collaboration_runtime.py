import uuid
from types import SimpleNamespace

import pytest

from services.agent.arceus_runtime.application.errors import RuntimeStateConflict
from services.agent.arceus_runtime.collaboration.service import CollaborationService
from services.shared.arceus_core_models import (
    ArceusCollaborationMessage,
    ArceusDecision,
    ArceusEvent,
    ArceusMemoryItem,
    ArceusParticipant,
    ArceusParticipantInboxItem,
    ArceusReview,
    ArceusTask,
)


class _FakeQuery:
    def __init__(self, rows) -> None:
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, _limit):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class _FakeDb:
    def __init__(self) -> None:
        self.rows = {
            ArceusParticipant: [],
            ArceusCollaborationMessage: [],
            ArceusParticipantInboxItem: [],
            ArceusDecision: [],
            ArceusReview: [],
            ArceusMemoryItem: [],
            ArceusTask: [],
            ArceusEvent: [],
        }

    def add(self, row):
        if getattr(row, "id", None) is None:
            row.id = uuid.uuid4()
        if getattr(row, "version_number", None) is None:
            row.version_number = 1
        if row.__class__ in self.rows:
            self.rows[row.__class__].append(row)

    def flush(self):
        for values in self.rows.values():
            for row in values:
                if getattr(row, "id", None) is None:
                    row.id = uuid.uuid4()
                if getattr(row, "version_number", None) is None:
                    row.version_number = 1

    def query(self, model):
        return _FakeQuery(self.rows.get(model, []))


class _FakeMissions:
    def __init__(self, mission) -> None:
        self.mission = mission

    def get(self, *, tenant_id, mission_id):
        return self.mission


class _FakeDecisions:
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    def get(self, *, tenant_id, decision_id):
        for decision in self.db.rows[ArceusDecision]:
            if decision.id == decision_id:
                return decision
        raise RuntimeStateConflict("Decision not found.")


class _FakeEvents:
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    def append(self, **kwargs):
        event = SimpleNamespace(id=uuid.uuid4(), version_number=1, **kwargs)
        self.db.rows[ArceusEvent].append(event)
        return event


class _FakeUow:
    def __init__(self, mission) -> None:
        self.db = _FakeDb()
        self.missions = _FakeMissions(mission)
        self.decisions = _FakeDecisions(self.db)
        self.events = _FakeEvents(self.db)


def _participant(*, tenant_id, mission_id, role_key, participant_type="ai_specialist", status="available"):
    return ArceusParticipant(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        display_name=role_key,
        role_key=role_key,
        participant_type=participant_type,
        active_mission_ids=[str(mission_id)],
        capabilities=[],
        authorities=[],
        status=status,
    )


def test_message_delivery_routes_relevant_inbox_items_and_events() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(SimpleNamespace(id=mission_id))
    sender = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="backend_engineer")
    reviewer = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="security_reviewer")
    offline = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="qa_reviewer", status="offline")
    uow.db.rows[ArceusParticipant].extend([sender, reviewer, offline])

    message = CollaborationService(uow).send_message(
        tenant_id=tenant_id,
        mission_id=mission_id,
        sender_participant_id=sender.id,
        message_type="risk_alert",
        subject="Auth risk",
        body="Account linking needs review.",
        structured_payload={"risk": "account_linking"},
        recipient_participant_ids=[reviewer.id],
        topic_keys=["risk.security"],
        correlation_id=mission_id,
    )

    assert message.body_hash
    assert len(uow.db.rows[ArceusParticipantInboxItem]) == 1
    assert uow.db.rows[ArceusParticipantInboxItem][0].participant_id == reviewer.id
    assert all(item.participant_id != offline.id for item in uow.db.rows[ArceusParticipantInboxItem])
    assert uow.db.rows[ArceusEvent][-1].event_type == "MESSAGE_CREATED"


def test_message_rejects_raw_secret_without_secret_reference_label() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(SimpleNamespace(id=mission_id))
    sender = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="backend_engineer")
    uow.db.rows[ArceusParticipant].append(sender)

    with pytest.raises(RuntimeStateConflict):
        CollaborationService(uow).send_message(
            tenant_id=tenant_id,
            mission_id=mission_id,
            sender_participant_id=sender.id,
            message_type="finding",
            subject="Secret found",
            body="token=abc123",
            structured_payload={},
            correlation_id=mission_id,
        )


def test_review_request_enforces_independent_reviewer() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(SimpleNamespace(id=mission_id))
    requester = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="backend_engineer")
    uow.db.rows[ArceusParticipant].append(requester)

    with pytest.raises(RuntimeStateConflict):
        CollaborationService(uow).request_review(
            tenant_id=tenant_id,
            mission_id=mission_id,
            requester_participant_id=requester.id,
            reviewer_participant_id=requester.id,
            review_type="security",
            target_type="artifact",
            target_id=uuid.uuid4(),
            target_hash="a" * 64,
        )


def test_high_risk_decision_requires_human_approval_and_preserves_options() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(SimpleNamespace(id=mission_id))
    proposer = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="security_reviewer")
    approver = _participant(tenant_id=tenant_id, mission_id=mission_id, role_key="human_approver", participant_type="human")
    uow.db.rows[ArceusParticipant].extend([proposer, approver])
    service = CollaborationService(uow)

    decision = service.create_decision(
        tenant_id=tenant_id,
        mission_id=mission_id,
        proposer_participant_id=proposer.id,
        decision_key="auth.account_linking",
        decision_type="authentication",
        title="Account linking policy",
        problem_statement="How should matching emails link accounts?",
        risk_level="high",
        options=[
            {"option_key": "explicit_verification", "title": "Explicit verification", "description": "Require proof.", "benefits": ["safe"], "drawbacks": [], "risks": [], "reversibility": "high"},
            {"option_key": "automatic_match", "title": "Automatic match", "description": "Auto-link email.", "benefits": ["fast"], "drawbacks": ["risk"], "risks": ["takeover"], "reversibility": "low"},
        ],
    )

    with pytest.raises(RuntimeStateConflict):
        service.resolve_decision(
            tenant_id=tenant_id,
            decision_id=decision.id,
            selected_option_key="explicit_verification",
            rationale="Safer.",
            approver_participant_id=approver.id,
            human_approved=False,
        )

    resolved = service.resolve_decision(
        tenant_id=tenant_id,
        decision_id=decision.id,
        selected_option_key="explicit_verification",
        rationale="Safer.",
        approver_participant_id=approver.id,
        human_approved=True,
    )

    assert resolved.status == "approved"
    assert resolved.selected_option["option_key"] == "explicit_verification"
    assert len(resolved.alternatives) == 2


def test_memory_requires_evidence_before_authoritative_approval() -> None:
    tenant_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    uow = _FakeUow(SimpleNamespace(id=mission_id))
    service = CollaborationService(uow)
    memory = service.propose_memory(
        tenant_id=tenant_id,
        memory_scope="mission",
        scope_reference_id=mission_id,
        title="Auth policy",
        content="Use explicit verification for account linking.",
        source_type="decision",
        source_ids=[],
        evidence_ids=[],
        sensitivity="mission",
    )

    with pytest.raises(RuntimeStateConflict):
        service.approve_memory(tenant_id=tenant_id, memory_id=memory.id)

    memory.evidence_ids = [str(uuid.uuid4())]
    approved = service.approve_memory(tenant_id=tenant_id, memory_id=memory.id)

    assert approved.lifecycle_status == "approved"
    assert approved.trust_level == "authoritative"
