"""
Shared utilities for LangGraph flows.
"""
from __future__ import annotations

import json
import sys
import threading
from typing import Any

import structlog
import httpx
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from google.auth import credentials
from google.oauth2 import service_account

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables.retry import RunnableRetry
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app import constants
from app.config import settings

# Optional import for dev mode only (Ollama)
try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None  # type: ignore

logger = structlog.get_logger(__name__)

ClientError = None
try:
    # Try direct import
    from google.genai.errors import ClientError
except ImportError:
    # Try finding it in sys.modules
    for name, module in sys.modules.items():
        if "google" in name and "genai" in name and "errors" in name:
            if hasattr(module, "ClientError"):
                ClientError = getattr(module, "ClientError")
                logger.info(f"Found ClientError in {name}")
                break

if ClientError is None:
    logger.error("CRITICAL: Could not find ClientError class. Retries will fail.")


OAUTH_SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"


def is_retryable_vertex_error(exception: Exception) -> bool:
    """Return True if the exception looks like a Vertex 429/503 error.
    
    This function checks both exception types and error messages to catch
    Vertex AI rate limiting errors that might be wrapped or have different formats.
    
    Args:
        exception: The exception to check
        
    Returns:
        True if this exception should trigger a retry
    """
    # Check exception types first
    if isinstance(exception, (ResourceExhausted, ServiceUnavailable)):
        return True
    
    # Check for ClientError (newer Google GenAI SDK)
    try:
        if isinstance(exception, ClientError):
            return True
    except (NameError, AttributeError, TypeError):
        # ClientError might not be defined
        pass
    
    # Check for ChatGoogleGenerativeAIError (LangChain wrapper)
    # This wraps ClientError, so we need to check the message
    if isinstance(exception, ChatGoogleGenerativeAIError):
        msg = str(exception)
        if "429" in msg or "Resource exhausted" in msg or "Too Many Requests" in msg:
            return True
    
    # Check error message for 429/Resource exhausted indicators (fallback)
    msg = str(exception)
    return (
        "429" in msg or
        "Resource exhausted" in msg or
        "Too Many Requests" in msg or
        "503" in msg or
        "Service Unavailable" in msg
    )

# Global singletons
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()
_agent_model: BaseChatModel | None = None
_agent_model_lock = threading.Lock()
_tool_model: BaseChatModel | None = None
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


def _wrap_with_retry(runnable: Any) -> Any:
    """Wrap a runnable (model or agent) with retry logic based on provider.
    
    Args:
        runnable: The runnable to wrap (can be a model, bound model, or agent executor)
        
    Returns:
        Runnable wrapped with retry logic
    """
    if settings.LLM_PROVIDER == "ollama":
        # Ollama: retry on connection errors and timeouts
        return RunnableRetry(
            bound=runnable,
            retry_exception_types=(
                ConnectionError,
                ConnectionRefusedError,
                TimeoutError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.HTTPError,  # Catch-all for other httpx errors
            ),
            max_attempt_number=constants.CONSTANTS.get("LLM_RETRY_STOP_AFTER_ATTEMPT", 10),
            wait_exponential_jitter=True,
            exponential_jitter_params={
                "initial": constants.CONSTANTS.get("LLM_RETRY_INITIAL_INTERVAL", 1.0),
                "max": constants.CONSTANTS.get("LLM_RETRY_MAX_INTERVAL", 60),
                "multiplier": 2,
            },
        )
    elif settings.LLM_PROVIDER == "vertex":
        # Vertex AI: retry on 429 errors that slip through internal retries
        # LangChain wraps ClientError into ChatGoogleGenerativeAIError, so we need to catch both
        # Build exception types list with all known Vertex AI error types
        exception_types = [
            ResourceExhausted,
            ServiceUnavailable,
            ChatGoogleGenerativeAIError,  # LangChain wrapper that contains 429 errors
        ]
        
        # Add ClientError if available (the underlying error type)
        if ClientError is not None:
            exception_types.append(ClientError)
        
        # Manually construct RunnableRetry with exception types
        # The custom filter function is_retryable_vertex_error() is available
        # for future use or debugging, but RunnableRetry uses exception types directly
        return RunnableRetry(
            bound=runnable,
            retry_exception_types=tuple(exception_types),
            max_attempt_number=constants.CONSTANTS.get("LLM_RETRY_STOP_AFTER_ATTEMPT", 10),
            wait_exponential_jitter=True,
            exponential_jitter_params={
                "initial": constants.CONSTANTS.get("LLM_RETRY_INITIAL_INTERVAL", 1.0),
                "max": constants.CONSTANTS.get("LLM_RETRY_MAX_INTERVAL", 60),
                "multiplier": 2,
            },
        )
    else:
        # Unknown provider - return unwrapped
        logger.warning(
            "unknown_llm_provider",
            provider=settings.LLM_PROVIDER,
        )
        return runnable


