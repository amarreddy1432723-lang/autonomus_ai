import json
import os
import urllib.error
import urllib.request
import jwt
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status, File, UploadFile, Request, Response, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, List, Optional
from langchain_core.messages import HumanMessage, AIMessage
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from .config import settings
from services.shared.database import get_db
from services.shared.models import FileReference, Memory
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from services.shared.api import clamp_pagination, install_api_foundation
from services.shared.security import resolve_user_id_from_auth_or_clerk
from .schemas import (
    MemoryCreate,
    MemoryExtractRequest,
    MemoryResponse,
    MemoryUpdate,
    SessionMemoryEvent,
    SessionMemoryResponse,
    AutonomyLevelUpdate,
    AutonomyRunRequest,
    VaultSetupRequest,
    VaultStatusResponse,
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonlychangeinprod!")
JWT_ALGORITHM = "HS256"

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.shared.database import SessionLocal, verify_default_user, engine, Base
    from .worker import worker_queue
    # Auto-create any new tables in the database
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        verify_default_user(db)
    finally:
        db.close()

    # Start background worker queue
    worker_queue.start()
    try:
        yield
    finally:
        worker_queue.stop()

app = FastAPI(title="my-ai Agent Service", version="1.0.0", lifespan=lifespan)
install_api_foundation(app, "agent-service")
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

@app.get("/")
def service_root():
    return {
        "service": "agent-service",
        "status": "running",
        "message": "This is a NEXUS API service. Open the frontend UI instead.",
        "frontend": os.getenv("NEXUS_FRONTEND_URL", "http://localhost:3000/workspace"),
        "docs": "/docs",
    }

def get_current_user_id(
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="x-user-id"),
    db: Session = Depends(get_db),
) -> UUID:
    return resolve_user_id_from_auth_or_clerk(db, authorization, x_user_id, JWT_SECRET_KEY, JWT_ALGORITHM)

def parse_vault_key(x_vault_key: str | None) -> bytes | None:
    if not x_vault_key:
        return None
    try:
        return bytes.fromhex(x_vault_key)
    except Exception:
        return None

class ChatMessage(BaseModel):
    role: str # "user", "assistant"
    content: str

class ChatRequest(BaseModel):
    user_id: str
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    persist: bool = True
    file_ids: List[str] = Field(default_factory=list)
    interview_style: Optional[str] = None
    target_role: Optional[str] = None
    target_company: Optional[str] = None
    project_notes: Optional[str] = None
    interview_prompt: Optional[str] = None

EXPOSED_CHAT_MODELS: dict[str, tuple[str, str]] = {
    "autonomus-ai-v1": ("autonomus", "autonomus-ai-v1"),
    "nexus-fast": ("nexus", "nexus-fast"),
    "nexus-reasoning": ("nexus", "nexus-reasoning"),
    "nexus-code": ("nexus", "nexus-code"),
    "groq-llama-3.3": ("groq", "llama-3.3-70b-versatile"),
    "openai-gpt-4o-mini": ("openai", "gpt-4o-mini"),
    "gemini-1.5-flash": ("google", "gemini-1.5-flash"),
}

EXPOSED_PROVIDER_MODELS = set(EXPOSED_CHAT_MODELS.values())

def resolve_exposed_chat_model(provider: str | None, model: str | None) -> tuple[str | None, str | None]:
    if not provider and not model:
        return None, None

    normalized_provider = (provider or "").strip().lower()
    normalized_model = (model or "").strip()
    if normalized_provider in EXPOSED_CHAT_MODELS and not normalized_model:
        return EXPOSED_CHAT_MODELS[normalized_provider]

    pair = (normalized_provider, normalized_model)
    if pair in EXPOSED_PROVIDER_MODELS:
        return pair

    raise HTTPException(status_code=400, detail="Unsupported chat model selection.")

class TrainingExampleRequest(BaseModel):
    user_request: str
    assistant_response: str
    goal_context: Optional[dict[str, Any]] = None
    selected_model: Optional[dict[str, str]] = None
    user_correction: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)
    quality_status: str = "candidate"
    source: str = "chat"

class InterviewPlanRequest(BaseModel):
    resume_id: Optional[str] = None
    target_role: str = ""
    target_company: str = ""
    job_description: str = ""

class CodeSessionCreate(BaseModel):
    title: str = "Code workspace"
    file_ids: List[str] = Field(default_factory=list)
    project_id: Optional[UUID] = None

class CodeProjectCreate(BaseModel):
    name: str = "Untitled Code Project"
    description: str = ""
    repo_url: str = ""
    file_ids: List[str] = Field(default_factory=list)

class CodeProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    status: Optional[str] = None

class CodeBackgroundRunRequest(BaseModel):
    instruction: str
    mode: str = "code"
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class FileContentUpdate(BaseModel):
    content: str

class InlineCodeEditRequest(BaseModel):
    file_id: UUID
    filename: str = ""
    instruction: str
    selected_text: str
    full_content: str = ""
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class CodeCompletionRequest(BaseModel):
    file_id: UUID
    filename: str = ""
    prefix: str
    suffix: str = ""
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class CodeSessionFilesUpdate(BaseModel):
    file_ids: List[str] = Field(default_factory=list)

class CodeInstructionRequest(BaseModel):
    instruction: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class CodeCommandRunRequest(BaseModel):
    command: str
    timeout_seconds: int = 45
    approved: bool = False

class CodeSuggestNextRequest(BaseModel):
    user_description: str = ""
    selected_mode: str = "auto"
    selected_file_ids: List[str] = Field(default_factory=list)
    open_file_ids: List[str] = Field(default_factory=list)
    current_prompt: str = ""
    recent_messages: List[dict[str, Any]] = Field(default_factory=list)

class CodeWorkspaceTaskRequest(BaseModel):
    id: Optional[str] = None
    title: str = "Workspace task"
    description: str = ""
    summary: str = ""
    mode: str = "code"
    status: str = "typed"
    risk: str = "medium"
    requires_approval: bool = False
    files: List[str] = Field(default_factory=list)
    folders: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    commands: List[str] = Field(default_factory=list)
    expected_commands: List[str] = Field(default_factory=list)
    suggested_prompt: str = ""
    prompt: str = ""
    impact: str = ""
    file_hint: str = ""
    check_hint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

class CodeWorkspaceTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    risk: Optional[str] = None
    requires_approval: Optional[bool] = None
    files: Optional[List[str]] = None
    folders: Optional[List[str]] = None
    steps: Optional[List[str]] = None
    commands: Optional[List[str]] = None
    expected_commands: Optional[List[str]] = None
    suggested_prompt: Optional[str] = None
    prompt: Optional[str] = None
    impact: Optional[str] = None
    file_hint: Optional[str] = None
    check_hint: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

class CodeAgentLoopRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    max_steps: int = Field(default=8, ge=1, le=20)
    approved_tools: List[str] = Field(default_factory=list)

class CodeRuntimeInstallRequest(BaseModel):
    command: Optional[str] = None
    timeout_seconds: int = 300
    approved: bool = False

class CodePreviewCheckRequest(BaseModel):
    url: str

class CodeFixPreviewRequest(BaseModel):
    instruction: str = ""
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class CodeGitConnectRequest(BaseModel):
    repo_url: str
    default_branch: str = "main"

class CodeGitImportRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None

class GitHubSessionImportRequest(BaseModel):
    repository: str
    branch: Optional[str] = None

class GitHubBranchRequest(BaseModel):
    branch_name: Optional[str] = None
    base_branch: Optional[str] = None

class GitHubCommitRequest(BaseModel):
    message: Optional[str] = None

class GitHubPullRequestRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None

class CodePreparePullRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class CodePatchSelectionRequest(BaseModel):
    file_ids: List[str] = Field(default_factory=list)

class CodeRollbackRequest(BaseModel):
    snapshot_id: Optional[str] = None

class AgentJobCreateRequest(BaseModel):
    code_session_id: Optional[UUID] = None
    mode: str = "code"
    prompt: str = ""
    approval_state: str = "none"

class NexusCodeRequest(BaseModel):
    instruction: str
    file_ids: List[str] = Field(default_factory=list)
    context: str = ""
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class WorkspaceActivityRequest(BaseModel):
    prompt: str = ""
    mode: str = "auto"

class ToolSelectionRequest(BaseModel):
    prompt: str = ""
    mode: str = "auto"
    max_tools: int = Field(default=8, ge=1, le=20)
    include_high_risk: bool = True

class ToolValidationRequest(BaseModel):
    tool_name: str
    approved: bool = False

class NexusResearchRequest(BaseModel):
    query: str
    depth: str = "standard"

class NexusBrowseRequest(BaseModel):
    url: str

class FreeTierRecommendRequest(BaseModel):
    project_type: str = ""
    needs: str = ""

class NexusDesignRequest(BaseModel):
    description: str
    output_type: str = "page"
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class NexusDeployAnalyzeRequest(BaseModel):
    project_type: str = ""
    repo_context: str = ""

class NexusSafetyRequest(BaseModel):
    content: str
    action: str = "answer"

class NexusSuggestionFeedbackRequest(BaseModel):
    suggestion_id: str
    feedback: str = "dismissed"

class NexusModelRouteRequest(BaseModel):
    prompt: str
    speed_priority: bool = True

class NexusBlendRequest(BaseModel):
    prompt: str
    context: str = ""
    file_ids: List[str] = Field(default_factory=list)
    task_type: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class BillingCheckoutRequest(BaseModel):
    plan: str = "pro"
    billing_cycle: str = "monthly"

class PAScheduleRequest(BaseModel):
    task: str
    duration_minutes: int = 60
    deadline: Optional[str] = None

class PAOSStateRequest(BaseModel):
    state: str

class PAMeetingPrepRequest(BaseModel):
    meeting_context: str

class PADelegateRequest(BaseModel):
    instruction: str

class PACommandRequest(BaseModel):
    command: str

class PATaskRequest(BaseModel):
    title: str
    description: str = ""
    due_at: Optional[str] = None
    priority_score: float = 0.5

class PATaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    due_at: Optional[str] = None
    priority_score: Optional[float] = None

class PAScheduleItemRequest(BaseModel):
    title: str
    next_run_at: Optional[str] = None
    trigger: str = "time"
    permission: str = "confirm"
    payload: dict[str, Any] = Field(default_factory=dict)

class PAScheduleItemUpdateRequest(BaseModel):
    title: Optional[str] = None
    next_run_at: Optional[str] = None
    status: Optional[str] = None
    permission: Optional[str] = None

def build_uploaded_context(db: Session, user_id: UUID, file_ids: List[str], prompt: str) -> str:
    if not file_ids:
        return ""
    from .file_service import file_context_for_prompt

    return file_context_for_prompt(db, user_id, file_ids, prompt)

