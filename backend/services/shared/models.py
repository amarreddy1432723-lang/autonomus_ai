import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Integer, JSON, Boolean, Text, Table, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    auth_provider = Column(String(100), default="email")
    auth_provider_id = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    timezone = Column(String(100), default="UTC")
    locale = Column(String(50), default="en")
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="user", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    integrations = relationship("Integration", back_populates="user", cascade="all, delete-orphan")
    task_executions = relationship("TaskExecution", back_populates="user", cascade="all, delete-orphan")

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    autonomy_level = Column(String(50), default="observer") 
    comm_style = Column(String(50), default="bullets") 
    trust_rules = Column(JSON, default=list) 
    communication_style = Column(JSON, default=dict)
    work_patterns = Column(JSON, default=dict)
    decision_style = Column(JSON, default=dict)
    domain_expertise = Column(JSON, default=list)
    tool_preferences = Column(JSON, default=dict)
    estimation_biases = Column(JSON, default=dict)
    feedback_patterns = Column(JSON, default=dict)
    model_version = Column(Integer, default=1)
    model_confidence = Column(Float, default=0.1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="profile")

class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), default="general")
    priority = Column(Integer, default=3)
    status = Column(String(50), default="active") 
    priority_score = Column(Float, default=0.0)
    deadline = Column(DateTime(timezone=True), nullable=True)
    success_criteria = Column(JSON, default=list)
    constraints = Column(JSON, default=list)
    assumptions = Column(JSON, default=list)
    progress_pct = Column(Float, default=0.0)
    progress = Column(Float, default=0.0) 
    plan_version = Column(Integer, default=1)
    original_plan = Column(JSON, nullable=True)
    current_plan = Column(JSON, nullable=True)
    plan_change_log = Column(JSON, default=list)
    estimated_hours_total = Column(Float, nullable=True)
    actual_hours_total = Column(Float, nullable=True)
    estimation_accuracy_pct = Column(Float, nullable=True)
    reflection_summary = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="goals")
    projects = relationship("Project", back_populates="goal", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    phase_number = Column(Integer, default=1)
    milestone = Column(String(255), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    progress_pct = Column(Float, default=0.0)
    lead_agent = Column(String(100), nullable=True)
    dependencies = Column(JSON, default=list) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="projects")
    goal = relationship("Goal", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

task_dependencies = Table(
    "task_dependencies",
    Base.metadata,
    Column("task_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("depends_on_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True) 
    goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="queued") 
    priority_score = Column(Float, default=0.0)
    
    pert_estimate = Column(Float, default=0.0) 
    optimistic_estimate = Column(Float, default=0.0)
    most_likely_estimate = Column(Float, default=0.0)
    pessimistic_estimate = Column(Float, default=0.0)
    
    est_hours_optimistic = Column(Float, default=0.0)
    est_hours_likely = Column(Float, default=0.0)
    est_hours_pessimistic = Column(Float, default=0.0)
    est_hours_pert = Column(Float, default=0.0)
    est_hours_std_dev = Column(Float, default=0.0)
    
    actual_hours = Column(Float, default=0.0)
    
    is_critical_path = Column(Boolean, default=False)
    float_hours = Column(Float, default=0.0)
    earliest_start_day = Column(Integer, nullable=True)
    earliest_finish_day = Column(Integer, nullable=True)
    latest_start_day = Column(Integer, nullable=True)
    latest_finish_day = Column(Integer, nullable=True)

    assigned_agent = Column(String(100), nullable=True)
    success_criteria = Column(JSON, default=list)
    execution_result = Column(JSON, default=dict)
    quality_score = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    due_date = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="tasks")
    goal = relationship("Goal", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    executions = relationship("TaskExecution", back_populates="task", cascade="all, delete-orphan")
    
    dependencies = relationship(
        "Task",
        secondary=task_dependencies,
        primaryjoin="Task.id==task_dependencies.c.task_id",
        secondaryjoin="Task.id==task_dependencies.c.depends_on_id",
        backref="dependents"
    )

    @property
    def dependency_ids(self) -> list[uuid.UUID]:
        return [d.id for d in self.dependencies]

class TaskExecution(Base):
    __tablename__ = "task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_type = Column(String(100), nullable=False)
    attempt_number = Column(Integer, default=1)
    status = Column(String(50), default="running") 
    
    model_used = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 6), default=0.0)
    
    tool_calls = Column(JSON, default=list)
    
    tool_name = Column(String(100), nullable=False) 
    tool_input = Column(Text, nullable=True)        
    tool_output = Column(Text, nullable=True)       
    output_text = Column(Text, nullable=True)
    output_data = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)
    
    success = Column(Boolean, default=True) 
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", back_populates="executions")
    user = relationship("User", back_populates="task_executions")

class Memory(Base):
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(100), nullable=False) 
    memory_type = Column(String(100), default="fact") 
    content = Column(Text, nullable=False)
    vector = Column(Vector(1536), nullable=True) 
    content_vector = Column(Vector(1536), nullable=True) 
    source = Column(String(100), default="ai_extracted")
    source_session_id = Column(UUID(as_uuid=True), nullable=True)
    source_url = Column(String(500), nullable=True)
    confidence = Column(Float, default=0.8)
    importance = Column(Integer, default=5) 
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    tags = Column(JSON, default=list) 
    related_memory_ids = Column(JSON, default=list) 
    is_archived = Column(Boolean, default=False)
    is_superseded = Column(Boolean, default=False)
    superseded_by = Column(UUID(as_uuid=True), ForeignKey("memories.id"), nullable=True)
    compressed_from = Column(JSON, default=list)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    meta_data = Column(JSON, default=dict) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="memories")

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    requested_by_agent = Column(String(100), default="execution")
    action_description = Column(Text, default="")
    action_payload = Column(JSON, default=dict)
    action_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False) 
    risk_level = Column(String(50), default="low") 
    risk_reasoning = Column(Text, default="")
    if_approved = Column(Text, nullable=True)
    if_rejected = Column(Text, nullable=True)
    alternatives = Column(JSON, default=list)
    status = Column(String(50), default="pending") 
    decided_by = Column(String(50), nullable=True)
    user_response = Column(Text, nullable=True)
    modified_payload = Column(JSON, nullable=True)
    decision_reason = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    timeout_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True) 
    notification_ids = Column(JSON, default=list)

    user = relationship("User", back_populates="approvals")

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    schedule_type = Column(String(50), nullable=False) 
    cron_expression = Column(String(100), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, default=0)
    max_runs = Column(Integer, nullable=True)
    trigger_type = Column(String(50), nullable=False) 
    trigger_payload = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="schedules")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    priority = Column(Integer, default=2) 
    channels = Column(JSON, default=lambda: ["in_app"])
    status = Column(String(50), default="pending") 
    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")

class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(100), nullable=False)
    status = Column(String(50), default="active")
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(JSON, default=list)
    provider_user_id = Column(String(255), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="integrations")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=False) 
    session_id = Column(UUID(as_uuid=True), nullable=True)
    event_type = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    actor_type = Column(String(50), nullable=False)
    actor_id = Column(String(255), nullable=True)
    action = Column(Text, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    metadata_json = Column(JSON, default=dict)
    ip_address = Column(String(45), nullable=True) 
    user_agent = Column(Text, nullable=True)
    checksum = Column(String(255), nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
