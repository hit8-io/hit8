"""
Shared utilities for LangGraph agents.
"""
from __future__ import annotations

import json
import threading

import structlog
from google.oauth2 import service_account
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config import settings

logger = structlog.get_logger(__name__)

# Agent model configuration constants
AGENT_MODEL_PROVIDER = "vertexai"
AGENT_THINKING_LEVEL = "medium"  # Can be configured via settings if needed
OAUTH_SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"

# Global Langfuse client (shared across agents)
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()


def get_langfuse_client() -> Langfuse | None:
    """Get or create Langfuse client (lazy initialization, shared across agents).
    
    Returns:
        Langfuse client instance or None if disabled
    """
    global _langfuse_client
    if not settings.langfuse_enabled:
        return None
    
    if _langfuse_client is None:
        with _langfuse_lock:
            if _langfuse_client is None:
                _langfuse_client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_base_url,
                )
                logger.info(
                    "langfuse_client_initialized",
                    env=settings.environment,
                    base_url=settings.langfuse_base_url,
                )
    
    return _langfuse_client


def get_langfuse_handler() -> CallbackHandler | None:
    """Get Langfuse callback handler if enabled, None otherwise.
    
    Returns:
        CallbackHandler instance or None if disabled
    """
    if not settings.langfuse_enabled:
        return None
    
    # Ensure Langfuse client is initialized before creating handler
    get_langfuse_client()
    
    # CallbackHandler uses the singleton client (now lazily initialized)
    handler = CallbackHandler()
    logger.debug("langfuse_callback_handler_created")
    return handler


# Cache agent model at module level (shared across agents)
_agent_model: ChatGoogleGenerativeAI | None = None
_agent_model_lock = threading.Lock()


def get_agent_model(
    thinking_level: str | None = None,
) -> ChatGoogleGenerativeAI:
    """
    Get or create cached Vertex AI model for agent (shared across agents).
    
    Args:
        thinking_level: Optional thinking level override. If None, uses AGENT_THINKING_LEVEL.
    
    Returns:
        ChatGoogleGenerativeAI model instance
    """
    global _agent_model
    
    if _agent_model is None:
        with _agent_model_lock:
            if _agent_model is None:
                service_account_info = json.loads(settings.vertex_service_account)
                project_id = service_account_info["project_id"]
                
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=[OAUTH_SCOPE_CLOUD_PLATFORM]
                )
                
                model_kwargs = {
                    "provider": AGENT_MODEL_PROVIDER,
                    "thinking_level": thinking_level or AGENT_THINKING_LEVEL,
                }
                
                _agent_model = ChatGoogleGenerativeAI(
                    model=settings.vertex_ai_model_name,
                    model_kwargs=model_kwargs,
                    project=project_id,
                    location=settings.vertex_ai_location,
                    credentials=creds,
                )
                logger.info(
                    "agent_model_initialized",
                    model=settings.vertex_ai_model_name,
                    thinking_level=thinking_level or AGENT_THINKING_LEVEL,
                )
    
    return _agent_model

