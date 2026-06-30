import json
import os
import jwt
from uuid import UUID
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from langchain_core.messages import HumanMessage, AIMessage
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from .config import settings
from services.shared.database import get_db
from services.shared.models import Memory
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware
from services.shared.api import clamp_pagination, install_api_foundation
from services.shared.security import resolve_user_id_from_auth
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
    x_user_id: str | None = Header(None, alias="x-user-id")
) -> UUID:
    return resolve_user_id_from_auth(authorization, x_user_id, JWT_SECRET_KEY, JWT_ALGORITHM)

class ChatMessage(BaseModel):
    role: str # "user", "assistant"
    content: str
    
class ChatRequest(BaseModel):
    user_id: str
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

async def chat_stream_generator(
    user_id: str,
    prompt: str,
    chat_history: List[ChatMessage],
    session_id: str = "default",
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
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
        "user_id": user_id
    }
    
    config = {
        "configurable": {
            "session_id": session_id,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
        }
    }
    
    assistant_text = []
    stm = RedisShortTermMemoryStore()
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
        if final_text:
            stm.append_event(user_id, session_id, {"role": "assistant", "content": final_text})
        try:
            extract_memories(UUID(user_id), "\n".join([prompt, final_text]))
        except Exception:
            pass
        yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

@app.post("/api/v1/agents/chat")
async def chat_endpoint(request: ChatRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
    prompt = request.messages[-1].content
    history = request.messages[:-1]
    
    return StreamingResponse(
        chat_stream_generator(
            request.user_id,
            prompt,
            history,
            request.session_id or "default",
            request.llm_provider,
            request.llm_model,
        ),
        media_type="text/event-stream"
    )

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
