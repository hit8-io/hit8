"""
FastAPI application entrypoint.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin.exceptions import FirebaseError
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from app.config import settings
from app.deps import verify_google_token
from app.graph import AgentState, create_graph

logger = logging.getLogger(__name__)


def parse_doppler_secrets() -> None:
    """Parse Doppler secrets JSON if provided (for Cloud Run)."""
    if doppler_secrets_json := os.getenv("DOPPLER_SECRETS_JSON"):
        secrets = json.loads(doppler_secrets_json)
        # Set individual environment variables from Doppler secrets
        for key, value in secrets.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = str(value)


def get_cors_headers(request: Request) -> dict[str, str]:
    """Get CORS headers for the given request."""
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin and origin in settings.cors_allow_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def extract_message_content(content: Any) -> str:
    """Extract message content, handling various formats."""
    if isinstance(content, list):
        # If content is a list (e.g., from multimodal responses), join or take first
        if content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"]
        elif content and isinstance(content[0], str):
            return content[0]
        else:
            return str(content)
    elif not isinstance(content, str):
        return str(content)
    return content


def extract_ai_message(messages: list[BaseMessage]) -> BaseMessage:
    """Extract the last AI message from the message list."""
    ai_messages = [msg for msg in messages if not isinstance(msg, HumanMessage)]
    if not ai_messages:
        raise ValueError("No AI response generated")
    return ai_messages[-1]


# Parse Doppler secrets at module level
parse_doppler_secrets()

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


# Exception handlers to ensure CORS headers are included in error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions and ensure CORS headers are included."""
    headers = dict(exc.headers) if exc.headers else {}
    headers.update(get_cors_headers(request))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(FirebaseError)
async def firebase_exception_handler(request: Request, exc: FirebaseError):
    """Handle Firebase errors and ensure CORS headers are included."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Authentication failed"},
        headers=get_cors_headers(request),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and ensure CORS headers are included."""
    # Log the error for debugging
    logger.exception("Unhandled exception", exc_info=exc)
    
    # Determine error message based on exception type
    if isinstance(exc, ValueError):
        detail = str(exc)
    else:
        detail = "Internal server error"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
        headers=get_cors_headers(request),
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
    ai_message = extract_ai_message(result["messages"])
    content = extract_message_content(ai_message.content)
    
    return ChatResponse(response=content, user_id=user_id)

