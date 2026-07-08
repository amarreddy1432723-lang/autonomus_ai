import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Integer, JSON, Boolean, Text, Table, Numeric, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, relationship as orm_relationship
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
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    file_references = relationship("FileReference", back_populates="user", cascade="all, delete-orphan")
    file_chunks = relationship("FileChunk", back_populates="user", cascade="all, delete-orphan")
    usage_events = relationship("UsageEvent", back_populates="user", cascade="all, delete-orphan")
    code_sessions = relationship("CodeSession", back_populates="user", cascade="all, delete-orphan")
    vault = relationship("UserVault", back_populates="user", uselist=False, cascade="all, delete-orphan")
    life_graph_nodes = relationship("LifeGraphNode", back_populates="user", cascade="all, delete-orphan")
    life_graph_edges = relationship("LifeGraphEdge", back_populates="user", cascade="all, delete-orphan")
    weekly_reflections = relationship("WeeklyReflection", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False)
    device_info = Column(JSON, default=dict)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="sessions")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_type = Column(String(50), default="free")
    status = Column(String(50), default="active")
    billing_cycle = Column(String(50), nullable=True)
    provider = Column(String(100), nullable=True)
    provider_customer_id = Column(String(255), nullable=True)
    provider_subscription_id = Column(String(255), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    next_billing_at = Column(DateTime(timezone=True), nullable=True)
    cancel_at = Column(DateTime(timezone=True), nullable=True)
    entitlements = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="subscriptions")

class FileReference(Base):
    __tablename__ = "file_references"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_type = Column(String(50), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=True)
    storage_provider = Column(String(100), default="local")
    bucket = Column(String(255), nullable=True)
    object_key = Column(Text, nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(255), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    status = Column(String(50), default="active")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="file_references")

class FileChunk(Base):
    __tablename__ = "file_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_references.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="file_chunks")
    file = relationship("FileReference")

class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    route = Column(String(255), nullable=False)
    model = Column(String(255), nullable=True)
    provider = Column(String(100), nullable=True)
    session_id = Column(String(255), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Numeric(12, 6), default=0.0)
    file_ids = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="usage_events")

class CodeSession(Base):
    __tablename__ = "code_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    file_ids = Column(JSON, default=list)
    status = Column(String(50), default="active")
    plan_text = Column(Text, nullable=True)
    patch_text = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="code_sessions")

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

class EmbeddingJob(Base):
    __tablename__ = "embedding_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=True)
    provider = Column(String(100), default="pgvector")
    model = Column(String(255), nullable=True)
    status = Column(String(50), default="queued")
    operation = Column(String(50), default="upsert")
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    meta_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class MemoryConflict(Base):
    __tablename__ = "memory_conflicts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    existing_memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False)
    new_memory_id = Column(UUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=True)
    incoming_content = Column(Text, nullable=False)
    conflict_type = Column(String(100), default="semantic_contradiction")
    similarity = Column(Float, default=0.0)
    status = Column(String(50), default="open")
    resolution = Column(Text, nullable=True)
    meta_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

Index("idx_memories_user_archived", Memory.user_id, Memory.is_archived)
Index("idx_memories_user_type", Memory.user_id, Memory.memory_type)
Index("idx_memories_user_importance", Memory.user_id, Memory.importance)
Index("idx_embedding_jobs_user_status", EmbeddingJob.user_id, EmbeddingJob.status)
Index("idx_memory_conflicts_user_status", MemoryConflict.user_id, MemoryConflict.status)

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


UserSession.__table__.append_constraint(UniqueConstraint(UserSession.token_hash, name="uq_user_sessions_token_hash"))
Index("idx_user_sessions_user_active", UserSession.user_id, UserSession.is_active)
Index("idx_user_sessions_expires", UserSession.expires_at)

Subscription.__table__.append_constraint(
    UniqueConstraint(Subscription.provider, Subscription.provider_subscription_id, name="uq_subscriptions_provider_subscription")
)
Index("idx_subscriptions_user_status", Subscription.user_id, Subscription.status)
Index("idx_subscriptions_next_billing", Subscription.next_billing_at)

Index("idx_file_references_user_owner", FileReference.user_id, FileReference.owner_type, FileReference.owner_id)
Index("idx_file_references_user_status", FileReference.user_id, FileReference.status)
Index("idx_file_references_checksum", FileReference.checksum_sha256)
Index("idx_file_chunks_file_index", FileChunk.file_id, FileChunk.chunk_index)
Index("idx_file_chunks_user_file", FileChunk.user_id, FileChunk.file_id)
UsageEvent.__table__.append_constraint(CheckConstraint("total_tokens >= 0", name="ck_usage_total_tokens_non_negative"))
Index("idx_usage_user_created", UsageEvent.user_id, UsageEvent.created_at)
Index("idx_usage_user_session", UsageEvent.user_id, UsageEvent.session_id)
Index("idx_code_sessions_user_status", CodeSession.user_id, CodeSession.status)

Goal.__table__.append_constraint(CheckConstraint("priority BETWEEN 1 AND 5", name="ck_goals_priority_range"))
Goal.__table__.append_constraint(CheckConstraint("progress_pct BETWEEN 0.0 AND 1.0", name="ck_goals_progress_pct_range"))
Index("idx_goals_user_status", Goal.user_id, Goal.status)
Index("idx_goals_user_deadline_active", Goal.user_id, Goal.deadline, postgresql_where=(Goal.status == "active"))
Index("idx_goals_user_priority_active", Goal.user_id, Goal.priority, postgresql_where=(Goal.status == "active"))
Index("idx_goals_parent", Goal.parent_goal_id, postgresql_where=(Goal.parent_goal_id.isnot(None)))

