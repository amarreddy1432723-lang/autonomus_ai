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
    project_id: Optional[UUID] = None
    goal_id: Optional[UUID]
    user_id: UUID
    parent_task_id: Optional[UUID] = None
    status: str
    priority_score: float
    pert_estimate: float
    optimistic_estimate: float
    most_likely_estimate: float
    pessimistic_estimate: float
    est_hours_optimistic: float = 0.0
    est_hours_likely: float = 0.0
    est_hours_pessimistic: float = 0.0
    est_hours_pert: float = 0.0
    est_hours_std_dev: float = 0.0
    actual_hours: float = 0.0
    is_critical_path: bool = False
    float_hours: float = 0.0
    earliest_start_day: Optional[int] = None
    earliest_finish_day: Optional[int] = None
    latest_start_day: Optional[int] = None
    latest_finish_day: Optional[int] = None
    success_criteria: List[str] = Field(default_factory=list)
    execution_result: Dict[str, Any] = Field(default_factory=dict)
    quality_score: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    dependency_ids: List[UUID] = Field(default_factory=list)

    class Config:
        from_attributes = True

# Goal schemas
class GoalBase(BaseModel):
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None

class GoalCreate(GoalBase):
    category: Optional[str] = None
    priority: Optional[int] = None
    success_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)

class ProjectResponse(BaseModel):
    id: UUID
    goal_id: UUID
    user_id: UUID
    title: str
    description: Optional[str] = None
    status: str
    phase_number: int
    milestone: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    progress_pct: float = 0.0
    lead_agent: Optional[str] = None
    dependencies: List[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class GoalResponse(GoalBase):
    id: UUID
    user_id: UUID
    category: str = "general"
    priority: int = 3
    status: str
    priority_score: float
    progress: float
    success_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    progress_pct: float = 0.0
    plan_version: int = 1
    original_plan: Optional[Dict[str, Any]] = None
    current_plan: Optional[Dict[str, Any]] = None
    plan_change_log: List[Dict[str, Any]] = Field(default_factory=list)
    estimated_hours_total: Optional[float] = None
    actual_hours_total: Optional[float] = None
    estimation_accuracy_pct: Optional[float] = None
    reflection_summary: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    projects: List[ProjectResponse] = Field(default_factory=list)
    tasks: List[TaskResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

class ReplanRequest(BaseModel):
    trigger: str = "manual_review"
    strategy: str = "hybrid"

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
