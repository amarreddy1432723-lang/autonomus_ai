import json
import os
import jwt
from uuid import UUID
from fastapi import FastAPI, Depends, Header, HTTPException, status
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
from .schemas import MemoryResponse, MemoryUpdate

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
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

def get_current_user_id(
    authorization: str | None = Header(None), 
    x_user_id: str | None = Header(None, alias="x-user-id")
) -> UUID:
    # 1. Try Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id_str = payload.get("sub")
            if user_id_str:
                return UUID(user_id_str)
        except Exception:
            pass
            
    # 2. Try X-User-Id fallback
    if x_user_id:
        try:
            return UUID(x_user_id)
        except ValueError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials missing or invalid."
    )

class ChatMessage(BaseModel):
    role: str # "user", "assistant"
    content: str
    
class ChatRequest(BaseModel):
    user_id: str
    messages: List[ChatMessage]

async def chat_stream_generator(user_id: str, prompt: str, chat_history: List[ChatMessage]):
    from .brain import brain_agent
    
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
    
    try:
        async for event in brain_agent.astream_events(input_state, version="v2"):
            kind = event.get("event")
            node_name = event.get("metadata", {}).get("langgraph_node", "")
            
            if kind == "on_chain_start" and event.get("name") == "LangGraph":
                yield f"event: thinking\ndata: {json.dumps({'status': 'started'})}\n\n"
                
            elif kind == "on_chain_start" and node_name:
                yield f"event: thinking\ndata: {json.dumps({'node': node_name, 'status': 'running'})}\n\n"
                
            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield f"event: token\ndata: {json.dumps({'token': chunk.content})}\n\n"
                    
            elif kind == "on_tool_start":
                tool_name = event.get("name")
                inputs = event["data"].get("input")
                yield f"event: tool_start\ndata: {json.dumps({'tool': tool_name, 'inputs': inputs})}\n\n"
                
            elif kind == "on_tool_end":
                tool_name = event.get("name")
                output = event["data"].get("output")
                yield f"event: tool_end\ndata: {json.dumps({'tool': tool_name, 'output': str(output)})}\n\n"
                
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
        chat_stream_generator(request.user_id, prompt, history),
        media_type="text/event-stream"
    )

class CompressRequest(BaseModel):
    user_id: str

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

@app.get("/api/v1/memories", response_model=List[MemoryResponse])
def get_memories(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return db.query(Memory).filter(Memory.user_id == user_id).all()

@app.get("/api/v1/memories/search")
def search_memories(query: str, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .llm_router import get_embedding_vector
    from .memory_agent import cosine_distance_py
    
    try:
        query_vec = get_embedding_vector(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate query embedding: {e}")
        
    memories = db.query(Memory).filter(Memory.user_id == user_id).all()
    
    results = []
    for m in memories:
        if m.vector:
            m_vec = m.vector
            if isinstance(m_vec, str):
                import json
                try:
                    m_vec = json.loads(m_vec)
                except Exception:
                    continue
            distance = cosine_distance_py(query_vec, m_vec)
            similarity = 1.0 - distance
            results.append({
                "id": m.id,
                "content": m.content,
                "type": m.type,
                "importance": m.importance,
                "confidence": m.confidence,
                "similarity": similarity,
                "created_at": m.created_at,
                "tags": m.tags or []
            })
            
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:10]

@app.patch("/api/v1/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: UUID,
    memory_in: MemoryUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    if memory_in.content is not None:
        memory.content = memory_in.content
    if memory_in.type is not None:
        memory.type = memory_in.type
    if memory_in.memory_type is not None:
        memory.memory_type = memory_in.memory_type
    if memory_in.importance is not None:
        memory.importance = memory_in.importance
    if memory_in.confidence is not None:
        memory.confidence = memory_in.confidence
    if memory_in.tags is not None:
        memory.tags = memory_in.tags

    meta = memory.meta_data or {}
    if memory_in.meta_data is not None:
        meta.update(memory_in.meta_data)
    if memory_in.is_archived is not None:
        memory.is_archived = memory_in.is_archived
        meta["is_archived"] = memory_in.is_archived
    memory.meta_data = meta

    db.commit()
    db.refresh(memory)
    return memory

@app.delete("/api/v1/memories/{memory_id}")
def archive_memory(
    memory_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    memory = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    memory.is_archived = True
    meta = memory.meta_data or {}
    meta["is_archived"] = True
    memory.meta_data = meta

    db.commit()
    return {"message": "Memory archived successfully"}