def _training_data_path(filename: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    path = root / "training" / "data" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

async def chat_stream_generator(
    user_id: str,
    prompt: str,
    chat_history: List[ChatMessage],
    session_id: str = "default",
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    persist: bool = True,
    file_ids: Optional[List[str]] = None,
    interview_style: Optional[str] = None,
    target_role: Optional[str] = None,
    target_company: Optional[str] = None,
    project_notes: Optional[str] = None,
    interview_prompt: Optional[str] = None,
):
    from .brain import brain_agent
    from .memory_agent import RedisShortTermMemoryStore, extract_memories

    formatted_messages = []
    for msg in chat_history:
        if msg.role == "user":
            formatted_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            formatted_messages.append(AIMessage(content=msg.content))

    formatted_messages.append(HumanMessage(content=prompt))

    input_state = {
        "messages": formatted_messages,
        "user_id": user_id,
        "file_context": "",
    }

    if file_ids:
        from services.shared.database import SessionLocal
        from .file_service import file_context_for_prompt
        db = SessionLocal()
        try:
            input_state["file_context"] = file_context_for_prompt(db, UUID(user_id), file_ids, prompt)
        finally:
            db.close()

    config = {
        "configurable": {
            "session_id": session_id,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "interview_style": interview_style,
            "target_role": target_role,
            "target_company": target_company,
            "project_notes": project_notes,
            "interview_prompt": interview_prompt,
        }
    }

    assistant_text = []
    stm = RedisShortTermMemoryStore()
    if persist:
        stm.append_event(user_id, session_id, {"role": "user", "content": prompt})

    try:
        async for event in brain_agent.astream_events(input_state, config=config, version="v2"):
            kind = event.get("event")
            node_name = event.get("metadata", {}).get("langgraph_node", "")

            if kind == "on_chain_start" and event.get("name") == "LangGraph":
                yield f"event: thinking\ndata: {json.dumps({'status': 'started'})}\n\n"

            elif kind == "on_chain_start" and node_name:
                yield f"event: thinking\ndata: {json.dumps({'node': node_name, 'status': 'running'})}\n\n"

            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    token = str(chunk.content)
                    if node_name == "classify_intent":
                        continue
                    try:
                        parsed_token = json.loads(token)
                        if set(parsed_token.keys()) == {"intent"}:
                            continue
                    except Exception:
                        pass
                    assistant_text.append(str(chunk.content))
                    yield f"event: token\ndata: {json.dumps({'token': chunk.content})}\n\n"

            elif kind == "on_tool_start":
                tool_name = event.get("name")
                inputs = event["data"].get("input")
                yield f"event: tool_start\ndata: {json.dumps({'tool': tool_name, 'inputs': inputs})}\n\n"

            elif kind == "on_tool_end":
                tool_name = event.get("name")
                output = event["data"].get("output")
                yield f"event: tool_end\ndata: {json.dumps({'tool': tool_name, 'output': str(output)})}\n\n"

        final_text = "".join(assistant_text)
        if persist and final_text:
            stm.append_event(user_id, session_id, {"role": "assistant", "content": final_text})
        if persist:
            try:
                extract_memories(UUID(user_id), "\n".join([prompt, final_text]))
            except Exception:
                pass
        usage_payload = {}
        db = None
        try:
            from services.shared.database import SessionLocal
            from .usage import record_usage
            db = SessionLocal()
            usage = record_usage(
                db=db,
                user_id=UUID(user_id),
                route="/api/v1/agents/chat",
                provider=llm_provider,
                model=llm_model,
                session_id=session_id,
                prompt_text="\n".join([m.content for m in chat_history] + [prompt, input_state.get("file_context") or ""]),
                completion_text=final_text,
                file_ids=file_ids or [],
            )
            usage_payload = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": float(usage.estimated_cost_usd or 0),
            }
        except Exception:
            pass
        finally:
            if db:
                db.close()
        yield f"event: done\ndata: {json.dumps({'status': 'completed', 'usage': usage_payload})}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

@app.post("/api/v1/agents/chat")
async def chat_endpoint(
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .billing import check_entitlement

    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")

    access = check_entitlement(db, user_id, "chat_message")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Plan limit reached", "access": access})

    prompt = request.messages[-1].content
    history = request.messages[:-1]
    llm_provider, llm_model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)

    return StreamingResponse(
        chat_stream_generator(
            str(user_id),
            prompt,
            history,
            request.session_id or "default",
            llm_provider,
            llm_model,
            request.persist,
            request.file_ids,
            request.interview_style,
            request.target_role,
            request.target_company,
            request.project_notes,
            request.interview_prompt,
        ),
        media_type="text/event-stream"
    )

@app.post("/api/v1/models/route")
def nexus_model_route(request: NexusModelRouteRequest, user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import choose_model_for_task, classify_task_type

    task_type = classify_task_type(request.prompt)
    return {
        "task_type": task_type,
        "selected_model": choose_model_for_task(task_type, request.speed_priority),
    }

@app.post("/api/v1/models/blend")
def nexus_model_blend(request: NexusBlendRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .nexus_services import NexusLLMConfig, blended_answer, classify_task_type

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    task_type = request.task_type or classify_task_type(request.prompt)
    uploaded_context = build_uploaded_context(db, user_id, request.file_ids, request.prompt)
    context = "\n\n".join([request.context, uploaded_context]).strip()
    config = NexusLLMConfig(provider, model) if provider or model else None
    return blended_answer(request.prompt, context, task_type, config)

@app.post("/api/v1/training/examples", status_code=202)
def capture_training_example(
    request: TrainingExampleRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    status_value = request.quality_status.strip().lower()
    if status_value not in {"candidate", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="quality_status must be candidate, approved, or rejected.")
    if not request.user_request.strip() or not request.assistant_response.strip():
        raise HTTPException(status_code=400, detail="user_request and assistant_response are required.")

    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user_id),
        "user_request": request.user_request.strip(),
        "assistant_response": request.assistant_response.strip(),
        "goal_context": request.goal_context or {},
        "selected_model": request.selected_model or {},
        "user_correction": (request.user_correction or "").strip(),
        "media_urls": [url for url in request.media_urls if url.startswith(("http://", "https://"))],
        "quality_status": status_value,
        "source": request.source,
    }

    output = _training_data_path("candidate_examples.jsonl")
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    return {"status": "captured", "quality_status": status_value}

@app.post("/api/v1/interview/plan")
async def interview_plan_endpoint(
    request: InterviewPlanRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .file_service import get_file_text
    from .interview_planner import build_interview_plan, stream_plan_text

    resume_text = ""
    if request.resume_id:
        try:
            resume_text = get_file_text(db, user_id, UUID(str(request.resume_id)))
        except Exception:
            resume_text = ""

    plan = build_interview_plan(
        resume_text=resume_text,
        target_role=request.target_role,
        target_company=request.target_company,
        job_description=request.job_description,
    )

    async def event_stream():
        for chunk in stream_plan_text(plan):
            yield f"event: token\ndata: {json.dumps({'token': chunk})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/v1/training/train")
def trigger_self_training(user_id: UUID = Depends(get_current_user_id)):
    from .training_service import start_self_training_job
    return start_self_training_job()

@app.get("/api/v1/training/jobs")
def get_self_training_jobs(user_id: UUID = Depends(get_current_user_id)):
    from .training_service import sync_job_statuses
    return sync_job_statuses()

@app.get("/api/v1/training/active-model")
def get_active_model(user_id: UUID = Depends(get_current_user_id)):
    from .training_service import get_active_finetuned_model
    model = get_active_finetuned_model()
    return {"active_finetuned_model": model or "None"}

@app.post("/api/v1/files", status_code=201)
async def upload_file(
    upload: UploadFile = File(...),
    owner_type: str = "chat",
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .billing import check_entitlement
    from .file_service import create_file_reference, extract_file_to_chunks

    access = check_entitlement(db, user_id, "file_upload")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "File upload limit reached", "access": access})

    record = await create_file_reference(db, user_id, upload, owner_type=owner_type)
    extraction = extract_file_to_chunks(db, user_id, record.id)
    db.refresh(record)
    return {
        "id": str(record.id),
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "status": record.status,
        "storage_provider": record.storage_provider,
        "metadata": record.metadata_json or {},
        "extraction": extraction,
    }

@app.get("/api/v1/files")
def list_files(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    records = db.query(FileReference).filter(
        FileReference.user_id == user_id,
        FileReference.status == "active",
    ).order_by(FileReference.created_at.desc()).all()
    return [
        {
            "id": str(record.id),
            "filename": record.filename,
            "content_type": record.content_type,
            "size_bytes": record.size_bytes,
            "metadata": record.metadata_json or {},
            "created_at": record.created_at,
        }
        for record in records
    ]

@app.get("/api/v1/files/{file_id}")
def get_file(file_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .file_service import get_file_text

    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "id": str(record.id),
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "metadata": record.metadata_json or {},
        "preview": get_file_text(db, user_id, file_id)[:8000],
    }

@app.get("/api/v1/files/{file_id}/content")
def get_file_content(file_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .file_service import get_file_text

    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id, FileReference.status == "active").first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    text = get_file_text(db, user_id, file_id)
    if len(text) > 600_000:
        raise HTTPException(status_code=413, detail="File is too large for inline editing")
    return {
        "id": str(record.id),
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "content": text,
    }

@app.put("/api/v1/files/{file_id}/content")
def update_file_content(file_id: UUID, request: FileContentUpdate, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from pathlib import Path
    from services.shared.models import FileChunk
    from .file_service import put_object, storage_provider

    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id, FileReference.status == "active").first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    editable_extensions = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".html", ".css"}
    extension = Path(record.filename).suffix.lower()
    if extension not in editable_extensions:
        raise HTTPException(status_code=400, detail="This file type is not editable inline")
    data = request.content.encode("utf-8")
    if len(data) > 1_500_000:
        raise HTTPException(status_code=413, detail="Edited file exceeds the inline editor limit")
    put_object(record.object_key, data, record.content_type or "text/plain")

    # Desktop/local mode: mirror inline edits back into the selected local project.
    if record.owner_type == "code_workspace" and record.owner_id:
        from services.shared.models import CodeSession
        session = db.query(CodeSession).filter(CodeSession.id == record.owner_id).first()
        if session and session.metadata_json and session.metadata_json.get("local_workspace_path"):
            from pathlib import Path
            local_root = Path(str(session.metadata_json["local_workspace_path"])).expanduser().resolve()
            safe_name = record.filename.replace("\\", "/").lstrip("/")
            local_file = (local_root / safe_name).resolve()
            if not str(local_file).startswith(str(local_root)):
                raise HTTPException(status_code=400, detail="Unsafe local workspace file path")
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(data)

    record.size_bytes = len(data)
    record.metadata_json = {**(record.metadata_json or {}), "edited_inline": True, "inline_editor_updated_at": datetime.now(timezone.utc).isoformat()}
    db.query(FileChunk).filter(FileChunk.file_id == record.id, FileChunk.user_id == user_id).delete()
    db.commit()
    db.refresh(record)
    return {"id": str(record.id), "filename": record.filename, "size_bytes": record.size_bytes, "status": "saved"}