def _create_model(
    model_name: str,
    thinking_level: str | None,
    temperature: float | None,
    log_name: str,
    max_output_tokens: int | None = None,
) -> BaseChatModel:
    """Create a ChatModel instance (Vertex AI or Ollama).
    
    Args:
        model_name: Model name/identifier
        thinking_level: Optional thinking level for Vertex AI models
        temperature: Optional temperature override
        log_name: Name for logging purposes
        max_output_tokens: Optional max output tokens (for Vertex AI) or num_predict (for Ollama)
    """
    model: BaseChatModel
    
    # Switch provider based on settings
    if settings.LLM_PROVIDER == "ollama":
        if ChatOllama is None:
            raise ImportError(
                "langchain-ollama is required for Ollama provider. "
                "Install it with: uv add --dev langchain-ollama"
            )
        if not settings.OLLAMA_BASE_URL:
            raise ValueError("OLLAMA_BASE_URL is required when LLM_PROVIDER is 'ollama'")
        
        chat_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature if temperature is not None else 0.0,
            "base_url": settings.OLLAMA_BASE_URL,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,  # Configurable: "0" unloads immediately, "5m" keeps for 5 minutes, etc.
        }
        
        # Only set num_ctx if configured (optional parameter)
        if settings.OLLAMA_NUM_CTX is not None:
            chat_kwargs["num_ctx"] = settings.OLLAMA_NUM_CTX
        
        # Only set num_predict if max_output_tokens is provided (otherwise use ChatOllama default)
        if max_output_tokens is not None:
            chat_kwargs["num_predict"] = max_output_tokens
        
        model = ChatOllama(**chat_kwargs)
        
        log_data = {
            "model": model_name,
            "url": settings.OLLAMA_BASE_URL,
        }
        if settings.OLLAMA_NUM_CTX is not None:
            log_data["num_ctx"] = settings.OLLAMA_NUM_CTX
        if max_output_tokens is not None:
            log_data["num_predict"] = max_output_tokens
        
        logger.info(f"{log_name}_initialized_ollama", **log_data)
    elif settings.LLM_PROVIDER == "vertex":
        # Vertex AI Logic
        creds, project_id = _get_vertex_credentials()
        
        model_kwargs: dict[str, Any] = {"provider": "vertexai"}
        if thinking_level is not None:
            model_kwargs["thinking_level"] = thinking_level
        
        # temperature and max_output_tokens should be passed directly to ChatGoogleGenerativeAI, not in model_kwargs
        model_kwargs_for_constructor: dict[str, Any] = {
            "model": model_name,
            "model_kwargs": model_kwargs,
            "project": project_id,
            "location": settings.VERTEX_AI_LOCATION,
            "credentials": creds,
            "max_retries": constants.CONSTANTS.get("VERTEX_AI_MAX_RETRIES", 6),
        }
        
        # Add temperature as a direct parameter if provided
        if temperature is not None:
            model_kwargs_for_constructor["temperature"] = temperature
        
        # Add max_output_tokens as a direct parameter if provided (for long reports)
        if max_output_tokens is not None:
            model_kwargs_for_constructor["max_output_tokens"] = max_output_tokens
        
        model = ChatGoogleGenerativeAI(**model_kwargs_for_constructor)
        
        log_data = {
            "model": model_name,
            "max_retries": constants.CONSTANTS.get("VERTEX_AI_MAX_RETRIES", 6),
        }
        if thinking_level is not None:
            log_data["thinking_level"] = thinking_level
        elif temperature is not None:
            log_data["temperature"] = temperature
        if max_output_tokens is not None:
            log_data["max_output_tokens"] = max_output_tokens
        
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
    max_output_tokens: int | None = None,
) -> BaseChatModel:
    """
    Get or create cached model for agent (shared across flows).
    
    Args:
        thinking_level: Optional override. If None, uses LLM_THINKING_LEVEL from constants.
        temperature: Optional override. If None, uses LLM_TEMPERATURE from constants.
            Only used if thinking_level is not set.
        max_output_tokens: Optional max output tokens. If provided, creates a new model instance
            instead of using the cached one (for cases like editor node that need higher limits).
    """
    # If max_output_tokens is specified, create a new model instance (don't use cache)
    # This allows editor node to use higher output limits without affecting other flows
    if max_output_tokens is not None:
        final_thinking_level = thinking_level or constants.CONSTANTS.get("LLM_THINKING_LEVEL")
        final_temperature = temperature or constants.CONSTANTS.get("LLM_TEMPERATURE")
        return _create_model(
            model_name=settings.LLM_MODEL_NAME,
            thinking_level=final_thinking_level,
            temperature=final_temperature,
            log_name="agent_model",
            max_output_tokens=max_output_tokens,
        )
    
    # Use cached model for normal cases
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
) -> BaseChatModel:
    """
    Get or create cached model for tool operations.
    
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

