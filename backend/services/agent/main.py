import json
import os
import jwt
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status, File, UploadFile
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
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonlychangeinprod!")
JWT_ALGORITHM = "HS256"

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.shared.database import SessionLocal, verify_default_user
    db = SessionLocal()
    try:
        verify_default_user(db)
    finally:
        db.close()
    yield

app = FastAPI(title="my-ai Agent Service", version="1.0.0", lifespan=lifespan)
install_api_foundation(app, "agent-service")
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

def get_current_user_id(
    authorization: str | None = Header(None), 
    x_user_id: str | None = Header(None, alias="x-user-id"),
    db: Session = Depends(get_db),
) -> UUID:
    return resolve_user_id_from_auth_or_clerk(db, authorization, x_user_id, JWT_SECRET_KEY, JWT_ALGORITHM)

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

EXPOSED_CHAT_MODELS: dict[str, tuple[str, str]] = {
    "autonomus-ai-v1": ("autonomus", "autonomus-ai-v1"),
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

class CodeSessionCreate(BaseModel):
    title: str = "Code workspace"
    file_ids: List[str] = Field(default_factory=list)

class CodeInstructionRequest(BaseModel):
    instruction: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

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
async def chat_endpoint(request: ChatRequest, user_id: UUID = Depends(get_current_user_id)):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
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
        ),
        media_type="text/event-stream"
    )

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

@app.post("/api/v1/files", status_code=201)
async def upload_file(
    upload: UploadFile = File(...),
    owner_type: str = "chat",
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .file_service import create_file_reference, extract_file_to_chunks

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

@app.post("/api/v1/code/sessions", status_code=201)
def create_code_session_endpoint(
    request: CodeSessionCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .code_workspace import create_code_session

    session = create_code_session(db, user_id, request.title, request.file_ids)
    return {"id": str(session.id), "title": session.title, "file_ids": session.file_ids, "status": session.status}

@app.get("/api/v1/code/sessions/{session_id}/files")
def list_code_session_files(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import code_files, get_code_session

    session = get_code_session(db, user_id, session_id)
    return [{"id": str(record.id), "filename": record.filename, "size_bytes": record.size_bytes} for record in code_files(db, user_id, session)]

@app.post("/api/v1/code/sessions/{session_id}/plan")
def plan_code_session(session_id: UUID, request: CodeInstructionRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import generate_plan, get_code_session
    from .usage import record_usage

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    plan = generate_plan(db, user_id, session, request.instruction, provider, model)
    record_usage(db, user_id, "/api/v1/code/plan", provider, model, str(session_id), request.instruction, plan, session.file_ids)
    return {"plan": plan}

@app.post("/api/v1/code/sessions/{session_id}/patch")
def patch_code_session(session_id: UUID, request: CodeInstructionRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import generate_patch, get_code_session
    from .usage import record_usage

    provider, model = resolve_exposed_chat_model(request.llm_provider, request.llm_model)
    session = get_code_session(db, user_id, session_id)
    patch = generate_patch(db, user_id, session, request.instruction, provider, model)
    record_usage(db, user_id, "/api/v1/code/patch", provider, model, str(session_id), request.instruction, patch, session.file_ids)
    return {"patch": patch}

@app.post("/api/v1/code/sessions/{session_id}/apply")
def apply_code_session_patch(session_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .code_workspace import apply_patch_payload, get_code_session

    session = get_code_session(db, user_id, session_id)
    return apply_patch_payload(db, user_id, session)

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
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    page, page_size, offset = clamp_pagination(page, page_size)
    memories = PostgresMemoryStore(db).list_memories(
        user_id=user_id,
        memory_type=memory_type,
        include_archived=include_archived,
        limit=page * page_size,
    )
    return memories[offset:offset + page_size]

@app.post("/api/v1/memories", response_model=MemoryResponse, status_code=201)
def create_memory(
    memory_in: MemoryCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .memory_agent import MemoryWrite, PostgresMemoryStore

    memory, _ = PostgresMemoryStore(db).create_memory(
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
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    return PostgresMemoryStore(db).hybrid_search(user_id, query, limit=limit, memory_type=memory_type)

@app.patch("/api/v1/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    memory_in: MemoryUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return PostgresMemoryStore(db).update_memory(
        memory,
        **memory_in.model_dump(exclude_unset=True),
    )

@app.delete("/api/v1/memories/{memory_id}")
def archive_memory(
    memory_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    from .memory_agent import PostgresMemoryStore

    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    PostgresMemoryStore(db).archive_memory(memory)
    return {"message": "Memory archived successfully"}
