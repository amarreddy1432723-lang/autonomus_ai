import json
import uuid
import time
from typing import Any, List, Optional, Iterator
from pydantic import Field
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from langchain_core.messages import AIMessage, BaseMessage, ToolCall, AIMessageChunk

class MockChatOpenAI(BaseChatModel):
    model_name: str = Field(default="mock-gpt-4o-mini")
    
    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        # Return self, tools can be ignored for simple mock replies
        return self
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        chunks = list(self._stream(messages, stop, run_manager, **kwargs))
        final_message = chunks[0].message
        for chunk in chunks[1:]:
            final_message += chunk.message
            
        # Compile tool calls explicitly if present
        tool_calls = []
        for chunk in chunks:
            if hasattr(chunk.message, "tool_calls") and chunk.message.tool_calls:
                tool_calls.extend(chunk.message.tool_calls)
        if tool_calls:
            final_message.tool_calls = tool_calls
            
        return ChatResult(generations=[ChatGeneration(message=final_message)])
        
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        last_msg = messages[-1].content.lower()
        
        # Determine if this is the intent classification prompt
        is_classification = False
        for msg in messages:
            if msg.type == "system" and "intent classifier" in msg.content.lower():
                is_classification = True
                break
                
        if is_classification:
            intent = "general_chat"
            if "goal" in last_msg or "build" in last_msg or "launch" in last_msg:
                intent = "goal_creation"
            elif "task" in last_msg or "todo" in last_msg or "create a task" in last_msg:
                intent = "task_creation"
            elif "search" in last_msg or "pricing" in last_msg or "find" in last_msg:
                intent = "execution"
                
            response_content = json.dumps({"intent": intent})
            yield ChatGenerationChunk(message=AIMessageChunk(content=response_content))
        else:
            # Check if this requires a tool call (e.g., search/pricing or read file)
            if "search" in last_msg or "pricing" in last_msg:
                call_id = f"call_{uuid.uuid4().hex}"
                tool_call = ToolCall(
                    name="web_search",
                    args={"query": last_msg},
                    id=call_id
                )
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_calls=[tool_call],
                        tool_call_chunks=[
                            {
                                "name": "web_search",
                                "args": json.dumps({"query": last_msg}),
                                "id": call_id,
                                "index": 0
                            }
                        ]
                    )
                )
            elif "read" in last_msg and "file" in last_msg:
                file_name = "test.txt"
                if "read file" in last_msg:
                    parts = last_msg.split("read file")
                    if len(parts) > 1:
                        file_name = parts[1].strip().split()[0].strip("'\"")
                call_id = f"call_{uuid.uuid4().hex}"
                tool_call = ToolCall(
                    name="read_file",
                    args={"file_path": file_name},
                    id=call_id
                )
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_calls=[tool_call],
                        tool_call_chunks=[
                            {
                                "name": "read_file",
                                "args": json.dumps({"file_path": file_name}),
                                "id": call_id,
                                "index": 0
                            }
                        ]
                    )
                )
            else:
                # Standard chat responses
                if "name is" in last_msg:
                    response_content = "Nice to meet you! I have saved your name to memory."
                elif "clerk" in last_msg:
                    response_content = "Using Clerk provides dynamic user authentication, which could save you about 6 hours."
                else:
                    response_content = "I am your Autonomous Personal AI Agent. I will help you plan and execute your goals."
                
                words = response_content.split(" ")
                for i, word in enumerate(words):
                    content_chunk = word + (" " if i < len(words) - 1 else "")
                    yield ChatGenerationChunk(message=AIMessageChunk(content=content_chunk))
                    time.sleep(0.01)
                
    @property
    def _llm_type(self) -> str:
        return "mock-chat-openai"
