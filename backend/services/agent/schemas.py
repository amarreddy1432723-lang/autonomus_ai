from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class MemoryResponse(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    memory_type: str
    content: str
    importance: int
    confidence: float
    source: Optional[str] = None
    source_url: Optional[str] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    is_archived: bool = False
    is_superseded: bool = False
    related_memory_ids: List[str] = []
    compressed_from: List[str] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    tags: List[str] = []

    class Config:
        from_attributes = True

class MemorySearchResponse(BaseModel):
    id: UUID
    content: str
    type: str
    importance: int
    confidence: float
    similarity: float
    score: Optional[float] = None
    source: Optional[str] = None
    memory_type: Optional[str] = None
    created_at: datetime
    tags: List[str] = []

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    type: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[int] = None
    confidence: Optional[float] = None
    tags: Optional[List[str]] = None
    is_archived: Optional[bool] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    meta_data: Optional[Dict[str, Any]] = None

class MemoryCreate(BaseModel):
    content: str
    type: str = "fact"
    memory_type: str = "fact"
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source: str = "user_explicit"
    source_session_id: Optional[UUID] = None
    source_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    meta_data: Dict[str, Any] = Field(default_factory=dict)

class MemoryExtractRequest(BaseModel):
    conversation: str
    session_id: Optional[str] = None

class SessionMemoryEvent(BaseModel):
    role: str
    content: str
    name: Optional[str] = None
    timestamp: Optional[str] = None
    meta_data: Dict[str, Any] = Field(default_factory=dict)

class SessionMemoryResponse(BaseModel):
    session_id: str
    events: List[Dict[str, Any]]

class AutonomyRunRequest(BaseModel):
    max_tasks: int = Field(default=3, ge=1, le=20)
    dry_run: bool = False

class AutonomyLevelUpdate(BaseModel):
    autonomy_level: str = Field(pattern="^(observer|assistant|partner|chief_of_staff)$")

class VaultSetupRequest(BaseModel):
    salt: str
    recovery_hash: Optional[str] = None

class VaultStatusResponse(BaseModel):
    exists: bool
    salt: Optional[str] = None
    vault_version: int = 1

