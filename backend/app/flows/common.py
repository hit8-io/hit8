"""
Shared utilities for LangGraph flows.
"""
from __future__ import annotations

import json
import threading
from typing import Any

import structlog
from google.auth import credentials
from google.oauth2 import service_account
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app import constants
from app.config import settings

logger = structlog.get_logger(__name__)

OAUTH_SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"

# Global singletons
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()
_agent_model: ChatGoogleGenerativeAI | None = None
_agent_model_lock = threading.Lock()
_tool_model: ChatGoogleGenerativeAI | None = None
_tool_model_lock = threading.Lock()
_credentials: credentials.Credentials | None = None
_project_id: str | None = None
_credentials_lock = threading.Lock()


def _get_vertex_credentials() -> tuple[credentials.Credentials, str]:
    """Get or create Vertex AI credentials and project ID (cached)."""
    global _credentials, _project_id
    if _credentials is None or _project_id is None:
        with _credentials_lock:
            if _credentials is None or _project_id is None:
                service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                _project_id = service_account_info["project_id"]
                _credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=[OAUTH_SCOPE_CLOUD_PLATFORM],
                )
    return _credentials, _project_id


def _create_model(
    model_name: str,
    thinking_level: str | None,
    temperature: float | None,
    log_name: str,
) -> ChatGoogleGenerativeAI:
    """Create a ChatGoogleGenerativeAI model instance."""
    creds, project_id = _get_vertex_credentials()
    
    model_kwargs: dict[str, Any] = {"provider": "vertexai"}
    if thinking_level is not None:
        model_kwargs["thinking_level"] = thinking_level
    elif temperature is not None:
        model_kwargs["temperature"] = temperature
    
    model = ChatGoogleGenerativeAI(
        model=model_name,
        model_kwargs=model_kwargs,
        project=project_id,
        location=settings.VERTEX_AI_LOCATION,
        credentials=creds,
    )
    
    log_data = {"model": model_name}
    if thinking_level is not None:
        log_data["thinking_level"] = thinking_level
    elif temperature is not None:
        log_data["temperature"] = temperature
    
    logger.info(f"{log_name}_initialized", **log_data)
    return model


def get_langfuse_client() -> Langfuse | None:
    """Get or create Langfuse client (lazy initialization, shared across flows)."""
    global _langfuse_client
    if not settings.LANGFUSE_ENABLED:
        return None
    
    if _langfuse_client is None:
        with _langfuse_lock:
            if _langfuse_client is None:
                # Langfuse client initialization
                # Pass base_url explicitly to ensure OTEL exporter uses correct endpoint
                import os
                langfuse_base_url = os.getenv("LANGFUSE_BASE_URL")
                _langfuse_client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    base_url=langfuse_base_url,
                )
                logger.info(
                    "langfuse_client_initialized",
                    env=settings.environment,
                )
    return _langfuse_client


def get_langfuse_handler() -> CallbackHandler | None:
    """Get Langfuse callback handler if enabled, None otherwise."""
    if not settings.LANGFUSE_ENABLED:
        return None
    get_langfuse_client()  # Ensure client is initialized
    handler = CallbackHandler()
    return handler


def get_agent_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
) -> ChatGoogleGenerativeAI:
    """
    Get or create cached Vertex AI model for agent (shared across flows).
    
    Args:
        thinking_level: Optional override. If None, uses LLM_THINKING_LEVEL from constants.
        temperature: Optional override. If None, uses LLM_TEMPERATURE from constants.
            Only used if thinking_level is not set.
    """
    global _agent_model
    if _agent_model is None:
        with _agent_model_lock:
            if _agent_model is None:
                final_thinking_level = thinking_level or constants.CONSTANTS.get("LLM_THINKING_LEVEL")
                final_temperature = temperature or constants.CONSTANTS.get("LLM_TEMPERATURE")
                _agent_model = _create_model(
                    model_name=settings.LLM_MODEL_NAME,
                    thinking_level=final_thinking_level,
                    temperature=final_temperature,
                    log_name="agent_model",
                )
    return _agent_model


def get_tool_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
) -> ChatGoogleGenerativeAI:
    """
    Get or create cached Vertex AI model for tool operations.
    
    Args:
        thinking_level: Optional override. If None, uses TOOL_LLM_THINKING_LEVEL from constants.
        temperature: Optional override. If None, uses TOOL_LLM_TEMPERATURE from constants.
            Only used if thinking_level is not set.
    """
    global _tool_model
    if _tool_model is None:
        with _tool_model_lock:
            if _tool_model is None:
                model_name = constants.CONSTANTS.get("TOOL_LLM_MODEL") or settings.LLM_MODEL_NAME
                final_thinking_level = thinking_level or constants.CONSTANTS.get("TOOL_LLM_THINKING_LEVEL")
                final_temperature = temperature or constants.CONSTANTS.get("TOOL_LLM_TEMPERATURE")
                _tool_model = _create_model(
                    model_name=model_name,
                    thinking_level=final_thinking_level,
                    temperature=final_temperature,
                    log_name="tool_model",
                )
    return _tool_model

