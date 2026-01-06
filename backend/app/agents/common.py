"""
Shared utilities for LangGraph agents.
"""
from __future__ import annotations

import threading

import structlog
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config import settings

logger = structlog.get_logger(__name__)

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

