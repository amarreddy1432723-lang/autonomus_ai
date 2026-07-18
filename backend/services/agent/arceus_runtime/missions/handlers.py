from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from services.shared.arceus_core_models import ArceusMission

from ..application.errors import ClarificationInvalid, MissionStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import MissionClarificationResponse, MissionDetailResponse, MissionEventResponse, MissionOperationResponse, MissionProgressResponse, MissionSummaryResponse
from .commands import CreateMissionCommand, MissionTransitionCommand, SubmitClarificationsCommand
from .domain import EVENT_BY_ACTION, TOPIC_BY_ACTION, transition_mission


def mission_summary(mission: ArceusMission) -> MissionSummaryResponse:
    return MissionSummaryResponse(
        id=mission.id,
        project_id=mission.project_id,
        title=mission.title,
        objective=mission.objective,
        status=mission.status,
        risk_level=mission.risk_level,
        priority=mission.priority,
        current_version=mission.version_number,
        maximum_budget_amount=mission.maximum_budget_amount,
        actual_cost_amount=mission.actual_cost_amount or Decimal("0"),
        created_at=mission.created_at,
        updated_at=mission.updated_at,
        version_number=mission.version_number,
    )


def mission_progress(status: str) -> MissionProgressResponse:
    if status == "completed":
        return MissionProgressResponse(percent=100, status=status)
    if status in {"running", "reviewing", "verifying"}:
        return MissionProgressResponse(percent=25, status=status)
    if status in {"ready", "awaiting_plan_approval"}:
        return MissionProgressResponse(percent=10, status=status)
    if status in {"compiling", "compiled", "organizing"}:
        return MissionProgressResponse(percent=5, status=status)
    return MissionProgressResponse(percent=0, status=status)


