"""
Shared utilities for LangGraph flows.
"""
from __future__ import annotations

import asyncio
import json
import random
import threading
import time
from typing import Any, Callable, Coroutine

import structlog
import httpx
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from litellm.exceptions import RateLimitError

from langchain_litellm import ChatLiteLLM
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from tenacity import (
    retry,
    wait_random_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)
import tiktoken

from app import constants
from app.config import settings
from app.llm_router import router
from app.constants import (
    ANALYST_SEMAPHORE,
    ANALYST_TIMEOUT_SECONDS,
    ANALYST_MAX_RETRIES,
)

logger = structlog.get_logger(__name__)


# Application-level rate limiter for Pro models (strict 5 RPM = 12 seconds between requests)
# LiteLLM Router's in-memory rate limiting isn't reliable for strict limits
_pro_model_rate_limiter: dict[str, float] = {}  # model_name -> last_request_timestamp
_pro_model_rate_limiter_lock: asyncio.Lock | None = None
_pro_model_rate_limiter_lock_sync = threading.Lock()
_PRO_MODEL_MIN_INTERVAL_SECONDS = 12.0  # 5 RPM = 60/5 = 12 seconds minimum between requests


def _get_pro_model_rate_limiter_lock() -> asyncio.Lock:
    """Get or create the async lock for Pro model rate limiting. Lazy-initialized."""
    global _pro_model_rate_limiter_lock
    if _pro_model_rate_limiter_lock is None:
        with _pro_model_rate_limiter_lock_sync:
            if _pro_model_rate_limiter_lock is None:
                _pro_model_rate_limiter_lock = asyncio.Lock()
    return _pro_model_rate_limiter_lock


async def _wait_for_pro_model_rate_limit(model_name: str | None) -> None:
    """Wait if needed to enforce 5 RPM limit for Pro models.
    
    Pro models (gemini-2.5-pro, gemini-3-pro-preview) have a strict 5 RPM limit.
    This function ensures at least 12 seconds between requests for these models.
    
    Args:
        model_name: Model name to check (e.g., "gemini-2.5-pro")
    """
    if not model_name:
        return
    
    # Only apply to Pro models
    if "gemini-2.5-pro" not in model_name and "gemini-3-pro-preview" not in model_name:
        return
    
    lock = _get_pro_model_rate_limiter_lock()
    async with lock:
        last_request_time = _pro_model_rate_limiter.get(model_name, 0.0)
        current_time = time.time()
        time_since_last = current_time - last_request_time
        
        if time_since_last < _PRO_MODEL_MIN_INTERVAL_SECONDS:
            wait_time = _PRO_MODEL_MIN_INTERVAL_SECONDS - time_since_last
            logger.debug(
                "pro_model_rate_limit_wait",
                model_name=model_name,
                wait_time_seconds=wait_time,
                time_since_last_request=time_since_last,
            )
            await asyncio.sleep(wait_time)
        
        # Update last request time
        _pro_model_rate_limiter[model_name] = time.time()


