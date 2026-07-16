import os
from fastapi import FastAPI, Depends, HTTPException, Query, Request, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from common.sentry_setup import initialize_sentry
from services.shared.database import get_db
from services.shared.models import User, UserProfile, Integration, UserSession
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from services.shared.api import install_api_foundation
from services.shared.api import clamp_pagination
from services.shared.security import (
    dev_auth_fallback_enabled,
    encrypt_secret,
    resolve_user_id_from_auth_or_clerk,
    secret_fingerprint,
)
from .schemas import (
    DesktopAuthCodeRequest,
    DesktopAuthExchangeRequest,
    LogoutRequest,
    RefreshRequest,
    SessionResponse,
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
    IntegrationCreate,
    IntegrationResponse,
)
from .config import settings
from .auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
    refresh_token_expires_at,
)

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

initialize_sentry("auth")

app = FastAPI(title="my-ai Auth Service", version="1.0.0", lifespan=lifespan)
install_api_foundation(app, "auth-service")
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

@app.get("/")
def service_root():
    return {
        "service": "auth-service",
        "status": "running",
        "message": "This is a Arceus API service. Open the frontend UI instead.",
        "frontend": os.getenv("NEXUS_FRONTEND_URL", "http://localhost:3000/workspace"),
        "docs": "/docs",
    }

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

def get_current_user_id(
    token: str | None = Depends(oauth2_scheme),
    x_user_id: str | None = Header(None, alias="x-user-id"),
    db: Session = Depends(get_db),
) -> UUID:
    authorization = f"Bearer {token}" if token else None
    return resolve_user_id_from_auth_or_clerk(db, authorization, x_user_id, settings.JWT_SECRET, settings.JWT_ALGORITHM)

