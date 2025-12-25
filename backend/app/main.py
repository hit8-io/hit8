"""
FastAPI application entrypoint.
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.config import settings
from app.deps import verify_google_token
from app.graph import create_graph, AgentState

# Initialize FastAPI app
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the graph
graph = create_graph()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    user_id: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_payload: dict = Depends(verify_google_token)
):
    """Chat endpoint that processes user messages through LangGraph."""
    user_id = user_payload["sub"]
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=request.message)]
    }
    
    result = graph.invoke(initial_state)
    messages = result["messages"]
    ai_messages = [msg for msg in messages if not isinstance(msg, HumanMessage)]
    
    if not ai_messages:
        return ChatResponse(response="I apologize, but I couldn't generate a response.", user_id=user_id)
    
    ai_message = ai_messages[-1]
    
    # Extract content - handle both string and list formats
    content = ai_message.content
    if isinstance(content, list):
        # Gemini returns content as list of dicts with 'text' field
        content = content[0].get('text', '') if content and isinstance(content[0], dict) else str(content[0])
    elif not isinstance(content, str):
        content = str(content)
    
    return ChatResponse(response=content, user_id=user_id)