def _count_tokens_from_messages(messages: list[BaseMessage] | list[dict[str, Any]] | Any, model_name: str | None = None) -> int | None:
    """Count input tokens from messages.
    
    Uses tiktoken to count tokens. For Vertex AI models, uses cl100k_base encoding
    (same as GPT-4).
    
    Args:
        messages: List of messages (BaseMessage objects or dicts) or single message
        model_name: Optional model name to determine encoding (defaults to cl100k_base)
        
    Returns:
        Number of input tokens, or None if counting failed
    """
    try:
        # Use cl100k_base encoding (GPT-4/Vertex AI compatible)
        # For most Vertex AI models, this is a reasonable approximation
        encoding = tiktoken.get_encoding("cl100k_base")
        
        total_tokens = 0
        
        # Handle different message formats
        if not isinstance(messages, list):
            messages = [messages]
        
        for msg in messages:
            # Extract content from message
            content = ""
            if isinstance(msg, dict):
                content = str(msg.get('content', ''))
            elif hasattr(msg, 'content'):
                content = str(msg.content)
            else:
                content = str(msg)
            
            # Count tokens in content
            if content:
                content_tokens = len(encoding.encode(content))
                total_tokens += content_tokens
            else:
                # If no content, log a warning (this shouldn't happen normally)
                logger.debug(
                    "token_counting_empty_content",
                    message_type=type(msg).__name__,
                )
            
            # Add overhead for message formatting (role, etc.)
            # Rough estimate: ~4 tokens per message for formatting
            # Note: This is a minimal overhead estimate
            total_tokens += 4
        
        return total_tokens
    except Exception as e:
        logger.debug(
            "token_counting_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def _extract_messages_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[BaseMessage] | list[dict[str, Any]] | Any | None:
    """Extract messages from coroutine arguments.
    
    Messages are typically the first positional argument or in 'messages' keyword.
    
    Args:
        args: Positional arguments passed to coroutine
        kwargs: Keyword arguments passed to coroutine
        
    Returns:
        Messages if found, None otherwise
    """
    # Try keyword argument first
    if 'messages' in kwargs:
        return kwargs['messages']
    
    # Try first positional argument (most common pattern: model.ainvoke(messages, config=...))
    if args and len(args) > 0:
        first_arg = args[0]
        # Check if it looks like messages (list of BaseMessage or dicts)
        if isinstance(first_arg, list):
            return first_arg
        # Could be a single message
        if hasattr(first_arg, 'content') or isinstance(first_arg, dict):
            return [first_arg]
    
    return None


# Global singletons
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()
_llm_cache: dict[tuple[Any, ...], BaseChatModel] = {}
_llm_cache_lock = threading.Lock()
_report_llm_semaphore: asyncio.Semaphore | None = None
_report_llm_semaphore_lock = threading.Lock()
_consult_llm_semaphore: asyncio.Semaphore | None = None
_consult_llm_semaphore_lock = threading.Lock()


def get_report_llm_semaphore() -> asyncio.Semaphore:
    """Return a semaphore that limits concurrent report LLM calls (analyst + editor). Lazy-initialized."""
    global _report_llm_semaphore
    if _report_llm_semaphore is None:
        with _report_llm_semaphore_lock:
            if _report_llm_semaphore is None:
                n = constants.CONSTANTS.get("REPORT_LLM_CONCURRENCY", 2)
                _report_llm_semaphore = asyncio.Semaphore(max(n, 1))
    return _report_llm_semaphore


def get_consult_llm_semaphore() -> asyncio.Semaphore:
    """Return a semaphore that limits concurrent consult_general_knowledge (nested chat graph) invocations. Lazy-initialized."""
    global _consult_llm_semaphore
    if _consult_llm_semaphore is None:
        with _consult_llm_semaphore_lock:
            if _consult_llm_semaphore is None:
                n = constants.CONSTANTS.get("REPORT_CONSULT_LLM_CONCURRENCY", 1)
                _consult_llm_semaphore = asyncio.Semaphore(max(n, 1))
    return _consult_llm_semaphore




def _gather_error_context(
    exception: Exception | None,
    semaphore: asyncio.Semaphore | None,
    call_context: dict[str, Any],
) -> dict[str, Any]:
    """Gather comprehensive error context for detailed logging."""
    context = dict(call_context)
    
    # Extract error information
    if exception:
        error_msg = str(exception)
        context["error_message"] = error_msg
        context["error_type"] = type(exception).__name__
        context["error_repr"] = repr(exception)
        
        # Extract status code
        status_code = None
        if hasattr(exception, 'status_code'):
            status_code = exception.status_code
        elif hasattr(exception, 'status'):
            status_code = getattr(exception, 'status', None)
        context["status_code"] = status_code
        
        # Extract details from ResourceExhausted
        if isinstance(exception, ResourceExhausted):
            if hasattr(exception, 'message'):
                context["resource_exhausted_message"] = str(exception.message)
            if hasattr(exception, 'details'):
                context["resource_exhausted_details"] = str(exception.details)
    
    # Add semaphore state
    if semaphore is not None:
        try:
            context["semaphore_available"] = semaphore._value if hasattr(semaphore, '_value') else None
        except Exception:
            pass  # Don't fail if we can't get semaphore state
    
    return context


async def execute_llm_call_async(
    coro: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    semaphore: asyncio.Semaphore | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    retry_exception_types: tuple[type[Exception], ...] | None = None,
    call_context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """
    Simplified async wrapper for LLM calls.
    
    LiteLLM Router handles:
    - Token quota (TPM)
    - Rate limiting (RPM)
    - Automatic retries (5xx errors)
    - Cooldown on failures
    
    This wrapper only handles:
    - Semaphore (concurrency control)
    - Timeout (prevent stalling)
    - Network-level retries (optional, LiteLLM handles most)
    
    Args:
        coro: Async callable (coroutine function) to execute
        *args: Positional arguments to pass to coro
        semaphore: Optional semaphore for concurrency control (default: ANALYST_SEMAPHORE)
        timeout_seconds: Optional timeout in seconds (default: 600.0 = 10 minutes)
        max_retries: Optional max retry attempts (default: ANALYST_MAX_RETRIES, but LiteLLM handles most)
        retry_exception_types: Optional tuple of exception types to retry (default: ResourceExhausted, ServiceUnavailable)
        call_context: Optional dict with context for logging (e.g., {"file_id": "...", "node": "..."})
        **kwargs: Keyword arguments to pass to coro
        
    Returns:
        Result from coro execution
        
    Raises:
        asyncio.TimeoutError: If execution exceeds timeout
        Exception: If all retries are exhausted or non-retryable exception occurs
    """
    # Use defaults from constants if not provided
    if semaphore is None:
        semaphore = ANALYST_SEMAPHORE
    
    call_context = call_context or {}
    
    # Calculate dynamic timeout based on input tokens if available
    # If timeout_seconds is None, calculate based on input tokens
    if timeout_seconds is None:
        input_tokens = call_context.get("input_tokens")
        if input_tokens and input_tokens > 0:
            # Dynamic timeout calculation (realistic estimates based on Gemini performance):
            # - Base timeout: 60 seconds (1 minute) for small requests
            # - Input processing: ~0.002 seconds per token (2ms per token - realistic for Gemini)
            # - Output generation: ~0.015 seconds per expected output token (15ms per token - realistic for Gemini)
            #   (estimate 20% of input tokens as output)
            # - Buffer: 60 seconds (1 minute) for network/processing overhead
            # - Rate limiter wait: 12 seconds (for Pro models)
            # - Safety margin: 2x multiplier for retries and variability
            
            estimated_output_tokens = int(input_tokens * 0.2)  # Estimate 20% output
            input_processing_time = input_tokens * 0.002  # ~2ms per input token (realistic)
            output_generation_time = estimated_output_tokens * 0.015  # ~15ms per output token (realistic)
            base_timeout = 60.0  # Base 1 minute
            buffer = 60.0  # 1 minute buffer
            rate_limiter_buffer = 12.0  # Rate limiter wait time
            
            # Calculate base timeout
            calculated_timeout = base_timeout + input_processing_time + output_generation_time + buffer + rate_limiter_buffer
            
            # Apply 2x safety margin for retries and variability
            calculated_timeout = calculated_timeout * 2.0
            
            # Cap at 30 minutes (1800s) - realistic max for even very large requests
            # Minimum 2 minutes (120s) for very small inputs
            timeout_seconds = max(120.0, min(calculated_timeout, 1800.0))
            
            logger.debug(
                "dynamic_timeout_calculated",
                input_tokens=input_tokens,
                estimated_output_tokens=estimated_output_tokens,
                calculated_timeout=calculated_timeout,
                final_timeout=timeout_seconds,
                **{k: v for k, v in call_context.items() if k != "input_tokens"},
            )
        else:
            # Default timeout: 10 minutes (600s) if no token info available
            timeout_seconds = 600.0
    
    # Default retry configuration (LiteLLM handles most retries, this is for network errors)
    if max_retries is None:
        max_retries = ANALYST_MAX_RETRIES
    
    if retry_exception_types is None:
        # Include RateLimitError from LiteLLM for proper retry handling
        retry_exception_types = (ResourceExhausted, ServiceUnavailable, RateLimitError)
    
    # Simple retry wrapper for network-level errors (LiteLLM handles API-level retries)
    async def _before_retry_sleep(retry_state):
        """Handle retry sleep with logging."""
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if exception:
            _log_retry_attempt(retry_state, call_context)
    
    @retry(
        wait=wait_random_exponential(multiplier=2, max=120),
        stop=stop_after_attempt(max_retries),
        retry=retry_if_exception_type(retry_exception_types),
        reraise=True,
        before_sleep=_before_retry_sleep,
        after=lambda retry_state: _log_retry_success(retry_state, call_context),
    )
    async def _execute():
        """Execute coro. LiteLLM Router handles rate limiting and retries."""
        logger.debug(
            "llm_call_executing",
            **call_context,
        )
        result = await coro(*args, **kwargs)
        logger.debug(
            "llm_call_completed",
            **call_context,
        )
        return result
    
    # Semaphore (concurrency control)
    sem_wait_start = time.time()
    
    # Log semaphore state before acquisition
    semaphore_info = {}
    if hasattr(semaphore, '_value'):
        semaphore_info["available_slots"] = semaphore._value
    if hasattr(semaphore, '_waiters') and semaphore._waiters is not None:
        semaphore_info["waiting_count"] = len(semaphore._waiters)
    if hasattr(semaphore, '_initial_value'):
        semaphore_info["total_slots"] = semaphore._initial_value
    
    logger.debug(
        "llm_semaphore_acquiring",
        semaphore_info=semaphore_info,
        **call_context,
    )
    
    async with semaphore:
        sem_wait_time = time.time() - sem_wait_start
        if sem_wait_time > 0.1:  # Only log if we actually waited
            updated_info = {}
            if hasattr(semaphore, '_value'):
                updated_info["available_slots_after"] = semaphore._value
            if hasattr(semaphore, '_waiters') and semaphore._waiters is not None:
                updated_info["waiting_count_after"] = len(semaphore._waiters)
            
            logger.warning(
                "llm_semaphore_waiting",
                wait_time_seconds=sem_wait_time,
                semaphore_info_before=semaphore_info,
                semaphore_info_after=updated_info,
                **call_context,
            )
        else:
            updated_info = {}
            if hasattr(semaphore, '_value'):
                updated_info["available_slots_after"] = semaphore._value
            if hasattr(semaphore, '_waiters') and semaphore._waiters is not None:
                updated_info["waiting_count_after"] = len(semaphore._waiters)
            
            logger.debug(
                "llm_semaphore_acquired",
                semaphore_info_before=semaphore_info,
                semaphore_info_after=updated_info,
                **call_context,
            )
        
        # Enforce Pro model rate limit (5 RPM = 12 seconds between requests)
        # This is in addition to LiteLLM Router's rate limiting
        model_name = call_context.get("model_name") or call_context.get("parent_model")
        await _wait_for_pro_model_rate_limit(model_name)
        
        # Execute with timeout and optional retry
        try:
            return await asyncio.wait_for(
                _execute(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            error_details = _gather_error_context(
                exception=None,
                semaphore=semaphore,
                call_context=call_context,
            )
            error_details["timeout_seconds"] = timeout_seconds
            
            logger.error(
                "llm_call_timeout",
                **error_details,
            )
            raise
        except retry_exception_types as e:
            error_details = _gather_error_context(
                exception=e,
                semaphore=semaphore,
                call_context=call_context,
            )
            
            is_rate_limit = (
                error_details.get("status_code") == 429 or
                "429" in error_details.get("error_message", "") or
                "rate limit" in error_details.get("error_message", "").lower() or
                "resource exhausted" in error_details.get("error_message", "").lower() or
                isinstance(e, ResourceExhausted)
            )
            
            if is_rate_limit:
                logger.error(
                    "llm_rate_limit_error_detected",
                    **error_details,
                )
            else:
                logger.error(
                    "llm_call_error",
                    **error_details,
                )
            raise


def _log_retry_attempt(retry_state, call_context: dict[str, Any]):
    """Log retry attempt with extensive details.
    
    This logs INTERNAL retries (handled by tenacity within execute_llm_call_async).
    Graph-level retries are logged separately in batch_processor_node.
    """
    attempt = retry_state.attempt_number
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    wait_time = retry_state.next_action.sleep if hasattr(retry_state, 'next_action') else None
    
    error_msg = str(exception) if exception else "Unknown error"
    status_code = None
    if exception and hasattr(exception, 'status_code'):
        status_code = exception.status_code
    elif exception and hasattr(exception, 'status'):
        status_code = getattr(exception, 'status', None)
    
    is_rate_limit = (
        status_code == 429 or
        "429" in error_msg or
        "rate limit" in error_msg.lower() or
        "resource exhausted" in error_msg.lower() or
        isinstance(exception, ResourceExhausted) if exception else False
    )
    
    # input_tokens is already in call_context, so we don't need to pass it separately
    if is_rate_limit:
        logger.warning(
            "llm_rate_limit_retry_internal",
            retry_type="internal",  # Internal retry (tenacity)
            retry_attempt=attempt,
            max_retries=retry_state.retry_object.stop.max_attempt_number if hasattr(retry_state.retry_object, 'stop') else None,
            wait_time_seconds=wait_time,
            error_message=error_msg,
            error_type=type(exception).__name__ if exception else "Unknown",
            **call_context,
        )
    else:
        logger.warning(
            "llm_call_retry_internal",
            retry_type="internal",  # Internal retry (tenacity)
            retry_attempt=attempt,
            wait_time_seconds=wait_time,
            error_message=error_msg,
            error_type=type(exception).__name__ if exception else "Unknown",
            **call_context,
        )


def _log_retry_success(retry_state, call_context: dict[str, Any]):
    """Log successful completion after internal retries.
    
    This logs success after INTERNAL retries (handled by tenacity).
    Graph-level retry success is logged separately in batch_processor_node.
    """
    if retry_state.attempt_number > 1:
        logger.info(
            "llm_call_retry_success_internal",
            retry_type="internal",  # Internal retry (tenacity)
            total_attempts=retry_state.attempt_number,
            **call_context,
        )


def get_provider_for_model(model_name: str | None = None) -> str:
    """Get provider name for a given model name.
    
    Args:
        model_name: Optional model name. If None, uses first available model.
        
    Returns:
        Provider name ("vertex" or "ollama")
    """
    try:
        llm_config = _get_first_available_llm_config(model_name=model_name)
        return llm_config.get("PROVIDER", "vertex")
    except Exception:
        return "vertex"  # Default to vertex on error


def _get_first_available_llm_config(model_name: str | None = None) -> dict[str, Any]:
    """Get LLM configuration from LLM list.
    
    Args:
        model_name: Optional model name to find. If provided, returns matching config.
                   If None, returns the first available config.
    
    Returns:
        Dictionary with MODEL_NAME, PROVIDER, LOCATION, THINKING_LEVEL, TEMPERATURE
        
    Raises:
        ValueError: If no configs found or if model_name specified but not found
    """
    llm_configs = settings.LLM
    if not llm_configs:
        raise ValueError("LLM must contain at least one configuration")
    
    # If model_name is specified, find matching config
    if model_name:
        for config in llm_configs:
            config_dict = config.model_dump() if hasattr(config, 'model_dump') else dict(config) if isinstance(config, dict) else config
            if config_dict.get("MODEL_NAME") == model_name:
                return config_dict
        # Model not found - raise error
        raise ValueError(f"Model '{model_name}' not found in LLM configuration")
    
    # Get first config - it's already a Pydantic model, convert to dict
    first_config = llm_configs[0]
    if hasattr(first_config, 'model_dump'):
        return first_config.model_dump()
    # If it's already a dict (shouldn't happen with Pydantic, but handle it)
    return dict(first_config) if isinstance(first_config, dict) else first_config


def _get_provider_config(provider: str) -> dict[str, Any]:
    """Get provider-specific configuration from LLM_PROVIDER list.
    
    Args:
        provider: Provider name ("vertex" or "ollama")
        
    Returns:
        Dictionary with provider-specific settings, or empty dict if not found
    """
    provider_configs = settings.LLM_PROVIDER
    for config in provider_configs:
        config_dict = config.model_dump() if hasattr(config, 'model_dump') else config
        if config_dict.get("PROVIDER") == provider:
            return config_dict
    # Return empty dict if provider not found (will use defaults/legacy fields)
    return {}


def _create_model(
    model_name: str,
    provider: str,
    location: str | None,
    thinking_level: str | None,
    temperature: float | None,
    log_name: str,
    max_output_tokens: int | None = None,
) -> BaseChatModel:
    """Create a ChatModel instance using LiteLLM Router.
    
    Args:
        model_name: Model name/identifier (must match router model_name)
        provider: LLM provider ("vertex" or "ollama") - kept for compatibility, not used
        location: Location/region - kept for compatibility, not used (router handles it)
        thinking_level: Optional thinking level - kept for compatibility, not used
        temperature: Optional temperature override
        log_name: Name for logging purposes
        max_output_tokens: Optional max output tokens
    """
    # Map model names to LiteLLM router model names
    # Router uses model_name from model_list configuration
    router_model_name = model_name
    
    # Handle thinking models (Gemini 3.0) - set temperature to None
    if "gemini-3" in model_name or "preview" in model_name:
        temperature = None
    
    # Build model_kwargs
    model_kwargs: dict[str, Any] = {
        "user": "hit8-analyst",  # Tag for logging
        # Opt-in caching: do not cache by default (avoids writing huge tool-call payloads
        # e.g. thought_signatures from gemini-2.5-pro to Redis, which can timeout).
        "cache": {"no-store": True},
    }
    
    # Add max_output_tokens if provided
    if max_output_tokens is not None:
        model_kwargs["max_tokens"] = max_output_tokens
    
    # Create ChatLiteLLM with router
    model = ChatLiteLLM(
        router=router,
        model=router_model_name,  # Maps to 'model_name' in router list
        temperature=temperature,
        max_retries=0,  # Disable internal retries; Router handles it
        model_kwargs=model_kwargs,
    )
    
    logger.info(
        f"{log_name}_initialized_litellm",
        model=router_model_name,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    
    return model


def get_llm(
    *,
    model_name: str | None = None,
    thinking_level: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    log_name: str = "llm",
) -> BaseChatModel:
    """
    Get or create a cached ChatModel by (model_name, thinking_level, temperature, max_output_tokens).
    All LLM vending goes through this singleton cache.
    """
    llm_config = _get_first_available_llm_config(model_name=model_name)
    resolved_model_name = llm_config["MODEL_NAME"]
    resolved_thinking = thinking_level or llm_config.get("THINKING_LEVEL") or constants.CONSTANTS.get("LLM_THINKING_LEVEL")
    resolved_temp = temperature if temperature is not None else (llm_config.get("TEMPERATURE") if llm_config.get("TEMPERATURE") is not None else constants.CONSTANTS.get("LLM_TEMPERATURE"))
    key = (resolved_model_name, resolved_thinking, resolved_temp, max_output_tokens)
    with _llm_cache_lock:
        if key in _llm_cache:
            return _llm_cache[key]
        m = _create_model(
            model_name=resolved_model_name,
            provider=llm_config["PROVIDER"],
            location=llm_config.get("LOCATION"),
            thinking_level=resolved_thinking,
            temperature=resolved_temp,
            max_output_tokens=max_output_tokens,
            log_name=log_name,
        )
        _llm_cache[key] = m
        return m


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
    """Get Langfuse callback handler if enabled, None otherwise.
    
    Note: In Langfuse v3, session_id, user_id, and metadata should be set via
    config["metadata"] when invoking chains, not as constructor arguments.
    Use the following metadata keys:
    - "langfuse_session_id" for session tracking
    - "langfuse_user_id" for user tracking
    - Other metadata keys will be attached to traces
    
    Returns:
        CallbackHandler instance if Langfuse is enabled, None otherwise
    """
    if not settings.LANGFUSE_ENABLED:
        return None
    get_langfuse_client()  # Ensure client is initialized
    
    # CallbackHandler in Langfuse v3 doesn't accept constructor arguments
    # session_id, user_id, and metadata should be set via config["metadata"]
    handler = CallbackHandler()
    return handler


def extract_callbacks_from_config(config: Any | None) -> list[Any] | None:
    """Extract callbacks from RunnableConfig or dict config.
    
    LangGraph nodes receive RunnableConfig which may contain callbacks.
    When converting to dict, callbacks need to be explicitly preserved.
    This helper extracts callbacks from either a RunnableConfig object or a dict.
    
    Filters out AsyncCallbackManager objects and only returns actual callback handler
    instances, as managers cannot be passed directly to invoke/ainvoke methods.
    
    Args:
        config: RunnableConfig object or dict containing callbacks
        
    Returns:
        List of callback handlers if found, None otherwise
    """
    if not config:
        return None
    
    callbacks = None
    
    # Try accessing as dict first
    if isinstance(config, dict):
        callbacks = config.get("callbacks")
    
    # Try accessing as object attribute
    if not callbacks and hasattr(config, "callbacks"):
        callbacks = config.callbacks
    
    if not callbacks:
        return None
    
    # Normalize to list
    if not isinstance(callbacks, list):
        callbacks = [callbacks]
    
    # Filter out callback managers - only return actual handler instances
    # AsyncCallbackManager and CallbackManager objects cannot be passed directly
    # to invoke/ainvoke methods and will cause AttributeError: 'AsyncCallbackManager' object has no attribute 'run_inline'
    filtered_callbacks = []
    for cb in callbacks:
        # Skip callback managers (they don't have run_inline and cause errors)
        if hasattr(cb, "__class__"):
            class_name = cb.__class__.__name__
            # Check if it's a callback manager (not a handler)
            # Managers have "CallbackManager" in their name but not "Handler"
            if "CallbackManager" in class_name and "Handler" not in class_name:
                # Skip managers entirely - they cannot be passed to invoke/ainvoke
                # If handlers were meant to be used, they should have been passed separately
                logger.debug(
                    "skipping_callback_manager",
                    manager_class=class_name,
                    reason="CallbackManager objects cannot be passed directly to invoke/ainvoke",
                )
                continue
        # Include actual handler instances
        filtered_callbacks.append(cb)
    
    return filtered_callbacks if filtered_callbacks else None


def get_agent_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    model_name: str | None = None,
) -> BaseChatModel:
    """
    Get or create cached model for agent (shared across flows). Delegates to get_llm.
    """
    return get_llm(
        model_name=model_name,
        thinking_level=thinking_level,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        log_name="agent_model",
    )


def get_tool_model(
    thinking_level: str | None = None,
    temperature: float | None = None,
    model_name: str | None = None,
) -> BaseChatModel:
    """
    Get or create cached model for tool operations. Delegates to get_llm.
    If model_name is None, uses the first available LLM config (caller can pass
    _current_model_name.get() to align with the parent flow's model).
    """
    return get_llm(
        model_name=model_name,
        thinking_level=thinking_level,
        temperature=temperature,
        log_name="tool_model",
    )