def _create_desktop_auth_code(user_id: UUID) -> str:
    import jwt

    payload = {
        "sub": str(user_id),
        "type": "desktop_auth_code",
        "aud": "arceus-desktop",
        "exp": datetime.utcnow() + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def _decode_desktop_auth_code(code: str) -> UUID:
    import jwt

    try:
        payload = jwt.decode(
            code,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            audience="arceus-desktop",
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop authorization code is invalid or expired")
    if payload.get("type") != "desktop_auth_code":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop authorization code has the wrong purpose")
    return UUID(str(payload["sub"]))

def require_scopes(*required_scopes: str):
    def dependency(
        authorization: str | None = Header(None),
        x_user_id: str | None = Header(None, alias="x-user-id"),
        db: Session = Depends(get_db),
    ) -> UUID:
        return resolve_user_id_from_auth_or_clerk(
            db,
            authorization,
            x_user_id,
            settings.JWT_SECRET,
            settings.JWT_ALGORITHM,
            required_scopes=set(required_scopes),
        )
    return dependency

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
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
@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(login_data: UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh),
        device_info={"user_agent": request.headers.get("user-agent", "unknown")},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=refresh_token_expires_at(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(session)
    user.last_active_at = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer"
    }

@app.post("/refresh", response_model=TokenResponse)
@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
def refresh_tokens(refresh_in: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(refresh_in.refresh_token)
    session = db.query(UserSession).filter(
        UserSession.token_hash == token_hash,
        UserSession.is_active == True,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > datetime.utcnow(),
    ).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user = db.query(User).filter(User.id == session.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    refresh = create_refresh_token(user.id)
    session.token_hash = hash_refresh_token(refresh)
    session.expires_at = refresh_token_expires_at()
    session.last_seen_at = datetime.utcnow()
    session.ip_address = request.client.host if request.client else session.ip_address
    session.user_agent = request.headers.get("user-agent") or session.user_agent
    user.last_active_at = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": refresh,
        "token_type": "bearer"
    }

@app.post("/api/v1/auth/logout")
@app.post("/logout")
def logout(logout_in: LogoutRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    if logout_in.refresh_token:
        session = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.token_hash == hash_refresh_token(logout_in.refresh_token),
        ).first()
        if session:
            session.is_active = False
            session.revoked_at = datetime.utcnow()
    else:
        db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.is_active == True).update({
            "is_active": False,
            "revoked_at": datetime.utcnow(),
        })
    db.commit()
    return {"message": "Logged out successfully"}

@app.post("/api/v1/auth/desktop/code")
def create_desktop_auth_code(
    request_in: DesktopAuthCodeRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    if not request_in.redirect_uri.startswith("arceus://auth/callback"):
        raise HTTPException(status_code=400, detail="Desktop redirect URI must use arceus://auth/callback")
    code = _create_desktop_auth_code(user_id)
    separator = "&" if "?" in request_in.redirect_uri else "?"
    return {
        "code_expires_in_seconds": 300,
        "redirect_url": f"{request_in.redirect_uri}{separator}code={code}",
    }

@app.post("/api/v1/auth/desktop/exchange", response_model=TokenResponse)
def exchange_desktop_auth_code(
    exchange_in: DesktopAuthExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = _decode_desktop_auth_code(exchange_in.code)
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop authorization user is unavailable")
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh),
        device_info={"client": "arceus-desktop", "user_agent": request.headers.get("user-agent", "unknown")},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=refresh_token_expires_at(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(session)
    user.last_active_at = datetime.utcnow()
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

@app.get("/me", response_model=UserResponse)
@app.get("/api/v1/me", response_model=UserResponse)
@app.get("/api/v1/auth/me", response_model=UserResponse)
def get_me(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@app.get("/api/v1/auth/sessions", response_model=List[SessionResponse])
def list_sessions(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(UserSession).filter(UserSession.user_id == user_id).order_by(UserSession.created_at.desc()).all()

@app.delete("/api/v1/auth/sessions/all")
def revoke_all_sessions(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    db.query(UserSession).filter(UserSession.user_id == user_id, UserSession.is_active == True).update({
        "is_active": False,
        "revoked_at": datetime.utcnow(),
    })
    db.commit()
    return {"message": "All sessions revoked"}

@app.delete("/api/v1/auth/sessions/{session_id}")
def revoke_session(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id, UserSession.user_id == user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_active = False
    session.revoked_at = datetime.utcnow()
    db.commit()
    return {"message": "Session revoked"}

@app.get("/api/v1/integrations", response_model=List[IntegrationResponse])
def get_integrations(
    status_filter: str | None = Query(None, alias="status"),
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(require_scopes("integrations:read")),
    db: Session = Depends(get_db),
):
    page, page_size, offset = clamp_pagination(page, page_size)
    query = db.query(Integration).filter(Integration.user_id == user_id)
    if status_filter:
        query = query.filter(Integration.status == status_filter)
    return query.order_by(Integration.created_at.desc()).offset(offset).limit(page_size).all()

@app.post("/api/v1/integrations", response_model=IntegrationResponse, status_code=201)
def create_integration(integration_in: IntegrationCreate, user_id: UUID = Depends(require_scopes("integrations:write")), db: Session = Depends(get_db)):
    metadata = dict(integration_in.metadata_json or {})
    if integration_in.access_token:
        metadata["access_token_fingerprint"] = secret_fingerprint(integration_in.access_token)
    if integration_in.refresh_token:
        metadata["refresh_token_fingerprint"] = secret_fingerprint(integration_in.refresh_token)
    if integration_in.access_token or integration_in.refresh_token:
        metadata["tokens_encrypted"] = True

    existing = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.provider == integration_in.provider
    ).first()
    
    if existing:
        existing.status = "active"
        existing.access_token = encrypt_secret(integration_in.access_token)
        existing.refresh_token = encrypt_secret(integration_in.refresh_token)
        existing.token_expires_at = integration_in.token_expires_at
        existing.scopes = integration_in.scopes
        existing.provider_user_id = integration_in.provider_user_id
        existing.metadata_json = metadata
        db.commit()
        db.refresh(existing)
        return existing
        
    new_integration = Integration(
        user_id=user_id,
        provider=integration_in.provider,
        status="active",
        access_token=encrypt_secret(integration_in.access_token),
        refresh_token=encrypt_secret(integration_in.refresh_token),
        token_expires_at=integration_in.token_expires_at,
        scopes=integration_in.scopes,
        provider_user_id=integration_in.provider_user_id,
        metadata_json=metadata
    )
    db.add(new_integration)
    db.commit()
    db.refresh(new_integration)
    return new_integration

@app.delete("/api/v1/integrations/{provider}")
def delete_integration(provider: str, user_id: UUID = Depends(require_scopes("integrations:write")), db: Session = Depends(get_db)):
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

@app.get("/api/v1/security/status")
def security_status(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    encrypted_tokens = db.query(Integration).filter(
        Integration.user_id == user_id,
        Integration.access_token.like("enc:v1:%"),
    ).count()
    return {
        "jwt": {
            "algorithm": settings.JWT_ALGORITHM,
            "access_token_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_rotation": True,
        },
        "auth": {
            "dev_header_fallback": dev_auth_fallback_enabled(),
            "scope_enforcement": ["integrations:read", "integrations:write"],
        },
        "data_protection": {
            "integration_tokens_encrypted": True,
            "encrypted_integrations_for_user": encrypted_tokens,
        },
        "audit": {
            "append_only": True,
        },
        "ai_security": {
            "prompt_injection_filter": True,
            "tool_output_marked_untrusted": True,
        },
    }