@app.delete("/api/v1/files/{file_id}")
def delete_file(file_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .file_service import delete_object

    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    delete_object(record.object_key)
    record.status = "deleted"
    db.commit()
    return {"status": "deleted"}

@app.post("/api/v1/files/{file_id}/extract")
def extract_file(file_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .file_service import extract_file_to_chunks
    from .usage import record_usage

    result = extract_file_to_chunks(db, user_id, file_id)
    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
    record_usage(db, user_id, "/api/v1/files/extract", None, "file-extractor", None, "", "", [str(file_id)], result)
    if record:
        result["metadata"] = record.metadata_json or {}
    return result

@app.get("/api/v1/usage/summary")
def get_usage_summary(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .usage import usage_summary

    return usage_summary(db, user_id)

@app.get("/api/v1/billing/summary")
def get_billing_summary(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import billing_summary

    return billing_summary(db, user_id)

@app.get("/api/v1/billing/plans")
def get_billing_plans(user_id: UUID = Depends(get_current_user_id)):
    from .billing import PLAN_CATALOG

    return {"plans": PLAN_CATALOG}

@app.get("/api/v1/billing/entitlement/{feature}")
def get_feature_entitlement(feature: str, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement

    return check_entitlement(db, user_id, feature)

@app.get("/api/v1/billing/interview-access")
def get_interview_access(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement

    return check_entitlement(db, user_id, "interview_session")

@app.post("/api/v1/billing/interview-session")
def record_interview_access(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import record_interview_session

    return record_interview_session(db, user_id)

@app.post("/api/v1/billing/checkout")
def create_billing_checkout(request: BillingCheckoutRequest, user_id: UUID = Depends(get_current_user_id)):
    from .billing import create_checkout_session

    if request.plan not in {"starter", "pro", "enterprise"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")
    if request.billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="Unsupported billing cycle")
    return create_checkout_session(request.plan, request.billing_cycle)

@app.post("/api/v1/billing/portal")
def create_billing_portal(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import billing_summary

    summary = billing_summary(db, user_id)
    if not os.getenv("STRIPE_SECRET_KEY"):
        return {
            "status": "not_configured",
            "message": "Stripe Billing Portal is not configured yet.",
            "billing": summary["plan"],
        }
    return {
        "status": "requires_stripe_sdk",
        "message": "Stripe key is configured. Wire Stripe Billing Portal SDK to create a hosted portal session.",
        "customer_id": summary["stripe"].get("customer_id"),
    }

@app.post("/api/v1/billing/webhook")
async def post_billing_webhook(request: Request, db: Session = Depends(get_db)):
    from services.shared.models import AuditLog

    body = await request.body()
    if not os.getenv("STRIPE_WEBHOOK_SECRET"):
        return {"status": "not_configured", "message": "Stripe webhook secret is not configured."}
    try:
        event = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail={"code": "invalid_webhook", "message": "Webhook body must be valid JSON."})
    db.add(
        AuditLog(
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            event_type="billing.webhook",
            entity_type="stripe_event",
            actor_type="system",
            action="billing.webhook.received",
            metadata_json={"event_type": event.get("type"), "event_id": event.get("id")},
        )
    )
    db.commit()
    return {"status": "received", "event_type": event.get("type"), "event_id": event.get("id")}

def _require_admin(user_id: UUID) -> None:
    raw = os.getenv("NEXUS_ADMIN_USER_IDS", "")
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    if str(user_id) not in allowed:
        raise HTTPException(status_code=403, detail={"code": "admin_required", "message": "Admin access required."})

@app.get("/api/v1/admin/users")
def get_admin_users(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import Subscription, User

    _require_admin(user_id)
    rows = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "users": [
            {
                "id": str(item.id),
                "email": item.email,
                "name": item.name,
                "auth_provider": item.auth_provider,
                "is_active": item.is_active,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "subscription": {
                    "plan": (
                        db.query(Subscription.plan_type, Subscription.status)
                        .filter(Subscription.user_id == item.id)
                        .order_by(Subscription.created_at.desc())
                        .first()
                        or ("free", "active")
                    )[0],
                    "status": (
                        db.query(Subscription.plan_type, Subscription.status)
                        .filter(Subscription.user_id == item.id)
                        .order_by(Subscription.created_at.desc())
                        .first()
                        or ("free", "active")
                    )[1],
                },
            }
            for item in rows
        ]
    }

@app.get("/api/v1/admin/usage")
def get_admin_usage(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from sqlalchemy import func
    from services.shared.models import UsageEvent
    from .pa_service import admin_usage_summary

    _require_admin(user_id)
    usage = db.query(func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.total_tokens), 0)).one()
    return {
        "usage_events": int(usage[0] or 0),
        "total_tokens": int(usage[1] or 0),
        "pa": admin_usage_summary(db),
    }

@app.get("/api/v1/admin/jobs")
def get_admin_jobs(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob

    _require_admin(user_id)
    rows = db.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(100).all()
    return {
        "jobs": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "mode": item.mode,
                "status": item.status,
                "approval_state": item.approval_state,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in rows
        ]
    }

@app.get("/api/v1/admin/audit-logs")
def get_admin_audit_logs(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AuditLog

    _require_admin(user_id)
    rows = db.query(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(100).all()
    return {
        "audit_logs": [
            {
                "id": item.id,
                "user_id": str(item.user_id),
                "event_type": item.event_type,
                "entity_type": item.entity_type,
                "entity_id": str(item.entity_id) if item.entity_id else None,
                "action": item.action,
                "metadata": item.metadata_json or {},
                "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
            }
            for item in rows
        ]
    }

def _pa_access(db: Session, user_id: UUID) -> dict:
    from .billing import check_entitlement

    entitlement = check_entitlement(db, user_id, "nexus_pa")
    plan = entitlement.get("plan") or "free"
    if entitlement.get("reason") == "unlimited_mode":
        return {
            "allowed": True,
            "plan": plan,
            "upgrade_target": None,
            "reason": "unlimited_mode",
        }
    return {
        "allowed": plan in {"pro", "enterprise"},
        "plan": plan,
        "upgrade_target": "pro",
        "reason": "paid_plan" if plan in {"pro", "enterprise"} else "pa_requires_pro",
    }

def _require_pa_access(db: Session, user_id: UUID) -> dict:
    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "upgrade_required",
                "message": "NEXUS PA requires Pro access.",
                "access": access,
            },
        )
    return access

@app.get("/api/v1/pa/access")
def get_pa_access(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return _pa_access(db, user_id)

@app.get("/api/v1/pa/os-status")
def get_pa_os_status(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_os import pa_os_status

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        return {"access": access, "locked": True}
    return {"access": access, **pa_os_status(db, user_id)}

@app.post("/api/v1/pa/os-status")
def post_pa_os_status(request: PAOSStateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_os import pa_os_status, set_pa_os_state

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"message": "NEXUS PA requires access", "access": access})
    set_pa_os_state(user_id, request.state)
    return {"access": access, **pa_os_status(db, user_id)}

@app.post("/api/v1/pa/emergency-stop")
def post_pa_emergency_stop(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_os import emergency_stop, pa_os_status

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"message": "NEXUS PA requires access", "access": access})
    stop = emergency_stop(user_id)
    return {"access": access, **pa_os_status(db, user_id), "emergency": stop}

@app.get("/api/v1/pa/daily-brief")
def get_pa_daily_brief(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import daily_brief

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        return {"access": access, "locked": True}
    return {"access": access, **daily_brief(db, user_id)}

@app.post("/api/v1/pa/schedule")
def post_pa_schedule(request: PAScheduleRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import smart_schedule

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"message": "NEXUS PA requires Pro", "access": access})
    return smart_schedule(db, user_id, request.task, request.duration_minutes, request.deadline)

@app.post("/api/v1/pa/meeting-prep")
def post_pa_meeting_prep(request: PAMeetingPrepRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import meeting_prep

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"message": "NEXUS PA requires Pro", "access": access})
    return meeting_prep(db, user_id, request.meeting_context)

@app.get("/api/v1/pa/end-of-day")
def get_pa_end_of_day(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import end_of_day_summary

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        return {"access": access, "locked": True}
    return {"access": access, **end_of_day_summary(db, user_id)}

@app.post("/api/v1/pa/delegate")
def post_pa_delegate(request: PADelegateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import delegate_task

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        raise HTTPException(status_code=402, detail={"message": "NEXUS PA requires Pro", "access": access})
    return delegate_task(db, user_id, request.instruction)

@app.get("/api/v1/pa/weekly-reflection")
def get_pa_weekly_reflection(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import weekly_reflection

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        return {"access": access, "locked": True}
    return {"access": access, **weekly_reflection(db, user_id)}

@app.get("/api/v1/pa/insights")
def get_pa_insights(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import insights

    access = _pa_access(db, user_id)
    if not access["allowed"]:
        return {"access": access, "locked": True}
    return {"access": access, **insights(db, user_id)}

@app.get("/api/v1/pa/today")
def get_pa_today(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import pa_today

    access = _require_pa_access(db, user_id)
    return {"access": access, **pa_today(db, user_id)}

@app.post("/api/v1/pa/command")
def post_pa_command(request: PACommandRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import handle_command
    from .usage import record_usage

    access = _require_pa_access(db, user_id)
    result = handle_command(db, user_id, request.command)
    record_usage(db, user_id, "/api/v1/pa/command", None, "autonomus-pa", None, request.command, json.dumps(result))
    return {"access": access, **result}

@app.get("/api/v1/pa/tasks")
def get_pa_tasks(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import list_tasks

    _require_pa_access(db, user_id)
    return {"tasks": list_tasks(db, user_id)}

@app.post("/api/v1/pa/tasks", status_code=201)
def post_pa_task(request: PATaskRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import create_task

    _require_pa_access(db, user_id)
    if not request.title.strip():
        raise HTTPException(status_code=400, detail={"code": "invalid_request", "message": "Task title is required."})
    return create_task(db, user_id, request.title, request.description, request.due_at, request.priority_score)

@app.patch("/api/v1/pa/tasks/{task_id}")
def patch_pa_task(task_id: UUID, request: PATaskUpdateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import update_task

    _require_pa_access(db, user_id)
    try:
        return update_task(db, user_id, task_id, request.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.delete("/api/v1/pa/tasks/{task_id}")
def delete_pa_task(task_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import delete_task

    _require_pa_access(db, user_id)
    try:
        return delete_task(db, user_id, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.get("/api/v1/pa/reminders")
def get_pa_reminders(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import list_schedules

    _require_pa_access(db, user_id)
    return {"reminders": list_schedules(db, user_id, "reminder")}

@app.post("/api/v1/pa/reminders", status_code=201)
def post_pa_reminder(request: PAScheduleItemRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import create_schedule

    _require_pa_access(db, user_id)
    return create_schedule(db, user_id, title=request.title, pa_type="reminder", next_run_at=request.next_run_at, trigger=request.trigger, permission=request.permission, payload=request.payload)

@app.patch("/api/v1/pa/reminders/{reminder_id}")
def patch_pa_reminder(reminder_id: UUID, request: PAScheduleItemUpdateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import update_schedule

    _require_pa_access(db, user_id)
    try:
        return update_schedule(db, user_id, reminder_id, request.model_dump(exclude_unset=True), "reminder")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.delete("/api/v1/pa/reminders/{reminder_id}")
def delete_pa_reminder(reminder_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import delete_schedule

    _require_pa_access(db, user_id)
    try:
        return delete_schedule(db, user_id, reminder_id, "reminder")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.get("/api/v1/pa/automations")
def get_pa_automations(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import list_schedules

    _require_pa_access(db, user_id)
    return {"automations": list_schedules(db, user_id, "automation")}

@app.post("/api/v1/pa/automations", status_code=201)
def post_pa_automation(request: PAScheduleItemRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import create_schedule

    _require_pa_access(db, user_id)
    return create_schedule(db, user_id, title=request.title, pa_type="automation", next_run_at=request.next_run_at, trigger=request.trigger, permission=request.permission, payload=request.payload)

@app.patch("/api/v1/pa/automations/{automation_id}")
def patch_pa_automation(automation_id: UUID, request: PAScheduleItemUpdateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import update_schedule

    _require_pa_access(db, user_id)
    try:
        return update_schedule(db, user_id, automation_id, request.model_dump(exclude_unset=True), "automation")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.get("/api/v1/pa/notifications")
def get_pa_notifications(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import list_notifications

    _require_pa_access(db, user_id)
    return {"notifications": list_notifications(db, user_id)}

@app.post("/api/v1/pa/notifications/{notification_id}/read")
def post_pa_notification_read(notification_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import mark_notification_read

    _require_pa_access(db, user_id)
    try:
        return mark_notification_read(db, user_id, notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})

@app.post("/api/v1/pa/pause")
def post_pa_pause(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import pause_pa

    _require_pa_access(db, user_id)
    return pause_pa(db, user_id)

@app.post("/api/v1/pa/resume")
def post_pa_resume(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .pa_service import resume_pa

    _require_pa_access(db, user_id)
    return resume_pa(db, user_id)

@app.get("/api/v1/pa/life-graph")
def get_pa_life_graph(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .jarvis_planner import life_graph

    return life_graph(db, user_id)

@app.get("/api/v1/models/registry")
def get_model_registry_status(user_id: UUID = Depends(get_current_user_id)):
    from .model_registry import registry_snapshot

    return registry_snapshot()

@app.get("/api/v1/models/gateway")
def get_model_gateway_status(user_id: UUID = Depends(get_current_user_id)):
    from .model_gateway import model_gateway

    return {
        "architecture": "provider_agnostic_model_gateway",
        "providers": sorted(model_gateway.providers.keys()),
        "default_provider": "nexus",
    }

@app.post("/api/v1/models/health-check")
def post_model_registry_health_check(user_id: UUID = Depends(get_current_user_id)):
    from .model_registry import health_check_registry

    return health_check_registry()

@app.get("/api/v1/agent/tools")
def get_agent_tools(
    category: Optional[str] = Query(None),
    include_disabled: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
):
    from .tool_registry import list_tools

    return {
        "tools": list_tools(category=category, include_disabled=include_disabled),
        "architecture": "supervisor_orchestrator_with_selected_tools",
    }

@app.post("/api/v1/agent/tools/select")
def post_agent_tool_selection(request: ToolSelectionRequest, user_id: UUID = Depends(get_current_user_id)):
    from .tool_registry import select_tools

    return select_tools(
        prompt=request.prompt,
        selected_mode=request.mode,
        max_tools=request.max_tools,
        include_high_risk=request.include_high_risk,
    )

@app.post("/api/v1/agent/tools/validate")
def post_agent_tool_validation(request: ToolValidationRequest, user_id: UUID = Depends(get_current_user_id)):
    from .tool_registry import validate_tool_request

    return validate_tool_request(request.tool_name, approved=request.approved)

@app.get("/api/v1/intelligence/personalization")
def get_personalization(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .learning_loop import get_personalization_context

    return get_personalization_context(db, user_id)

@app.get("/api/v1/os/context")
def get_nexus_os_context(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob, CodeSession, Goal, Memory, Schedule, Task

    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.is_archived == False, Memory.is_superseded == False)  # noqa: E712
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(5)
        .all()
    )
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status.in_(["active", "in_progress", "pending"]))
        .order_by(Goal.priority_score.desc(), Goal.updated_at.desc())
        .limit(5)
        .all()
    )
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status.in_(["queued", "pending", "in_progress", "active"]))
        .order_by(Task.priority_score.desc(), Task.updated_at.desc())
        .limit(6)
        .all()
    )
    schedules = (
        db.query(Schedule)
        .filter(Schedule.user_id == user_id, Schedule.is_active == True)  # noqa: E712
        .order_by(Schedule.next_run_at.asc())
        .limit(4)
        .all()
    )
    code_sessions = (
        db.query(CodeSession)
        .filter(CodeSession.user_id == user_id)
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .limit(4)
        .all()
    )
    jobs = (
        db.query(AgentJob)
        .filter(AgentJob.user_id == user_id)
        .order_by(AgentJob.created_at.desc())
        .limit(6)
        .all()
    )
    return {
        "memories": [
            {"id": str(item.id), "type": item.memory_type, "content": item.content[:280], "importance": item.importance}
            for item in memories
        ],
        "goals": [
            {"id": str(item.id), "title": item.title, "status": item.status, "progress_pct": item.progress_pct}
            for item in goals
        ],
        "tasks": [
            {"id": str(item.id), "title": item.title, "status": item.status, "priority_score": item.priority_score}
            for item in tasks
        ],
        "schedules": [
            {"id": str(item.id), "title": item.title, "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None}
            for item in schedules
        ],
        "code_sessions": [
            {"id": str(item.id), "title": item.title, "status": item.status, "updated_at": item.updated_at.isoformat() if item.updated_at else None}
            for item in code_sessions
        ],
        "jobs": [
            {"id": str(item.id), "mode": item.mode, "status": item.status, "approval_state": item.approval_state}
            for item in jobs
        ],
    }

class CodeSessionImportLocalRequest(BaseModel):
    local_path: str

@app.post("/api/v1/code/sessions/import-local", status_code=201)
def import_local_workspace_session(
    request: CodeSessionImportLocalRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    import os
    import hashlib
    import uuid
    from pathlib import Path
    from services.shared.models import CodeProject, CodeSession, FileReference
    from .file_service import put_object, storage_provider
    from .code_workspace import refresh_file_tree, serialize_code_session, _activity

    if not settings.LOCAL_WORKSPACE_IMPORT_ENABLED:
        raise HTTPException(status_code=403, detail="Local workspace import is disabled on this deployment.")

    local_root = Path(request.local_path).expanduser().resolve()
    allowed_roots = [
        Path(value).expanduser().resolve()
        for value in settings.LOCAL_WORKSPACE_ALLOWED_ROOTS.split(os.pathsep)
        if value.strip()
    ]
    if allowed_roots and not any(str(local_root).startswith(str(root)) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Local path is outside configured allowed workspace roots.")
    if not local_root.is_dir():
        raise HTTPException(status_code=400, detail="Provided local path is not a valid directory")

    local_path = str(local_root)
    project_name = local_root.name or "Local Project"

    # 1. Create project
    project = CodeProject(
        user_id=user_id,
        name=project_name,
        description=f"Local project imported from {local_path}",
        status="active"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # 2. Create session
    session = CodeSession(
        user_id=user_id,
        project_id=project.id,
        title=f"{project_name} workspace",
        file_ids=[],
        status="active",
        metadata_json={
            "local_workspace_path": local_path,
            "activity_log": [_activity("start", "Local workspace imported", f"Path: {local_path}")],
            "file_tree": [],
            "patch_preview": [],
            "rollback_snapshots": [],
        }
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 3. Recursively scan files and save references
    ignore_dirs = {".git", "node_modules", ".venv", "venv", ".next", "dist", "build", "__pycache__", ".pytest_cache"}
    file_ids = []
    skipped_errors = []

    count = 0
    for root_dir, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            filepath = os.path.join(root_dir, file)
            if os.path.islink(filepath) or os.path.getsize(filepath) > settings.LOCAL_WORKSPACE_MAX_FILE_BYTES:
                continue
            try:
                rel_path = os.path.relpath(filepath, local_path).replace("\\", "/")
                if rel_path.startswith("../") or rel_path == "..":
                    continue
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                if "\x00" in content:
                    continue

                record = FileReference(
                    user_id=user_id,
                    filename=rel_path,
                    size_bytes=len(content.encode("utf-8")),
                    owner_type="code_workspace",
                    owner_id=session.id,
                    storage_provider=storage_provider(),
                    bucket=settings.S3_BUCKET,
                    object_key=f"users/{user_id}/code/{session.id}/{uuid.uuid4()}{Path(rel_path).suffix or '.txt'}",
                    content_type="text/plain",
                    checksum_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    status="active",
                    metadata_json={"local_workspace_path": local_path, "local_relative_path": rel_path},
                )
                db.add(record)
                db.flush()

                put_object(record.object_key, content.encode("utf-8"), "text/plain")
                db.commit()
                db.refresh(record)
                file_ids.append(str(record.id))
                count += 1
                if count >= settings.LOCAL_WORKSPACE_MAX_FILES:
                    break
            except Exception as e:
                import logging
                logging.exception(f"Error importing local file {filepath}: {e}")
                db.rollback()
                if len(skipped_errors) < 8:
                    skipped_errors.append({"file": os.path.relpath(filepath, local_path).replace("\\", "/"), "error": str(e)})
                continue
        if count >= settings.LOCAL_WORKSPACE_MAX_FILES:
            break

    session.file_ids = file_ids
    db.commit()
    db.refresh(session)

    refresh_file_tree(db, user_id, session)
    payload = serialize_code_session(db, user_id, session)
    payload["skipped_errors"] = skipped_errors
    return payload

class CodeSessionSyncLocalFileRequest(BaseModel):
    action: str
    relative_path: str

@app.post("/api/v1/code/sessions/{session_id}/sync-local-file", status_code=200)
def sync_local_workspace_file(
    session_id: UUID,
    request: CodeSessionSyncLocalFileRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    import os
    import hashlib
    import uuid
    from pathlib import Path
    from services.shared.models import CodeSession, FileReference
    from .file_service import put_object, storage_provider
    from .code_workspace import refresh_file_tree, serialize_code_session
    
    session = db.query(CodeSession).filter(CodeSession.id == session_id, CodeSession.user_id == user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    local_path = session.metadata_json.get("local_workspace_path")
    if not local_path:
        raise HTTPException(status_code=400, detail="Not a local workspace session")
        
    rel_path = request.relative_path.replace("\\", "/")
    filepath = os.path.join(local_path, rel_path)
    
    if request.action == "unlink":
        record = db.query(FileReference).filter(FileReference.owner_id == session.id, FileReference.filename == rel_path).first()
        if record:
            db.delete(record)
            if str(record.id) in session.file_ids:
                session.file_ids = [fid for fid in session.file_ids if fid != str(record.id)]
            db.commit()
    else:
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File does not exist locally")
            
        if os.path.getsize(filepath) > settings.LOCAL_WORKSPACE_MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="File too large")
            
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        if "\x00" in content:
            raise HTTPException(status_code=400, detail="Binary files are not supported")
            
        record = db.query(FileReference).filter(FileReference.owner_id == session.id, FileReference.filename == rel_path).first()
        if not record:
            record = FileReference(
                user_id=user_id,
                filename=rel_path,
                size_bytes=len(content.encode("utf-8")),
                owner_type="code_workspace",
                owner_id=session.id,
                storage_provider=storage_provider(),
                bucket=settings.S3_BUCKET,
                object_key=f"users/{user_id}/code/{session.id}/{uuid.uuid4()}{Path(rel_path).suffix or '.txt'}",
                content_type="text/plain",
                checksum_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                status="active",
                metadata_json={"local_workspace_path": local_path, "local_relative_path": rel_path},
            )
            db.add(record)
            db.flush()
            
            session.file_ids = list(session.file_ids) + [str(record.id)]
        else:
            record.size_bytes = len(content.encode("utf-8"))
            record.checksum_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            
        put_object(record.object_key, content.encode("utf-8"), "text/plain")
        db.commit()
        
    refresh_file_tree(db, user_id, session)
    return serialize_code_session(db, user_id, session)

@app.post("/api/v1/code/sessions", status_code=201)
def create_code_session_endpoint(
    request: CodeSessionCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import create_code_session, serialize_code_session

    session = create_code_session(db, user_id, request.title, request.file_ids, project_id=request.project_id)
    return serialize_code_session(db, user_id, session)

@app.get("/api/v1/code/projects")
def list_code_projects_endpoint(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import active_session_for_project, list_code_projects, serialize_code_project

    projects = list_code_projects(db, user_id)
    return [serialize_code_project(project, active_session_for_project(db, user_id, project)) for project in projects]

@app.post("/api/v1/code/projects", status_code=201)
def create_code_project_endpoint(
    request: CodeProjectCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import create_code_project, serialize_code_project

    project, session = create_code_project(db, user_id, request.name, request.description, request.repo_url, request.file_ids)
    return {**serialize_code_project(project, session), "session": {"id": str(session.id), "title": session.title}}

@app.get("/api/v1/code/projects/{project_id}")
def get_code_project_endpoint(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import active_session_for_project, get_code_project, serialize_code_project

    project = get_code_project(db, user_id, project_id)
    return serialize_code_project(project, active_session_for_project(db, user_id, project))

@app.patch("/api/v1/code/projects/{project_id}")
def update_code_project_endpoint(
    project_id: UUID,
    request: CodeProjectUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import active_session_for_project, serialize_code_project, update_code_project

    project = update_code_project(db, user_id, project_id, request.name, request.description, request.repo_url, request.status)
    return serialize_code_project(project, active_session_for_project(db, user_id, project))

@app.delete("/api/v1/code/projects/{project_id}")
def archive_code_project_endpoint(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import update_code_project

    update_code_project(db, user_id, project_id, status="archived")
    return {"archived": True, "project_id": str(project_id)}

@app.get("/api/v1/code/sessions")
def list_code_sessions_endpoint(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import list_code_sessions, serialize_code_session

    return [serialize_code_session(db, user_id, session, include_files=False) for session in list_code_sessions(db, user_id)]

@app.get("/api/v1/code/sessions/{session_id}")
def get_code_session_endpoint(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, serialize_code_session

    session = get_code_session(db, user_id, session_id)
    return serialize_code_session(db, user_id, session)

@app.patch("/api/v1/code/sessions/{session_id}/files")
def update_code_session_files_endpoint(
    session_id: UUID,
    request: CodeSessionFilesUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, serialize_code_session, update_session_files

    session = get_code_session(db, user_id, session_id)
    session = update_session_files(db, user_id, session, request.file_ids)
    return serialize_code_session(db, user_id, session)

@app.post("/api/v1/code/sessions/{session_id}/import-zip")
def import_code_session_zip(
    session_id: UUID,
    upload: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, import_zip_project

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "import", upload.filename or "project.zip")
    result = import_zip_project(db, user_id, session, upload)
    complete_job(db, job, "completed", result, files_touched=result.get("imported") or [])
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/files")
def list_code_session_files(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import code_files, get_code_session

    session = get_code_session(db, user_id, session_id)
    return [{"id": str(record.id), "filename": record.filename, "size_bytes": record.size_bytes} for record in code_files(db, user_id, session)]

@app.get("/api/v1/code/sessions/{session_id}/search")
def search_code_session_files(
    session_id: UUID,
    q: str = Query(""),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, search_workspace_files

    session = get_code_session(db, user_id, session_id)
    return search_workspace_files(db, user_id, session, q)

@app.post("/api/v1/code/sessions/{session_id}/suggest-next")
def suggest_next_code_session_actions(
    session_id: UUID,
    request: CodeSuggestNextRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, suggest_next_actions

    session = get_code_session(db, user_id, session_id)
    return suggest_next_actions(
        db,
        user_id,
        session,
        user_description=request.user_description,
        selected_mode=request.selected_mode,
        selected_file_ids=request.selected_file_ids,
        open_file_ids=request.open_file_ids,
        current_prompt=request.current_prompt,
        recent_messages=request.recent_messages,
    )

@app.get("/api/v1/code/sessions/{session_id}/tasks")
def list_code_session_tasks(
    session_id: UUID,
    include_dismissed: bool = Query(False),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, list_workspace_tasks

    session = get_code_session(db, user_id, session_id)
    return list_workspace_tasks(db, user_id, session, include_dismissed=include_dismissed)

@app.post("/api/v1/code/sessions/{session_id}/tasks")
def create_code_session_task(
    session_id: UUID,
    request: CodeWorkspaceTaskRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, upsert_workspace_task

    session = get_code_session(db, user_id, session_id)
    return upsert_workspace_task(db, user_id, session, request.model_dump(), status=request.status or "typed")

@app.patch("/api/v1/code/tasks/{task_id}")
def update_code_workspace_task(
    task_id: UUID,
    request: CodeWorkspaceTaskUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import update_workspace_task

    return update_workspace_task(db, user_id, task_id, request.model_dump(exclude_unset=True))

@app.post("/api/v1/code/tasks/{task_id}/accept")
def accept_code_workspace_task(task_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import set_workspace_task_status

    return set_workspace_task_status(db, user_id, task_id, "accepted")

@app.post("/api/v1/code/tasks/{task_id}/dismiss")
def dismiss_code_workspace_task(task_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import set_workspace_task_status

    return set_workspace_task_status(db, user_id, task_id, "dismissed")

@app.post("/api/v1/code/sessions/{session_id}/analyze")
def analyze_code_session_workspace(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import analyze_workspace_structure, get_code_session

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "analyze", "Analyze workspace structure and code signals")
    result = analyze_workspace_structure(db, user_id, session)
    complete_job(db, job, "completed", result)
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/commands")
def list_code_session_commands(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import discover_workspace_commands, get_code_session

    session = get_code_session(db, user_id, session_id)
    return discover_workspace_commands(db, user_id, session)

@app.post("/api/v1/code/sessions/{session_id}/runtime/sync")
def sync_code_session_runtime(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, sync_workspace_runtime
    from .agent_jobs import create_agent_job, complete_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "runtime_sync", "Sync workspace files into persistent runtime")
    result = sync_workspace_runtime(db, user_id, session)
    complete_job(db, job, "completed", result, files_touched=[{"filename": path} for path in result.get("files_written") or []])
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/runtime/status")
def get_code_session_runtime_status(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, workspace_runtime_status

    session = get_code_session(db, user_id, session_id)
    return workspace_runtime_status(db, user_id, session)

@app.post("/api/v1/code/sessions/{session_id}/runtime/install")
def install_code_session_runtime(
    session_id: UUID,
    request: CodeRuntimeInstallRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, install_workspace_dependencies

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "runtime_install", request.command or "Install workspace dependencies", approval_state="approved" if request.approved else "pending")
    result = install_workspace_dependencies(db, user_id, session, request.command, request.approved, request.timeout_seconds, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/runtime/command")
def run_code_session_runtime_command(
    session_id: UUID,
    request: CodeCommandRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, run_workspace_command
    from .agent_jobs import create_agent_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(
        db,
        user_id,
        session.id,
        "runtime_command",
        request.command,
        approval_state="approved" if request.approved else "none",
    )
    result = run_workspace_command(db, user_id, session, request.command, request.timeout_seconds, request.approved, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/preview/start")
def start_code_session_preview(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, start_workspace_preview

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "preview_start", "Start live workspace preview")
    result = start_workspace_preview(db, user_id, session, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/preview/stop")
def stop_code_session_preview(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, stop_workspace_preview

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "preview_stop", "Stop live workspace preview")
    result = stop_workspace_preview(db, session, job)
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/preview/status")
def get_code_session_preview_status(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, preview_status

    session = get_code_session(db, user_id, session_id)
    return preview_status(session)

@app.get("/api/v1/code/sessions/{session_id}/preview/logs")
def get_code_session_preview_logs(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, read_preview_logs

    session = get_code_session(db, user_id, session_id)
    return read_preview_logs(session)

@app.api_route("/api/v1/code/sessions/{session_id}/preview/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_code_session_preview_path(session_id: UUID, path: str, request: Request, token: str = Query(""), db: Session = Depends(get_db)):
    from services.shared.models import CodeSession
    import httpx

    session = db.query(CodeSession).filter(CodeSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Code session not found")
    preview = (session.metadata_json or {}).get("preview_runtime") or {}
    if not token or token != preview.get("token"):
        raise HTTPException(status_code=403, detail="Preview token is invalid")
    local_url = str(preview.get("local_url") or "").rstrip("/")
    if not local_url:
        raise HTTPException(status_code=404, detail="Preview is not running")
    query = [(key, value) for key, value in request.query_params.multi_items() if key != "token"]
    query_string = ("?" + "&".join(f"{quote(key)}={quote(value)}" for key, value in query)) if query else ""
    target = f"{local_url}/{path}{query_string}"

    body = await request.body()
    headers = {key: value for key, value in request.headers.items() if key.lower() not in ("host", "authorization")}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=request.method,
                url=target,
                headers=headers,
                content=body,
                timeout=15.0,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={key: value for key, value in resp.headers.items() if key.lower() not in ("content-length", "transfer-encoding")},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream preview error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Preview proxy failed: {exc}")

@app.api_route("/api/v1/code/sessions/{session_id}/preview/proxy/", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_code_session_preview_root(session_id: UUID, request: Request, token: str = Query(""), db: Session = Depends(get_db)):
    return await proxy_code_session_preview_path(session_id, "", request, token, db)

@app.post("/api/v1/code/sessions/{session_id}/plan")
def plan_code_session(session_id: UUID, request: CodeInstructionRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import generate_plan, get_code_session
    from .agent_jobs import create_agent_job, serialize_job
    from .usage import record_usage

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "plan", request.instruction)
    plan = generate_plan(db, user_id, session, request.instruction, provider, model, job)
    record_usage(db, user_id, "/api/v1/code/plan", provider, model, str(session_id), request.instruction, plan, session.file_ids)
    return {"plan": plan, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/patch")
def patch_code_session(session_id: UUID, request: CodeInstructionRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import generate_patch, get_code_session
    from .agent_jobs import create_agent_job, serialize_job
    from .usage import record_usage

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "patch", request.instruction, approval_state="pending")
    patch = generate_patch(db, user_id, session, request.instruction, provider, model, job)
    record_usage(db, user_id, "/api/v1/code/patch", provider, model, str(session_id), request.instruction, patch, session.file_ids)
    return {"patch": patch, "session_id": str(session.id), "patch_preview": (session.metadata_json or {}).get("patch_preview") or [], "job": serialize_job(job)}

class CreatePullRequestRequest(BaseModel):
    branch_name: str
    title: str
    body: str

@app.post("/api/v1/code/sessions/{session_id}/create-pr")
def create_session_pr(
    session_id: UUID,
    request: CreatePullRequestRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session
    from .github_service import create_pull_request

    session = get_code_session(db, user_id, session_id)
    if not session.project:
        raise HTTPException(status_code=400, detail="This session is not associated with any Code Project.")

    result = create_pull_request(
        db,
        user_id,
        session.project,
        session,
        request.branch_name,
        request.title,
        request.body,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@app.post("/api/v1/code/sessions/{session_id}/hunks/{hunk_id}/approve")
def approve_patch_hunk(
    session_id: UUID,
    hunk_id: str,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, _metadata, _set_metadata

    session = get_code_session(db, user_id, session_id)
    metadata = _metadata(session)
    hunks_state = metadata.get("patch_hunks_state") or {}
    hunks_state[hunk_id] = "approved"
    metadata["patch_hunks_state"] = hunks_state

    previews = metadata.get("patch_preview") or []
    for file_prev in previews:
        for hunk in file_prev.get("hunks") or []:
            if hunk.get("id") == hunk_id:
                hunk["status"] = "approved"

    _set_metadata(session, metadata)
    db.commit()
    return {"status": "success", "hunk_id": hunk_id, "state": "approved"}

@app.post("/api/v1/code/sessions/{session_id}/hunks/{hunk_id}/reject")
def reject_patch_hunk(
    session_id: UUID,
    hunk_id: str,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, _metadata, _set_metadata

    session = get_code_session(db, user_id, session_id)
    metadata = _metadata(session)
    hunks_state = metadata.get("patch_hunks_state") or {}
    hunks_state[hunk_id] = "rejected"
    metadata["patch_hunks_state"] = hunks_state

    previews = metadata.get("patch_preview") or []
    for file_prev in previews:
        for hunk in file_prev.get("hunks") or []:
            if hunk.get("id") == hunk_id:
                hunk["status"] = "rejected"

    _set_metadata(session, metadata)
    db.commit()
    return {"status": "success", "hunk_id": hunk_id, "state": "rejected"}

@app.get("/api/v1/code/sessions/{session_id}/diagnostics")
def get_session_diagnostics(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session
    from .diagnostics import run_diagnostics_checks

    session = get_code_session(db, user_id, session_id)
    diagnostics = run_diagnostics_checks(db, user_id, session)
    return {"diagnostics": diagnostics}

def _run_code_background_job(
    job_id: str,
    user_id: str,
    session_id: str,
    instruction: str,
    provider: str | None,
    model: str | None,
    run_patch: bool,
) -> None:
    from services.shared.database import SessionLocal
    from .agent_jobs import append_job_log, complete_job, get_agent_job
    from .code_workspace import generate_patch, generate_plan, get_code_session
    from .usage import record_usage

    db = SessionLocal()
    try:
        user_uuid = UUID(user_id)
        session_uuid = UUID(session_id)
        job_uuid = UUID(job_id)
        job = get_agent_job(db, user_uuid, job_uuid)
        session = get_code_session(db, user_uuid, session_uuid)
        if job.status == "cancelled":
            return
        append_job_log(db, job, "code", "Background plan started", instruction[:220])
        plan = generate_plan(db, user_uuid, session, instruction, provider, model, job, finalize_job=False)
        if job.status == "cancelled":
            return
        patch = ""
        preview = []
        if run_patch:
            append_job_log(db, job, "edit", "Background patch started", "Patch will remain pending until reviewed.")
            patch = generate_patch(db, user_uuid, session, instruction, provider, model, job, finalize_job=False)
            preview = (session.metadata_json or {}).get("patch_preview") or []
        result = {
            "plan": plan,
            "patch": patch,
            "patch_preview": preview,
            "summary": (session.metadata_json or {}).get("patch_summary") or "",
        }
        record_usage(db, user_uuid, "/api/v1/code/background-run", provider, model, str(session_uuid), instruction, "\n".join([plan, patch]), session.file_ids)
        complete_job(
            db,
            job,
            "completed",
            result,
            files_touched=[{"file_id": item["file_id"], "filename": item["filename"]} for item in preview],
            approval_state="pending" if preview else "none",
        )
    except Exception as exc:
        try:
            job = get_agent_job(db, UUID(user_id), UUID(job_id))
            complete_job(db, job, "failed", {"error": str(exc)})
        except Exception:
            pass
    finally:
        db.close()

@app.post("/api/v1/code/sessions/{session_id}/run-background", status_code=202)
def run_code_session_background(
    session_id: UUID,
    request: CodeBackgroundRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    mode = request.mode if request.mode in {"plan", "code"} else "code"

    # Enqueue job with queued status and pass model configurations
    job = create_agent_job(
        db,
        user_id,
        session.id,
        f"background_{mode}",
        request.instruction,
        approval_state="pending" if mode == "code" else "none",
        status="queued",
        metadata_json={"llm_provider": provider, "llm_model": model}
    )
    return {"status": "queued", "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/agent-loop")
async def run_code_session_agent_loop(
    session_id: UUID,
    request: CodeAgentLoopRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .agent_orchestrator import run_controlled_workspace_agent
    from .code_workspace import get_code_session

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "agent_loop", request.task)
    result = await run_controlled_workspace_agent(
        db,
        user_id,
        session,
        task=request.task,
        provider_name=provider,
        model_name=model,
        max_steps=request.max_steps,
        approved_tools=request.approved_tools,
        job=job,
    )
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/patch-preview")
def preview_code_session_patch(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, preview_patch_payload

    session = get_code_session(db, user_id, session_id)
    return {"patch_preview": preview_patch_payload(db, user_id, session)}

@app.post("/api/v1/code/sessions/{session_id}/reject")
def reject_code_session_patch(
    session_id: UUID,
    request: Optional[CodePatchSelectionRequest] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, reject_patch_payload

    session = get_code_session(db, user_id, session_id)
    return reject_patch_payload(db, session, request.file_ids if request else None)

class MobileSystemStatusRequest(BaseModel):
    battery_level: int
    is_charging: bool
    network_type: str
    active_apps: List[str]

class CallInterceptRequest(BaseModel):
    caller_number: str
    direction: str = "incoming"

class VoiceTelemetryRequest(BaseModel):
    stt_ms: float
    llm_ms: float
    tts_ms: float
    network_ms: float = 20.0

@app.post("/api/v1/pa/system-status")
def post_pa_system_status(request: MobileSystemStatusRequest, user_id: UUID = Depends(get_current_user_id)):
    from .pa_os.mobile_daemon import MobileOSDaemon
    daemon = MobileOSDaemon(user_id)
    status = daemon.update_system_status(
        request.battery_level,
        request.is_charging,
        request.network_type,
        request.active_apps,
    )
    return {"status": "success", "system_status": status}

@app.post("/api/v1/pa/calls/intercept")
def intercept_pa_call(request: CallInterceptRequest, user_id: UUID = Depends(get_current_user_id)):
    from .pa_os.mobile_daemon import MobileOSDaemon
    daemon = MobileOSDaemon(user_id)
    call = daemon.intercept_call(request.caller_number, request.direction)
    return {"status": "success", "call": call}

@app.post("/api/v1/pa/voice/telemetry")
def log_pa_voice_telemetry(request: VoiceTelemetryRequest, user_id: UUID = Depends(get_current_user_id)):
    from .pa_os.voice_pipeline import VoiceTelemetryTracker
    tracker = VoiceTelemetryTracker()
    log = tracker.log_latency(
        session_id="pa-voice-session",
        stt_ms=request.stt_ms,
        llm_ms=request.llm_ms,
        tts_ms=request.tts_ms,
        network_ms=request.network_ms,
    )
    return {"status": "success", "telemetry": log}

@app.post("/api/v1/code/sessions/{session_id}/run-command")
def run_code_session_command(
    session_id: UUID,
    request: CodeCommandRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, run_workspace_command
    from .agent_jobs import create_agent_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "command", request.command)
    result = run_workspace_command(db, user_id, session, request.command, request.timeout_seconds, job)
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/github/status")
def get_github_app_status(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .github_service import github_status

    return github_status(db, user_id)

@app.get("/api/v1/github/install-url")
def get_github_app_install_url(user_id: UUID = Depends(get_current_user_id)):
    from .github_service import github_install_url

    return github_install_url(user_id, JWT_SECRET_KEY)

@app.get("/api/v1/github/callback")
def github_app_callback(
    installation_id: str = Query(""),
    state: str = Query(""),
    setup_action: str = Query(""),
    db: Session = Depends(get_db),
):
    from .github_service import handle_github_callback

    if not installation_id:
        raise HTTPException(status_code=400, detail="GitHub installation_id is missing")
    result = handle_github_callback(db, installation_id, state, JWT_SECRET_KEY)
    frontend = settings.FRONTEND_URL.rstrip("/")
    return Response(
        content=(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>GitHub connected</title></head><body style='font-family:sans-serif;background:#08080c;color:#f5f5f5;padding:32px'>"
            "<h2>GitHub connected</h2><p>You can close this tab and return to NEXUS Code.</p>"
            f"<script>setTimeout(function(){{location.href='{frontend}/workspace?github=connected'}},700)</script>"
            "</body></html>"
        ),
        media_type="text/html",
    )

@app.get("/api/v1/github/repositories")
def list_github_app_repositories(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .github_service import list_repositories

    return list_repositories(db, user_id)

@app.post("/api/v1/code/sessions/{session_id}/github/import")
def github_import_code_session(
    session_id: UUID,
    request: GitHubSessionImportRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, refresh_file_tree, update_project_files_from_session, append_activity
    from .github_service import import_repository

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_import", request.repository)
    result = import_repository(db, user_id, session, request.repository, request.branch)
    refresh_file_tree(db, user_id, session)
    update_project_files_from_session(db, session)
    append_activity(db, session, "read", "GitHub repository imported", f"{len(result.get('imported') or [])} file(s) imported from {request.repository}")
    complete_job(db, job, "completed", result, files_touched=result.get("imported") or [])
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/github/branch")
def github_create_code_session_branch(
    session_id: UUID,
    request: GitHubBranchRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, append_activity
    from .github_service import create_branch

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_branch", request.branch_name or "Create GitHub branch", approval_state="approved")
    result = create_branch(db, user_id, session, request.branch_name, request.base_branch)
    append_activity(db, session, "done", "GitHub branch ready", f"{result['branch_name']} from {result['base_branch']}")
    complete_job(db, job, "completed", result, approval_state="approved")
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/github/commit")
def github_commit_code_session_changes(
    session_id: UUID,
    request: GitHubCommitRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, append_activity
    from .github_service import commit_approved_changes

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_commit", request.message or "Commit approved NEXUS Code changes", approval_state="approved")
    result = commit_approved_changes(db, user_id, session, request.message)
    append_activity(db, session, "done", "GitHub commit created", f"{len(result.get('committed') or [])} file(s) committed to {result.get('branch_name')}")
    complete_job(db, job, "completed", result, files_touched=result.get("committed") or [], approval_state="approved")
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/github/pr")
def github_open_code_session_pr(
    session_id: UUID,
    request: GitHubPullRequestRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, append_activity
    from .github_service import open_pull_request

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_pr", request.title or "Open GitHub pull request", approval_state="approved")
    result = open_pull_request(db, user_id, session, request.title, request.body)
    append_activity(db, session, "done", "GitHub pull request opened", result.get("pull_request_url") or "")
    complete_job(db, job, "completed", result, approval_state="approved")
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/github/pr-status")
def github_code_session_pr_status(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session
    from .github_service import pr_status

    session = get_code_session(db, user_id, session_id)
    return pr_status(db, user_id, session)

@app.post("/api/v1/code/sessions/{session_id}/run-checks")
def run_code_session_checks(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import get_code_session, run_workspace_checks
    from .agent_jobs import create_agent_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "checks", "Run workspace build/test/lint/typecheck checks")
    result = run_workspace_checks(db, user_id, session, job=job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/preview-check")
def check_code_session_preview(
    session_id: UUID,
    request: CodePreviewCheckRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import check_preview_url, get_code_session
    from .agent_jobs import create_agent_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "preview", request.url)
    result = check_preview_url(db, session, request.url, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/fix-preview")
def fix_code_session_preview_issue(
    session_id: UUID,
    request: CodeFixPreviewRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import generate_patch, generate_plan, get_code_session, read_preview_logs
    from .usage import record_usage

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    metadata = session.metadata_json or {}
    preview_checks = metadata.get("preview_checks") or []
    latest_check = preview_checks[-1] if preview_checks else {}
    preview_logs = read_preview_logs(session)
    if not latest_check and not preview_logs.get("logs"):
        raise HTTPException(status_code=400, detail="Run a preview check or start live preview before asking NEXUS to fix preview issues.")
    issue_instruction = "\n".join([
        "Fix the latest workspace preview issue.",
        f"Preview URL: {latest_check.get('url') or 'unknown'}",
        f"Status: {latest_check.get('status')} HTTP {latest_check.get('status_code')}",
        f"Title: {latest_check.get('title') or ''}",
        f"Issues: {', '.join(latest_check.get('issues') or []) or 'No explicit marker; inspect likely frontend/runtime causes.'}",
        f"Live preview command: {preview_logs.get('command') or 'unknown'}",
        f"Live preview log issues: {', '.join(preview_logs.get('issues') or []) or 'none detected'}",
        f"Live preview logs:\n{preview_logs.get('logs') or '(no live preview logs)'}",
        f"User instruction: {request.instruction}".strip(),
        "Prepare a safe patch only. Do not assume production deployment access.",
    ])
    job = create_agent_job(db, user_id, session.id, "fix_preview", issue_instruction, approval_state="pending")
    plan = generate_plan(db, user_id, session, issue_instruction, provider, model)
    patch = generate_patch(db, user_id, session, issue_instruction, provider, model, job)
    record_usage(db, user_id, "/api/v1/code/fix-preview", provider, model, str(session_id), issue_instruction, patch, session.file_ids)
    return {
        "plan": plan,
        "patch": patch,
        "patch_preview": (session.metadata_json or {}).get("patch_preview") or [],
        "job": serialize_job(job),
    }

@app.post("/api/v1/code/sessions/{session_id}/git/connect")
def connect_code_session_git(
    session_id: UUID,
    request: CodeGitConnectRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import connect_git_repository, get_code_session

    session = get_code_session(db, user_id, session_id)
    return connect_git_repository(db, session, request.repo_url, request.default_branch)

@app.post("/api/v1/code/sessions/{session_id}/git/import")
def import_code_session_github_repo(
    session_id: UUID,
    request: CodeGitImportRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import get_code_session, import_github_repository

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_import", request.repo_url)
    result = import_github_repository(db, user_id, session, request.repo_url, request.branch)
    complete_job(db, job, "completed", result, files_touched=result.get("imported") or [])
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/git/status")
def get_code_session_git_status(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, git_status

    session = get_code_session(db, user_id, session_id)
    return git_status(session)

@app.post("/api/v1/code/sessions/{session_id}/git/prepare-pr")
def prepare_code_session_pull_request(
    session_id: UUID,
    request: CodePreparePullRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, prepare_pull_request

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "git", request.title or session.title)
    result = prepare_pull_request(db, session, request.title, request.description, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/git/open-pr")
def open_code_session_pull_request(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, open_github_pull_request

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "github_pr", "Open GitHub pull request", approval_state="approved")
    result = open_github_pull_request(db, user_id, session, job)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/inline-edit")
def inline_edit_code_selection(
    session_id: UUID,
    request: InlineCodeEditRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from langchain_core.messages import HumanMessage, SystemMessage
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import append_activity, get_code_session
    from .llm_router import get_chat_llm
    from .usage import record_usage

    if not request.instruction.strip():
        raise HTTPException(status_code=400, detail="Inline edit instruction is required")
    if not request.selected_text.strip():
        raise HTTPException(status_code=400, detail="Select code before using inline edit")
    if len(request.selected_text) > 20000:
        raise HTTPException(status_code=413, detail="Selected code is too large for inline edit")

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "inline_edit", request.instruction, approval_state="pending")
    llm = get_chat_llm(role="coding", provider=provider, model=model)
    prompt = (
        f"Filename: {request.filename}\n"
        f"Instruction: {request.instruction}\n\n"
        "Selected code:\n"
        f"```\n{request.selected_text}\n```\n\n"
        "Return only the replacement code for the selected region. "
        "Do not include markdown fences, explanation, or surrounding unchanged file content."
    )
    response = llm.invoke([
        SystemMessage(content="You are NEXUS Code inline edit mode. Rewrite only the selected code. Preserve style and APIs."),
        HumanMessage(content=prompt),
    ])
    replacement = str(response.content).strip()
    if replacement.startswith("```"):
        lines = replacement.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        replacement = "\n".join(lines).strip()
    append_activity(db, session, "edit", f"Inline edit prepared for {request.filename or request.file_id}", request.instruction[:220])
    complete_job(db, job, "completed", {"replacement": replacement, "filename": request.filename}, files_touched=[{"file_id": str(request.file_id), "filename": request.filename}], approval_state="pending")
    record_usage(db, user_id, "/api/v1/code/inline-edit", provider, model, str(session_id), prompt, replacement, [str(request.file_id)])
    return {"replacement": replacement, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/complete")
def complete_code_at_cursor(
    session_id: UUID,
    request: CodeCompletionRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from langchain_core.messages import HumanMessage, SystemMessage
    from .agent_jobs import create_agent_job, complete_job, serialize_job
    from .code_workspace import append_activity, get_code_session
    from .llm_router import get_chat_llm
    from .usage import record_usage

    if not request.prefix.strip():
        raise HTTPException(status_code=400, detail="Completion needs code before the cursor")
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "completion", request.filename, approval_state="pending")
    llm = get_chat_llm(role="coding", provider=provider, model=model)
    prompt = (
        f"Filename: {request.filename}\n\n"
        "Code before cursor:\n"
        f"```\n{request.prefix[-12000:]}\n```\n\n"
        "Code after cursor:\n"
        f"```\n{request.suffix[:6000]}\n```\n\n"
        "Return only the next useful code to insert at the cursor. "
        "Keep it short, syntactically consistent, and do not repeat existing code."
    )
    response = llm.invoke([
        SystemMessage(content="You are NEXUS Code autocomplete. Return only insertable code, no markdown or explanation."),
        HumanMessage(content=prompt),
    ])
    completion = str(response.content).strip()
    if completion.startswith("```"):
        lines = completion.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        completion = "\n".join(lines).strip()
    append_activity(db, session, "edit", f"Completion prepared for {request.filename or request.file_id}", completion[:220])
    complete_job(db, job, "completed", {"completion": completion, "filename": request.filename}, files_touched=[{"file_id": str(request.file_id), "filename": request.filename}], approval_state="pending")
    record_usage(db, user_id, "/api/v1/code/complete", provider, model, str(session_id), prompt, completion, [str(request.file_id)])
    return {"completion": completion, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/apply")
def apply_code_session_patch(
    session_id: UUID,
    request: Optional[CodePatchSelectionRequest] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import apply_patch_payload, get_code_session
    from .agent_jobs import create_agent_job, serialize_job

    session = get_code_session(db, user_id, session_id)
    job = create_agent_job(db, user_id, session.id, "apply", "Apply approved workspace patch", approval_state="approved")
    result = apply_patch_payload(db, user_id, session, job, request.file_ids if request else None)
    return {**result, "job": serialize_job(job)}

@app.post("/api/v1/code/sessions/{session_id}/rollback")
def rollback_code_session_patch(
    session_id: UUID,
    request: Optional[CodeRollbackRequest] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import create_agent_job, serialize_job
    from .code_workspace import get_code_session, rollback_snapshot

    session = get_code_session(db, user_id, session_id)
    prompt = f"Rollback workspace snapshot {request.snapshot_id}" if request and request.snapshot_id else "Rollback last applied workspace patch"
    job = create_agent_job(db, user_id, session.id, "rollback", prompt, approval_state="approved")
    result = rollback_snapshot(db, user_id, session, request.snapshot_id if request else None, job)
    return {**result, "job": serialize_job(job)}

@app.get("/api/v1/code/sessions/{session_id}/rollback-snapshots")
def list_code_session_rollback_snapshots(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import get_code_session, list_rollback_snapshots

    session = get_code_session(db, user_id, session_id)
    return list_rollback_snapshots(session)

@app.post("/api/v1/code/jobs", status_code=201)
def create_agent_job_endpoint(request: AgentJobCreateRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import create_agent_job, serialize_job

    job = create_agent_job(db, user_id, request.code_session_id, request.mode, request.prompt, request.approval_state)
    return serialize_job(job)

@app.get("/api/v1/code/jobs")
def list_agent_jobs_endpoint(
    code_session_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import list_agent_jobs, serialize_job

    return [serialize_job(job) for job in list_agent_jobs(db, user_id, code_session_id)]

@app.get("/api/v1/code/jobs/{job_id}")
def get_agent_job_endpoint(job_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import get_agent_job, serialize_job

    return serialize_job(get_agent_job(db, user_id, job_id))

@app.get("/api/v1/code/jobs/{job_id}/logs/stream")
def stream_agent_job_logs(job_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    import time
    from services.shared.database import SessionLocal
    from .agent_jobs import get_agent_job, serialize_job

    def event_stream():
        sent = 0
        deadline = time.time() + 60
        while time.time() < deadline:
            db_stream = SessionLocal()
            try:
                job = get_agent_job(db_stream, user_id, job_id)
                payload = serialize_job(job)
                logs = payload.get("logs") or []
                for log in logs[sent:]:
                    yield f"event: log\ndata: {json.dumps(log)}\n\n"
                sent = len(logs)
                yield f"event: status\ndata: {json.dumps({'status': payload.get('status'), 'progress': payload.get('progress')})}\n\n"
                if payload.get("status") not in {"running", "queued"}:
                    yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                    break
            finally:
                db_stream.close()
            time.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/api/v1/code/jobs/{job_id}/cancel")
def cancel_agent_job_endpoint(job_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .agent_jobs import cancel_agent_job, serialize_job

    return serialize_job(cancel_agent_job(db, user_id, job_id))

@app.post("/api/v1/code/jobs/{job_id}/retry", status_code=202)
def retry_agent_job_endpoint(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .agent_jobs import reset_background_job_for_retry, serialize_job

    job = reset_background_job_for_retry(db, user_id, job_id)
    return {"status": "queued", "job": serialize_job(job)}

@app.get("/api/v1/code/worker/status")
def get_code_worker_status(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from services.shared.models import AgentJob
    from .worker import worker_queue

    queued = db.query(AgentJob).filter(AgentJob.user_id == user_id, AgentJob.status == "queued").count()
    running = db.query(AgentJob).filter(AgentJob.user_id == user_id, AgentJob.status == "running").count()
    interrupted = db.query(AgentJob).filter(AgentJob.user_id == user_id, AgentJob.status.in_(["timeout", "interrupted"])).count()
    return {
        **worker_queue.status(),
        "queued_jobs": queued,
        "running_jobs": running,
        "interrupted_jobs": interrupted,
    }

@app.post("/api/v1/code/generate")
def nexus_code_generate(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, generate_code_task, safety_check

    access = check_entitlement(db, user_id, "code_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Code generation limit reached", "access": access})
    guard = safety_check(request.instruction, "code_generate")
    if not guard.get("allowed"):
        raise HTTPException(status_code=400, detail=guard["reason"])
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    context = "\n\n".join([request.context, build_uploaded_context(db, user_id, request.file_ids, request.instruction)]).strip()
    result = generate_code_task("generate", request.instruction, context, NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/code/generate", provider, model, None, request.instruction, result.get("content", ""), request.file_ids)
    return result

@app.get("/api/v1/code/activity-stream")
async def code_activity_stream(
    prompt: str = "",
    mode: str = "auto",
    user_id: UUID = Depends(get_current_user_id),
):
    from .workspace_orchestrator import planned_activity, sse
    import asyncio

    async def generate():
        for event in planned_activity(prompt, mode):
            yield sse(event)
            await asyncio.sleep(0.12)

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/v1/code/debug")
def nexus_code_debug(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, generate_code_task

    access = check_entitlement(db, user_id, "code_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Code generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    context = "\n\n".join([request.context, build_uploaded_context(db, user_id, request.file_ids, request.instruction)]).strip()
    result = generate_code_task("debug", request.instruction, context, NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/code/debug", provider, model, None, request.instruction, result.get("content", ""), request.file_ids)
    return result

@app.post("/api/v1/code/refactor")
def nexus_code_refactor(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, generate_code_task

    access = check_entitlement(db, user_id, "code_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Code generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    context = "\n\n".join([request.context, build_uploaded_context(db, user_id, request.file_ids, request.instruction)]).strip()
    result = generate_code_task("refactor", request.instruction, context, NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/code/refactor", provider, model, None, request.instruction, result.get("content", ""), request.file_ids)
    return result

@app.post("/api/v1/code/explain")
def nexus_code_explain(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .nexus_services import NexusLLMConfig, explain_code

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    context = "\n\n".join([request.context, build_uploaded_context(db, user_id, request.file_ids, request.instruction)]).strip()
    return explain_code(request.instruction, context, NexusLLMConfig(provider, model))

@app.post("/api/v1/code/test")
def nexus_code_test(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, generate_code_task

    access = check_entitlement(db, user_id, "code_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Code generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    context = "\n\n".join([request.context, build_uploaded_context(db, user_id, request.file_ids, request.instruction)]).strip()
    result = generate_code_task("test", request.instruction, context, NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/code/test", provider, model, None, request.instruction, result.get("content", ""), request.file_ids)
    return result

@app.post("/api/v1/code/execute")
def nexus_code_execute(request: NexusCodeRequest, user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import safety_check

    guard = safety_check(request.instruction, "code_execute")
    return {
        "status": "approval_required",
        "risk": guard,
        "message": "Code execution is not run directly in production yet. Configure Docker or E2B sandbox, then approve execution per task.",
    }

@app.post("/api/v1/internet/research")
def nexus_internet_research(request: NexusResearchRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import build_research_report
    from .tools import web_search

    access = check_entitlement(db, user_id, "web_search")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Web research limit reached", "access": access})
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    try:
        raw = web_search.invoke({"query": request.query})
        if isinstance(raw, str):
            report = f"# Research Report: {request.query}\n\n## Live Findings\n{raw}"
            from .usage import record_usage
            record_usage(db, user_id, "/api/v1/internet/research", None, "web-search", None, request.query, report)
            return {"query": request.query, "report": report}
        results = raw
    except Exception:
        results = []
    report = build_research_report(request.query, results if isinstance(results, list) else [])
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/internet/research", None, "web-search", None, request.query, report)
    return {"query": request.query, "report": report}

@app.post("/api/v1/internet/browse")
def nexus_internet_browse(request: NexusBrowseRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from urllib.request import Request, urlopen
    from .billing import check_entitlement
    from .nexus_services import browse_summary

    access = check_entitlement(db, user_id, "web_search")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Web research limit reached", "access": access})
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http and https URLs are supported.")
    try:
        req = Request(request.url, headers={"User-Agent": "NEXUS-AI-Research/1.0"})
        with urlopen(req, timeout=10) as response:
            raw = response.read(200000)
        text = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Browse failed: {exc}")
    result = browse_summary(request.url, text)
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/internet/browse", None, "browser-read", None, request.url, result.get("summary", ""))
    return result

@app.get("/api/v1/internet/free-tiers")
def nexus_internet_free_tiers(user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import FREE_TIER_CATALOG

    return {"items": FREE_TIER_CATALOG}

@app.post("/api/v1/internet/setup-service")
def nexus_setup_service(request: FreeTierRecommendRequest, user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import recommend_free_tiers

    return {
        "status": "approval_required",
        "recommendations": recommend_free_tiers(request.project_type, request.needs),
        "message": "Service signup and credential storage require explicit approval before any browser automation or token storage.",
    }

@app.get("/api/v1/free-tiers/catalog")
def nexus_free_tier_catalog(user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import FREE_TIER_CATALOG

    return {"items": FREE_TIER_CATALOG}

@app.get("/api/v1/free-tiers/recommend")
def nexus_free_tier_recommend_get(
    project_type: str = "",
    needs: str = "",
    user_id: UUID = Depends(get_current_user_id),
):
    from .nexus_services import recommend_free_tiers

    return {"items": recommend_free_tiers(project_type, needs)}

@app.post("/api/v1/free-tiers/recommend")
def nexus_free_tier_recommend_post(request: FreeTierRecommendRequest, user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import recommend_free_tiers

    return {"items": recommend_free_tiers(request.project_type, request.needs)}

@app.post("/api/v1/design/generate-ui")
def nexus_design_generate_ui(request: NexusDesignRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, design_response

    access = check_entitlement(db, user_id, "ui_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "UI generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    result = design_response(request.description, request.output_type or "ui", NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/design/generate-ui", provider, model, None, request.description, result.get("content", ""))
    return result

@app.post("/api/v1/design/variants")
def nexus_design_variants(request: NexusDesignRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, design_variants

    access = check_entitlement(db, user_id, "ui_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "UI generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    result = design_variants(request.description, request.output_type or "page", NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/design/variants", provider, model, None, request.description, json.dumps(result))
    return result

@app.post("/api/v1/design/generate-page")
def nexus_design_generate_page(request: NexusDesignRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, design_response

    access = check_entitlement(db, user_id, "ui_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "UI generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    result = design_response(request.description, "page", NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/design/generate-page", provider, model, None, request.description, result.get("content", ""))
    return result

@app.post("/api/v1/design/animate")
def nexus_design_animate(request: NexusDesignRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, design_response

    access = check_entitlement(db, user_id, "ui_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "UI generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    result = design_response(request.description, "animation", NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/design/animate", provider, model, None, request.description, result.get("content", ""))
    return result

@app.post("/api/v1/design/critique")
def nexus_design_critique(request: NexusDesignRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import NexusLLMConfig, design_response

    access = check_entitlement(db, user_id, "ui_generation")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "UI generation limit reached", "access": access})
    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    result = design_response(request.description, "critique", NexusLLMConfig(provider, model))
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/design/critique", provider, model, None, request.description, result.get("content", ""))
    return result

@app.get("/api/v1/design/components")
def nexus_design_components(user_id: UUID = Depends(get_current_user_id)):
    return {
        "items": [
            {"name": "Command Center Shell", "type": "layout", "uses": "Agent workspaces and dashboards"},
            {"name": "Streaming Answer Panel", "type": "ai", "uses": "Chat, interview, research"},
            {"name": "Diff Review Table", "type": "code", "uses": "Approve/reject code changes"},
            {"name": "Deployment Timeline", "type": "deploy", "uses": "Realtime deploy progress"},
            {"name": "Usage Meter", "type": "analytics", "uses": "Token and cost visibility"},
        ]
    }

@app.post("/api/v1/deploy/analyze")
def nexus_deploy_analyze(request: NexusDeployAnalyzeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .nexus_services import deployment_analysis

    result = deployment_analysis(request.project_type, request.repo_context)
    from .usage import record_usage
    record_usage(db, user_id, "/api/v1/deploy/analyze", None, "deploy-analyzer", None, request.project_type, json.dumps(result))
    return result

@app.post("/api/v1/deploy/start")
def nexus_deploy_start(request: NexusDeployAnalyzeRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement
    from .nexus_services import deployment_analysis

    access = check_entitlement(db, user_id, "deployment")
    if not access.get("allowed"):
        raise HTTPException(status_code=402, detail={"message": "Deployment is locked or limit reached", "access": access})
    return {
        "status": "approval_required",
        "analysis": deployment_analysis(request.project_type, request.repo_context),
        "message": "Deployment can change production infrastructure, so it requires explicit approval and configured provider tokens.",
    }

@app.get("/api/v1/deploy/history")
def nexus_deploy_history(user_id: UUID = Depends(get_current_user_id)):
    return {"items": []}

@app.get("/api/v1/intelligence/suggestions")
def nexus_intelligence_suggestions(context: str = "", user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import proactive_suggestions

    return {"items": proactive_suggestions(context)}

@app.post("/api/v1/intelligence/feedback")
def nexus_intelligence_feedback(request: NexusSuggestionFeedbackRequest, user_id: UUID = Depends(get_current_user_id)):
    return {"status": "recorded", "suggestion_id": request.suggestion_id, "feedback": request.feedback}

@app.get("/api/v1/intelligence/insights")
def nexus_intelligence_insights(user_id: UUID = Depends(get_current_user_id)):
    return {
        "summary": "NEXUS intelligence is active. Connect deployment logs, code repositories, and usage budgets for richer weekly insights.",
        "signals": ["code", "deployment", "usage", "interview", "security"],
    }

@app.post("/api/v1/safety/check")
def nexus_safety_check(request: NexusSafetyRequest, user_id: UUID = Depends(get_current_user_id)):
    from .nexus_services import safety_check

    return safety_check(request.content, request.action)

class CompressRequest(BaseModel):
    user_id: str

class NewsItem(BaseModel):
    title: str
    snippet: str | None = None
    link: str
    source: str
    published_at: str | None = None

class NewsResponse(BaseModel):
    query: str
    items: List[NewsItem]

class JobItem(BaseModel):
    title: str
    company: str
    location: str
    apply_url: str
    source: str
    published_at: str | None = None
    tags: List[str] = Field(default_factory=list)

class JobsResponse(BaseModel):
    query: str
    items: List[JobItem]

@app.post("/api/v1/memories/compress")
def trigger_memory_compression(request: CompressRequest):
    from uuid import UUID
    from services.shared.database import SessionLocal
    from .memory_agent import compress_memories

    db = SessionLocal()
    try:
        user_uuid = UUID(request.user_id)
        count = compress_memories(db, user_uuid)
        return {"compressed_clusters_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post("/api/v1/memories/extract")
def extract_memory_endpoint(
    request: MemoryExtractRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    from .memory_agent import extract_memories

    return {"memories": extract_memories(user_id, request.conversation)}

@app.delete("/api/v1/memories/hard-delete")
def hard_delete_memories(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    return PostgresMemoryStore(db).hard_delete_user_memories(user_id)

@app.post("/api/v1/sessions/{session_id}/memory")
def append_session_memory(
    session_id: str,
    event: SessionMemoryEvent,
    user_id: UUID = Depends(get_current_user_id),
):
    from .memory_agent import RedisShortTermMemoryStore

    result = RedisShortTermMemoryStore().append_event(user_id, session_id, event.model_dump())
    return {"session_id": session_id, **result}

@app.get("/api/v1/sessions/{session_id}/memory", response_model=SessionMemoryResponse)
def get_session_memory(
    session_id: str,
    limit: int = 50,
    user_id: UUID = Depends(get_current_user_id),
):
    from .memory_agent import RedisShortTermMemoryStore

    return {
        "session_id": session_id,
        "events": RedisShortTermMemoryStore().read_events(user_id, session_id, limit=limit),
    }

@app.get("/api/v1/news/live", response_model=NewsResponse)
def get_live_news(
    query: str = "AI agents OR autonomous AI",
    limit: int = 8,
    user_id: UUID = Depends(get_current_user_id),
):
    from .tools import fetch_live_news

    try:
        items = fetch_live_news(query, limit=limit)
        return {"query": query, "items": items}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Live news lookup failed: {e}")

@app.get("/api/v1/jobs/live", response_model=JobsResponse)
def get_live_jobs(
    query: str = "AI engineer remote",
    limit: int = 8,
    user_id: UUID = Depends(get_current_user_id),
):
    from .tools import fetch_live_jobs

    try:
        items = fetch_live_jobs(query, limit=limit)
        return {"query": query, "items": items}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Live job lookup failed: {e}")

@app.get("/api/v1/agents/autonomy/status")
def autonomy_status(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .autonomy import get_autonomy_status

    return get_autonomy_status(db, user_id)

@app.post("/api/v1/agents/autonomy/run")
def run_autonomy(
    request: AutonomyRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .autonomy import run_autonomous_cycle

    return run_autonomous_cycle(db, user_id, max_tasks=request.max_tasks, dry_run=request.dry_run)

@app.patch("/api/v1/agents/autonomy/level")
def update_autonomy_level(
    request: AutonomyLevelUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .autonomy import get_or_create_user_profile

    profile = get_or_create_user_profile(db, user_id)
    profile.autonomy_level = request.autonomy_level
    db.commit()
    return {"autonomy_level": profile.autonomy_level}

@app.get("/api/v1/memories", response_model=List[MemoryResponse])
def get_memories(
    memory_type: str | None = None,
    include_archived: bool = False,
    page: int = 1,
    page_size: int = 20,
    user_id: UUID = Depends(get_current_user_id),
    x_vault_key: str | None = Header(None, alias="x-vault-key"),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    page, page_size, offset = clamp_pagination(page, page_size)
    vk = parse_vault_key(x_vault_key)
    memories = PostgresMemoryStore(db, vault_key=vk).list_memories(
        user_id=user_id,
        memory_type=memory_type,
        include_archived=include_archived,
        limit=page * page_size,
    )
    return memories[offset:offset + page_size]

@app.get("/api/v1/memories/summary")
def get_memory_transparency_summary(
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .nexus_services import memory_transparency_summary

    memories = db.query(Memory).filter(Memory.user_id == user_id)
    if not include_archived:
        memories = memories.filter(Memory.is_archived == False)  # noqa: E712
    return memory_transparency_summary(memories.order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(200).all())

@app.post("/api/v1/memories", response_model=MemoryResponse, status_code=201)
def create_memory(
    memory_in: MemoryCreate,
    user_id: UUID = Depends(get_current_user_id),
    x_vault_key: str | None = Header(None, alias="x-vault-key"),
    db: Session = Depends(get_db),
):
    from .memory_agent import MemoryWrite, PostgresMemoryStore

    vk = parse_vault_key(x_vault_key)
    memory, _ = PostgresMemoryStore(db, vault_key=vk).create_memory(
        user_id,
        MemoryWrite(
            content=memory_in.content,
            type=memory_in.type,
            memory_type=memory_in.memory_type,
            importance=memory_in.importance,
            confidence=memory_in.confidence,
            source=memory_in.source,
            source_session_id=memory_in.source_session_id,
            source_url=memory_in.source_url,
            tags=memory_in.tags,
            meta_data=memory_in.meta_data,
        ),
    )
    return memory

@app.get("/api/v1/memories/search")
def search_memories(
    query: str,
    limit: int = 10,
    memory_type: str | None = None,
    user_id: UUID = Depends(get_current_user_id),
    x_vault_key: str | None = Header(None, alias="x-vault-key"),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    vk = parse_vault_key(x_vault_key)
    return PostgresMemoryStore(db, vault_key=vk).hybrid_search(user_id, query, limit=limit, memory_type=memory_type)

@app.patch("/api/v1/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    memory_in: MemoryUpdate,
    user_id: UUID = Depends(get_current_user_id),
    x_vault_key: str | None = Header(None, alias="x-vault-key"),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    vk = parse_vault_key(x_vault_key)
    return PostgresMemoryStore(db, vault_key=vk).update_memory(
        memory,
        **memory_in.model_dump(exclude_unset=True),
    )

@app.delete("/api/v1/memories/{memory_id}")
def archive_memory(
    memory_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    x_vault_key: str | None = Header(None, alias="x-vault-key"),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    vk = parse_vault_key(x_vault_key)
    PostgresMemoryStore(db, vault_key=vk).archive_memory(memory)
    return {"message": "Memory archived successfully"}

@app.get("/api/v1/vault/status", response_model=VaultStatusResponse)
def get_vault_status(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from services.shared.models import UserVault
    from .schemas import VaultStatusResponse

    vault = db.query(UserVault).filter(UserVault.user_id == user_id).first()
    if not vault:
        return VaultStatusResponse(exists=False)
    return VaultStatusResponse(exists=True, salt=vault.salt, vault_version=vault.vault_version)

@app.post("/api/v1/vault/setup")
def setup_vault(
    payload: VaultSetupRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from services.shared.models import UserVault
    from .schemas import VaultSetupRequest

    existing = db.query(UserVault).filter(UserVault.user_id == user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vault already set up")

    vault = UserVault(
        user_id=user_id,
        salt=payload.salt,
        recovery_hash=payload.recovery_hash,
        vault_version=1,
        is_active=True
    )
    db.add(vault)
    db.commit()
    return {"message": "Vault set up successfully"}
