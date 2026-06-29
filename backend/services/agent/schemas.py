from pydantic import BaseModel
from typing import List, Optional
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
