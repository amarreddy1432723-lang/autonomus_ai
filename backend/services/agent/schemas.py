from pydantic import BaseModel
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
    created_at: datetime
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
    meta_data: Optional[Dict[str, Any]] = None
