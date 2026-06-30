from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, description="Password must be at least 12 characters")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True

from typing import List, Optional

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

class SessionResponse(BaseModel):
    id: UUID
    device_info: dict
    ip_address: Optional[str]
    is_active: bool
    expires_at: datetime
    revoked_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class IntegrationCreate(BaseModel):
    provider: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: List[str] = []
    provider_user_id: Optional[str] = None
    metadata_json: dict = {}

class IntegrationResponse(BaseModel):
    id: UUID
    provider: str
    status: str
    scopes: List[str]
    provider_user_id: Optional[str]
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
