"""
FastAPI application entrypoint.
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.deps import verify_google_token
from app.graph import create_graph, AgentState

# Initialize FastAPI app
app = FastAPI(title="Hit8 Chat API", version="1.0.0")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
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
    """
    Chat endpoint that processes user messages through LangGraph.

    Requires valid Google Identity Platform (Firebase Auth) ID token in Authorization header.
    """
    try:
        # Extract user ID from token payload
        user_id = user_payload.get("sub") or user_payload.get("user_id", "unknown")
        
        # Initialize state with user message
        initial_state: AgentState = {
            "messages": [HumanMessage(content=request.message)],
            "context": ""
        }
        
        # Run the graph
        result = graph.invoke(initial_state)
        
        # Extract the last AI message
        messages = result.get("messages", [])
        ai_messages = [msg for msg in messages if hasattr(msg, "content") and not isinstance(msg, HumanMessage)]
        
        if ai_messages:
            content = ai_messages[-1].content
            # Gemini 3 Pro returns content as a list of dicts with 'text' field
            if isinstance(content, list) and len(content) > 0:
                # Extract text from the first item in the list
                if isinstance(content[0], dict) and 'text' in content[0]:
                    response_text = content[0]['text']
                else:
                    response_text = str(content[0])
            elif isinstance(content, str):
                response_text = content
            else:
                response_text = str(content)
        else:
            response_text = "I apologize, but I couldn't generate a response."
        
        return ChatResponse(response=response_text, user_id=user_id)
    
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"Chat error: {error_detail}")  # Log to console for debugging
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )

