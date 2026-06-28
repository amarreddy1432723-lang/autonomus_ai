import json
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from langchain_core.messages import HumanMessage, AIMessage

from .config import settings
from services.shared.error_handler import register_error_handlers
from services.shared.rate_limiter import RateLimitHeaderMiddleware

app = FastAPI(title="my-ai Agent Service", version="1.0.0")
app.add_middleware(RateLimitHeaderMiddleware)
register_error_handlers(app)

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
