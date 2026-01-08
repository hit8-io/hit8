"""
Shared utilities for LangGraph flows.
"""
from __future__ import annotations

import json
import threading
from typing import Any

import structlog
from google.oauth2 import service_account
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app import constants
from app.config import settings

logger = structlog.get_logger(__name__)

# Agent model configuration constants
AGENT_MODEL_PROVIDER = "vertexai"
OAUTH_SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"

# Global Langfuse client (shared across flows)
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()


def get_langfuse_client() -> Langfuse | None:
    """Get or create Langfuse client (lazy initialization, shared across flows).
    
    Returns:
        Langfuse client instance or None if disabled
    """
    global _langfuse_client
    if not settings.LANGFUSE_ENABLED:
        return None
    
    if _langfuse_client is None:
        with _langfuse_lock:
            if _langfuse_client is None:
                _langfuse_client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_BASE_URL,
                )
                logger.info(
                    "langfuse_client_initialized",
                    env=settings.environment,
                    base_url=settings.LANGFUSE_BASE_URL,
                )
    
    return _langfuse_client


def get_langfuse_handler() -> CallbackHandler | None:
    """Get Langfuse callback handler if enabled, None otherwise.
    
    Returns:
        CallbackHandler instance or None if disabled
    """
    if not settings.LANGFUSE_ENABLED:
        return None
    
    # Ensure Langfuse client is initialized before creating handler
    get_langfuse_client()
    
    # CallbackHandler uses the singleton client (now lazily initialized)
    handler = CallbackHandler()
    logger.debug("langfuse_callback_handler_created")
    return handler


# Cache agent model at module level (shared across flows)
_agent_model: ChatGoogleGenerativeAI | None = None
_agent_model_lock = threading.Lock()


def get_agent_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
) -> ChatGoogleGenerativeAI:
    """
    Get or create cached Vertex AI model for agent (shared across flows).
    
    Args:
        thinking_level: Optional thinking level override. If None, uses LLM_THINKING_LEVEL from constants.
            If set, thinking_level is used. Otherwise, temperature is used if set.
        temperature: Optional temperature override. If None, uses LLM_TEMPERATURE from constants.
            Only used if thinking_level is not set.
    
    Returns:
        ChatGoogleGenerativeAI model instance
    """
    global _agent_model
    
    if _agent_model is None:
        with _agent_model_lock:
            if _agent_model is None:
                service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                project_id = service_account_info["project_id"]
                
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=[OAUTH_SCOPE_CLOUD_PLATFORM]
                )
                
                model_kwargs: dict[str, Any] = {
                    "provider": AGENT_MODEL_PROVIDER,
                }
                
                model_name = settings.LLM_MODEL_NAME
                
                # Use thinking_level if set, otherwise use temperature if set
                final_thinking_level = thinking_level or constants.CONSTANTS.get("LLM_THINKING_LEVEL")
                final_temperature = temperature or constants.CONSTANTS.get("LLM_TEMPERATURE")
                
                if final_thinking_level is not None:
                    model_kwargs["thinking_level"] = final_thinking_level
                elif final_temperature is not None:
                    model_kwargs["temperature"] = final_temperature
                
                _agent_model = ChatGoogleGenerativeAI(
                    model=model_name,
                    model_kwargs=model_kwargs,
                    project=project_id,
                    location=settings.VERTEX_AI_LOCATION,
                    credentials=creds,
                )
                
                log_data = {
                    "model": model_name,
                }
                if final_thinking_level is not None:
                    log_data["thinking_level"] = final_thinking_level
                elif final_temperature is not None:
                    log_data["temperature"] = final_temperature
                
                logger.info("agent_model_initialized", **log_data)
    
    return _agent_model


# Cache entity extraction model at module level
_entity_extraction_model: ChatGoogleGenerativeAI | None = None
_entity_extraction_model_lock = threading.Lock()


def get_entity_extraction_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
) -> ChatGoogleGenerativeAI:
    """
    Get or create cached Vertex AI model for entity extraction.
    
    Args:
        thinking_level: Optional thinking level override. If set, thinking_level is used. Otherwise, temperature is used if set.
        temperature: Optional temperature override. Only used if thinking_level is not set.
    
    Returns:
        ChatGoogleGenerativeAI model instance configured for entity extraction
    """
    global _entity_extraction_model
    
    if _entity_extraction_model is None:
        with _entity_extraction_model_lock:
            if _entity_extraction_model is None:
                service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                project_id = service_account_info["project_id"]
                
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=[OAUTH_SCOPE_CLOUD_PLATFORM]
                )
                
                model_kwargs: dict[str, Any] = {
                    "provider": AGENT_MODEL_PROVIDER,
                }
                
                model_name = settings.LLM_MODEL_NAME
                
                # Use thinking_level if set, otherwise use temperature if set
                if thinking_level is not None:
                    model_kwargs["thinking_level"] = thinking_level
                elif temperature is not None:
                    model_kwargs["temperature"] = temperature
                
                _entity_extraction_model = ChatGoogleGenerativeAI(
                    model=model_name,
                    model_kwargs=model_kwargs,
                    project=project_id,
                    location=settings.VERTEX_AI_LOCATION,
                    credentials=creds,
                )
                
                log_data = {
                    "model": model_name,
                }
                if thinking_level is not None:
                    log_data["thinking_level"] = thinking_level
                elif temperature is not None:
                    log_data["temperature"] = temperature
                
                logger.info("entity_extraction_model_initialized", **log_data)
    
    return _entity_extraction_model

