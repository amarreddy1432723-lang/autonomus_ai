from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# Task schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_agent: Optional[str] = None
    due_date: Optional[datetime] = None

class TaskCreate(TaskBase):
    goal_id: Optional[UUID] = None

class TaskUpdate(BaseModel):
    status: Optional[str] = None # queued, in_progress, waiting_approval, done, failed, blocked
    priority_score: Optional[float] = None

class TaskResponse(TaskBase):
    id: UUID
    goal_id: Optional[UUID]
    user_id: UUID
    status: str
    priority_score: float
    pert_estimate: float
    optimistic_estimate: float
    most_likely_estimate: float
    pessimistic_estimate: float
    created_at: datetime
    updated_at: datetime
    dependency_ids: List[UUID] = []

    class Config:
        from_attributes = True

# Goal schemas
class GoalBase(BaseModel):
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None

class GoalCreate(GoalBase):
    pass

class GoalResponse(GoalBase):
    id: UUID
    user_id: UUID
    status: str
    priority_score: float
    progress: float
    created_at: datetime
    updated_at: datetime
    tasks: List[TaskResponse] = []

    class Config:
        from_attributes = True

# Approval schemas
class ApprovalResponse(BaseModel):
    id: UUID
    user_id: UUID
    action_type: str
    payload: Dict[str, Any]
    status: str
    requested_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True

class ApprovalResolve(BaseModel):
    status: str # approved, rejected

class ScheduleCreate(BaseModel):
    task_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    title: str
    schedule_type: str
    cron_expression: Optional[str] = None
    next_run_at: datetime
    trigger_type: str
    trigger_payload: dict = {}

class ScheduleResponse(BaseModel):
    id: UUID
    task_id: Optional[UUID]
    goal_id: Optional[UUID]
    title: str
    schedule_type: str
    cron_expression: Optional[str]
    next_run_at: datetime
    last_run_at: Optional[datetime]
    run_count: int
    max_runs: Optional[int]
    trigger_type: str
    trigger_payload: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class GraphQLQuery(BaseModel):
    query: str
    variables: Optional[Dict[str, Any]] = None
