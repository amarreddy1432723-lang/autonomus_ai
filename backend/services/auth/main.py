from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID

from services.shared.database import get_db
from services.shared.models import User, UserProfile, Integration
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from .schemas import UserRegister, UserLogin, TokenResponse, UserResponse, IntegrationCreate, IntegrationResponse
from .auth import hash_password, verify_password, create_access_token, create_refresh_token, decode_token

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.shared.database import SessionLocal, verify_default_user
    db = SessionLocal()
    try:
        verify_default_user(db)
    finally:
        db.close()
    yield

app = FastAPI(title="my-ai Auth Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> UUID:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id_str = payload.get("sub")
    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity format",
        )

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password and create user
    hashed = hash_password(user_data.password)
    new_user = User(email=user_data.email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Initialize default user profile
    new_profile = UserProfile(user_id=new_user.id)
    db.add(new_profile)
    db.commit()
    
    return new_user

@app.post("/login", response_model=TokenResponse)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer"
    }

@app.post("/refresh", response_model=TokenResponse)
def refresh_tokens(refresh_token: str, db: Session = Depends(get_db)):
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    user_id_str = payload.get("sub")
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload identity format",
        )
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
        
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer"
    }

@app.get("/me", response_model=UserResponse)
def get_me(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

from typing import List

@app.get("/api/v1/integrations", response_model=List[IntegrationResponse])
def get_integrations(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Integration).filter(Integration.user_id == user_id).all()

@app.post("/api/v1/integrations", response_model=IntegrationResponse, status_code=201)
def create_integration(integration_in: IntegrationCreate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    existing = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.provider == integration_in.provider
    ).first()
    
    if existing:
        existing.status = "active"
        existing.access_token = integration_in.access_token
        existing.refresh_token = integration_in.refresh_token
        existing.token_expires_at = integration_in.token_expires_at
        existing.scopes = integration_in.scopes
        existing.provider_user_id = integration_in.provider_user_id
        existing.metadata_json = integration_in.metadata_json
        db.commit()
        db.refresh(existing)
        return existing
        
    new_integration = Integration(
        user_id=user_id,
        provider=integration_in.provider,
        status="active",
        access_token=integration_in.access_token,
        refresh_token=integration_in.refresh_token,
        token_expires_at=integration_in.token_expires_at,
        scopes=integration_in.scopes,
        provider_user_id=integration_in.provider_user_id,
        metadata_json=integration_in.metadata_json
    )
    db.add(new_integration)
    db.commit()
    db.refresh(new_integration)
    return new_integration

@app.delete("/api/v1/integrations/{provider}")
def delete_integration(provider: str, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    integration = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.provider == provider
    ).first()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{provider}' not found"
        )
    db.delete(integration)
    db.commit()
    return {"message": f"Successfully disconnected integration '{provider}'"}
