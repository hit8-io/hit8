"""
FastAPI application entrypoint.
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import yaml
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin.exceptions import FirebaseError
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from app.config import settings
from app.deps import verify_google_token
from app.graph import AgentState, create_graph, _get_langfuse_handler
from app.logging_utils import configure_structlog

# Initialize structlog before other imports that might use logging
configure_structlog()

# Load logging configuration from config.yaml
def setup_logging() -> None:
    """Setup logging from config.yaml."""
    config_file = Path(__file__).parent / "config.yaml"
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    with open(config_file) as f:
        config_data = yaml.safe_load(f)
        if config_data is None:
            config_data = {}
    
    env = "prod" if os.getenv("ENVIRONMENT") == "prod" else "dev"
    defaults = config_data.get("defaults", {})
    env_config = config_data.get(env, {})
    
    # Merge logging config (env overrides defaults)
    logging_config = defaults.get("logging", {})
    if "logging" in env_config:
        logging_config = {**logging_config, **env_config["logging"]}
    
    if logging_config:
        logging.config.dictConfig(logging_config)

# Setup logging at module level
setup_logging()

logger = structlog.get_logger(__name__)


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
    logger.warning(
        "firebase_authentication_failed",
        error=str(exc),
        path=request.url.path,
        method=request.method,
    )
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
    
    # Get Langfuse callback handler if enabled
    langfuse_handler = _get_langfuse_handler()
    
    # Prepare config with callbacks and metadata
    config: dict[str, Any] = {}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        logger.debug(
            "langfuse_callback_handler_added",
            handler_type=type(langfuse_handler).__name__,
        )
    
    # Add metadata for Langfuse tracing
    env = "prod" if os.getenv("ENVIRONMENT") == "prod" else "dev"
    metadata: dict[str, Any] = {
        "langfuse_user_id": user_id,
        "env": env,
    }
    if settings.langfuse_customer:
        metadata["customer"] = settings.langfuse_customer
    if settings.langfuse_project:
        metadata["project"] = settings.langfuse_project
    
    config["metadata"] = metadata
    
    result = graph.invoke(initial_state, config=config)
    ai_message = extract_ai_message(result["messages"])
    content = extract_message_content(ai_message.content)
    
    # Flush Langfuse traces to ensure they're sent
    if langfuse_handler and settings.langfuse_enabled:
        try:
            from langfuse import get_client
            get_client().flush()
        except Exception as e:
            logger.warning(
                "langfuse_flush_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
    
    return ChatResponse(response=content, user_id=user_id)