Project.__table__.append_constraint(CheckConstraint("progress_pct BETWEEN 0.0 AND 1.0", name="ck_projects_progress_pct_range"))
Index("idx_projects_goal_id", Project.goal_id)
Index("idx_projects_user_id", Project.user_id)
Index("idx_projects_user_status", Project.user_id, Project.status)

Task.__table__.append_constraint(CheckConstraint("priority_score BETWEEN 0.0 AND 1.0", name="ck_tasks_priority_score_range"))
Task.__table__.append_constraint(CheckConstraint("quality_score IS NULL OR quality_score BETWEEN 0.0 AND 1.0", name="ck_tasks_quality_score_range"))
Task.__table__.append_constraint(CheckConstraint("retry_count >= 0", name="ck_tasks_retry_count_non_negative"))
Task.__table__.append_constraint(CheckConstraint("max_retries >= 0", name="ck_tasks_max_retries_non_negative"))
Index("idx_tasks_project_id", Task.project_id)
Index("idx_tasks_user_id", Task.user_id)
Index("idx_tasks_user_status", Task.user_id, Task.status)
Index("idx_tasks_user_critical", Task.user_id, Task.is_critical_path, postgresql_where=(Task.is_critical_path == True))
Index(
    "idx_tasks_user_priority_active",
    Task.user_id,
    Task.priority_score,
    postgresql_where=(Task.status.in_(["queued", "in_progress", "blocked", "waiting_approval"])),
)
Index("idx_tasks_user_due_active", Task.user_id, Task.due_date, postgresql_where=(Task.due_date.isnot(None)))

Index("idx_task_exec_task_id", TaskExecution.task_id)
Index("idx_task_exec_user_id", TaskExecution.user_id)
Index("idx_task_exec_started", TaskExecution.started_at)
Index("idx_task_exec_status", TaskExecution.user_id, TaskExecution.status)

Memory.__table__.append_constraint(CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_memories_confidence_range"))
Memory.__table__.append_constraint(CheckConstraint("importance BETWEEN 1 AND 10", name="ck_memories_importance_range"))
Index("idx_memories_user_id", Memory.user_id)
Index("idx_memories_accessed", Memory.user_id, Memory.last_accessed_at)
Index("idx_memories_active", Memory.user_id, Memory.memory_type, Memory.importance, postgresql_where=(Memory.is_archived == False))

Index("idx_approvals_user_status", Approval.user_id, Approval.status)
Index("idx_approvals_pending", Approval.user_id, Approval.requested_at, postgresql_where=(Approval.status == "pending"))
Index("idx_approvals_task_id", Approval.task_id)

Index("idx_schedules_next_run", Schedule.next_run_at, postgresql_where=(Schedule.is_active == True))
Index("idx_schedules_user_active", Schedule.user_id, Schedule.is_active)

Notification.__table__.append_constraint(CheckConstraint("priority BETWEEN 0 AND 3", name="ck_notifications_priority_range"))
Index("idx_notifications_user_status", Notification.user_id, Notification.status)
Index("idx_notifications_unread", Notification.user_id, Notification.created_at, postgresql_where=(Notification.read_at.is_(None)))
Index("idx_notifications_priority", Notification.user_id, Notification.priority, Notification.created_at)

Integration.__table__.append_constraint(
    UniqueConstraint(Integration.user_id, Integration.provider, Integration.provider_user_id, name="uq_integrations_user_provider_account")
)
Index("idx_integrations_user_id", Integration.user_id)
Index("idx_integrations_expiry", Integration.token_expires_at, postgresql_where=(Integration.token_expires_at.isnot(None)))

Index("idx_audit_user_time", AuditLog.user_id, AuditLog.occurred_at)
Index("idx_audit_event_type", AuditLog.event_type, AuditLog.occurred_at)
Index("idx_audit_entity", AuditLog.entity_type, AuditLog.entity_id)

class UserVault(Base):
    __tablename__ = "user_vaults"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    salt = Column(String(64), nullable=False)
    recovery_hash = Column(String(128), nullable=True)
    vault_version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="vault")

class LifeGraphNode(Base):
    __tablename__ = "life_graph_nodes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label_encrypted = Column(Text, nullable=False)
    label_blind_index = Column(String(64), nullable=False, index=True)
    node_type = Column(String(100), nullable=False)
    category = Column(String(100), nullable=True)
    strength = Column(Float, default=0.5)
    last_activity = Column(DateTime(timezone=True), nullable=True)
    metadata_encrypted = Column(Text, nullable=True)
    vector = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="life_graph_nodes")

class LifeGraphEdge(Base):
    __tablename__ = "life_graph_edges"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("life_graph_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("life_graph_nodes.id", ondelete="CASCADE"), nullable=False)
    relationship = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = orm_relationship("User", back_populates="life_graph_edges")

class WeeklyReflection(Base):
    __tablename__ = "weekly_reflections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(DateTime(timezone=True), nullable=False)
    week_end = Column(DateTime(timezone=True), nullable=False)
    content_encrypted = Column(Text, nullable=False)
    tasks_completed = Column(Integer, default=0)
    tasks_overdue = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="weekly_reflections")

class ModelPerformanceLog(Base):
    __tablename__ = "model_performance_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_key = Column(String(100), nullable=False)
    provider = Column(String(100), nullable=False)
    model_name = Column(String(255), nullable=False)
    task_type = Column(String(100), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    error_type = Column(String(100), nullable=True)
    user_satisfaction = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