class CreateMissionHandler:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: CreateMissionCommand) -> MissionSummaryResponse:
        existing = self.uow.idempotency.get(
            tenant_id=command.tenant_id,
            scope="mission.create",
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            return MissionSummaryResponse(**self.uow.idempotency.resolve_existing(existing, command.request_hash))

        self.uow.projects.get(tenant_id=command.tenant_id, project_id=command.project_id)
        self.uow.projects.get_repositories(
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            repository_ids=list(command.repository_ids),
        )

        mission = ArceusMission(
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            created_by=command.mission_owner_id,
            title=command.title or command.objective.strip()[:120],
            objective=command.objective,
            status="draft",
            risk_level="medium",
            priority=command.priority,
            maximum_budget_amount=command.maximum_budget_amount,
            budget_currency=command.budget_currency.upper(),
        )
        self.uow.missions.add(mission)
        self.uow.db.flush()

        for repository_id in command.repository_ids:
            self.uow.missions.add_repository_scope(
                tenant_id=command.tenant_id,
                mission_id=mission.id,
                repository_id=repository_id,
            )
        for index, statement in enumerate(command.constraints, start=1):
            self.uow.missions.add_constraint(
                tenant_id=command.tenant_id,
                mission_id=mission.id,
                key=f"constraint_{index}",
                statement=statement,
            )
        for index, statement in enumerate(command.desired_outcomes, start=1):
            self.uow.missions.add_success_criterion(
                tenant_id=command.tenant_id,
                mission_id=mission.id,
                key=f"outcome_{index}",
                statement=statement,
            )

        event = self.uow.events.append(
            tenant_id=command.tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=mission.version_number,
            event_type="MISSION_CREATED",
            actor_type="human",
            actor_id=str(command.actor_id),
            payload={
                "mission_id": str(mission.id),
                "project_id": str(mission.project_id),
                "title": mission.title,
                "repository_ids": [str(item) for item in command.repository_ids],
            },
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
        )
        self.uow.outbox.add_from_event(event, topic="arceus.mission.created")
        response = mission_summary(mission)
        response_payload = response.model_dump(mode="json")
        self.uow.idempotency.complete(
            tenant_id=command.tenant_id,
            scope="mission.create",
            idempotency_key=command.idempotency_key,
            request_hash=command.request_hash,
            response_payload=response_payload,
        )
        self.uow.audit.record(
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            action="mission.create",
            resource_type="mission",
            resource_id=mission.id,
            result="success",
            metadata={"correlation_id": str(command.correlation_id)},
        )
        self.uow.commit()
        return response


class TransitionMissionHandler:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: MissionTransitionCommand) -> MissionOperationResponse:
        scope = f"mission.{command.action}"
        existing = self.uow.idempotency.get(
            tenant_id=command.tenant_id,
            scope=scope,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            return MissionOperationResponse(**self.uow.idempotency.resolve_existing(existing, command.request_hash))

        mission = self.uow.missions.get(tenant_id=command.tenant_id, mission_id=command.mission_id)
        self.uow.missions.require_version(mission, command.expected_version)
        previous_status, target_status = transition_mission(mission, command.action)
        operation_id = self.uow.new_id()
        event = self.uow.events.append(
            tenant_id=command.tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=mission.version_number,
            event_type=EVENT_BY_ACTION[command.action],
            actor_type="human",
            actor_id=str(command.actor_id),
            payload={
                "mission_id": str(mission.id),
                "previous_status": previous_status,
                "status": target_status,
                "operation_id": str(operation_id),
                "reason": command.reason,
            },
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
        )
        self.uow.outbox.add_from_event(event, topic=TOPIC_BY_ACTION[command.action])
        response = MissionOperationResponse(
            mission_id=mission.id,
            status=mission.status,
            previous_status=previous_status,
            version_number=mission.version_number,
            operation_id=operation_id,
        )
        self.uow.idempotency.complete(
            tenant_id=command.tenant_id,
            scope=scope,
            idempotency_key=command.idempotency_key,
            request_hash=command.request_hash,
            response_payload=response.model_dump(mode="json"),
        )
        self.uow.audit.record(
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            action=scope,
            resource_type="mission",
            resource_id=mission.id,
            result="success",
            metadata={"correlation_id": str(command.correlation_id), "previous_status": previous_status, "status": target_status},
        )
        self.uow.commit()
        return response


class MissionQueryHandler:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def list(self, *, tenant_id: UUID, project_id: UUID | None, status: str | None, limit: int) -> list[MissionSummaryResponse]:
        return [mission_summary(item) for item in self.uow.missions.list(tenant_id=tenant_id, project_id=project_id, status=status, limit=limit)]

    def get(self, *, tenant_id: UUID, mission_id: UUID) -> MissionDetailResponse:
        mission = self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        events = self.uow.events.list_for_mission(tenant_id=tenant_id, mission_id=mission_id, limit=20)
        return MissionDetailResponse(
            id=mission.id,
            project_id=mission.project_id,
            title=mission.title,
            objective=mission.objective,
            status=mission.status,
            risk_level=mission.risk_level,
            priority=mission.priority,
            current_version=mission.version_number,
            progress=mission_progress(mission.status),
            latest_events=[
                MissionEventResponse(
                    id=event.id,
                    event_type=event.event_type,
                    aggregate_version=event.aggregate_version,
                    payload=event.payload,
                    occurred_at=event.occurred_at,
                )
                for event in reversed(events)
            ],
            maximum_budget_amount=mission.maximum_budget_amount,
            actual_cost_amount=mission.actual_cost_amount or Decimal("0"),
            created_at=mission.created_at,
            updated_at=mission.updated_at,
            version_number=mission.version_number,
        )

    def clarifications(self, *, tenant_id: UUID, mission_id: UUID) -> list[MissionClarificationResponse]:
        self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        return [
            MissionClarificationResponse(
                id=item.id,
                question=item.question,
                impact_level="high" if "material" in (item.risk_if_unanswered or "").lower() else "medium",
                status=item.status,
                assumption=None,
                answer=item.answer,
            )
            for item in self.uow.missions.unknowns(tenant_id=tenant_id, mission_id=mission_id)
        ]


class SubmitClarificationsHandler:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: SubmitClarificationsCommand) -> MissionOperationResponse:
        existing = self.uow.idempotency.get(
            tenant_id=command.tenant_id,
            scope="mission.clarify",
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            return MissionOperationResponse(**self.uow.idempotency.resolve_existing(existing, command.request_hash))

        mission = self.uow.missions.get(tenant_id=command.tenant_id, mission_id=command.mission_id)
        self.uow.missions.require_version(mission, command.expected_version)
        if mission.status != "clarification_required":
            raise MissionStateConflict(
                "Mission clarifications can only be submitted while clarification is required.",
                details={"current_state": mission.status},
            )

        answer_map = {unknown_id: answer.strip() for unknown_id, answer in command.answers}
        unknowns = self.uow.missions.get_unknowns_by_ids(
            tenant_id=command.tenant_id,
            mission_id=command.mission_id,
            unknown_ids=list(answer_map.keys()),
        )
        if len(unknowns) != len(answer_map):
            raise ClarificationInvalid("One or more clarification IDs do not belong to this mission.")
        for unknown in unknowns:
            if unknown.status != "open":
                raise ClarificationInvalid("Clarification has already been answered.", details={"unknown_id": str(unknown.id)})
            unknown.answer = answer_map[unknown.id]
            unknown.status = "answered"

        previous_status = mission.status
        mission.status = "compiling"
        mission.version_number = int(mission.version_number) + 1
        operation_id = self.uow.new_id()
        event = self.uow.events.append(
            tenant_id=command.tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=mission.version_number,
            event_type="MISSION_CLARIFICATION_SUBMITTED",
            actor_type="human",
            actor_id=str(command.actor_id),
            payload={
                "mission_id": str(mission.id),
                "previous_status": previous_status,
                "status": mission.status,
                "answered_unknown_ids": [str(item.id) for item in unknowns],
                "operation_id": str(operation_id),
            },
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
        )
        self.uow.outbox.add_from_event(event, topic="arceus.mission.compilation.requested")
        response = MissionOperationResponse(
            mission_id=mission.id,
            status=mission.status,
            previous_status=previous_status,
            version_number=mission.version_number,
            operation_id=operation_id,
        )
        self.uow.idempotency.complete(
            tenant_id=command.tenant_id,
            scope="mission.clarify",
            idempotency_key=command.idempotency_key,
            request_hash=command.request_hash,
            response_payload=response.model_dump(mode="json"),
        )
        self.uow.audit.record(
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            action="mission.clarify",
            resource_type="mission",
            resource_id=mission.id,
            result="success",
            metadata={"answered_unknown_ids": [str(item.id) for item in unknowns]},
        )
        self.uow.commit()
        return response
