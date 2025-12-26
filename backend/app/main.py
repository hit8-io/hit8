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

from app.logging_utils import configure_structlog

# Initialize structlog before other imports that might use logging
configure_structlog()

# Parse Doppler secrets FIRST, before importing settings
# This ensures environment variables are set before Settings initialization
def parse_doppler_secrets() -> None:
    """Parse Doppler secrets JSON if provided (for Cloud Run)."""
    if doppler_secrets_json := os.getenv("DOPPLER_SECRETS_JSON"):
        try:
            secrets = json.loads(doppler_secrets_json)
            # Set individual environment variables from Doppler secrets
            for key, value in secrets.items():
                if key not in os.environ:  # Don't override existing env vars
                    os.environ[key] = str(value)
        except json.JSONDecodeError:
            # Invalid JSON, continue with existing env vars
            pass

# Parse Doppler secrets at module level BEFORE importing settings
parse_doppler_secrets()

# Now import settings after secrets are parsed
from app.config import settings, get_metadata
from app.deps import verify_google_token
from app.graph import AgentState, create_graph, _get_langfuse_handler

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
    
    env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
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
    
    # Add metadata for Langfuse tracing using centralized metadata
    centralized_metadata = get_metadata()
    metadata: dict[str, Any] = {
        "langfuse_user_id": user_id,
        **centralized_metadata,  # Includes environment, customer, project
    }
    logger.debug(
        "langfuse_metadata_constructed",
        environment=centralized_metadata["environment"],
        customer=centralized_metadata["customer"],
        project=centralized_metadata["project"],
    )
    
    config["metadata"] = metadata
    
    result = graph.invoke(initial_state, config=config)
    ai_message = extract_ai_message(result["messages"])
    content = extract_message_content(ai_message.content)
    
    # Flush Langfuse traces to ensure they're sent
    # Critical in serverless/production environments where the process may terminate quickly
    if langfuse_handler and settings.langfuse_enabled:
        try:
            from langfuse import get_client
            langfuse_client = get_client()
            
            # In production/serverless, use shutdown() for more reliable flushing
            # shutdown() flushes all data and waits for background threads to complete
            environment = centralized_metadata["environment"]
            if environment == "prd":
                logger.debug("langfuse_shutdown_starting", environment=environment)
                # shutdown() is more reliable in serverless environments
                # It flushes all data and ensures background threads complete
                langfuse_client.shutdown()
                logger.debug("langfuse_shutdown_completed", environment=environment)
            else:
                # In dev, use flush() as shutdown() might be too aggressive for long-running services
                logger.debug("langfuse_flush_starting", environment=environment)
                langfuse_client.flush()
                logger.debug("langfuse_flush_completed", environment=environment)
        except Exception as e:
            # Log error but don't fail the request
            logger.error(
                "langfuse_flush_failed",
                error=str(e),
                error_type=type(e).__name__,
                environment=centralized_metadata["environment"],
                langfuse_base_url=settings.langfuse_base_url,
            )
    
    return ChatResponse(response=content, user_id=user_id)

