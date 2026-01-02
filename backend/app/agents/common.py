"""
Shared utilities for LangGraph agents.
"""
from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

import structlog

from app.config import settings

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

logger = structlog.get_logger(__name__)

# Global Langfuse client (shared across agents)
_langfuse_client: Langfuse | None = None
_langfuse_lock = threading.Lock()


def get_langfuse_client() -> Langfuse | None:
    """Get or create Langfuse client (lazy initialization, shared across agents).
    
    Returns:
        Langfuse client instance or None if disabled/failed
    """
    global _langfuse_client
    if not settings.langfuse_enabled:
        return None
    
    if _langfuse_client is None:
        with _langfuse_lock:
            if _langfuse_client is None:
                try:
                    from langfuse import Langfuse
                    
                    # Validator ensures these are not None when langfuse_enabled is True
                    assert settings.langfuse_public_key is not None
                    assert settings.langfuse_secret_key is not None
                    assert settings.langfuse_base_url is not None
                    
                    env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
                    
                    # Convert Docker service names to localhost when running locally
                    langfuse_url = settings.langfuse_base_url
                    # Check if running outside Docker (no DOCKER_CONTAINER env var or not in container)
                    if not os.getenv("DOCKER_CONTAINER") and not os.path.exists("/.dockerenv"):
                        # Replace Docker service names with localhost
                        if langfuse_url and "langfuse:" in langfuse_url:
                            langfuse_url = langfuse_url.replace("langfuse:", "localhost:")
                            logger.debug(
                                "langfuse_url_converted_for_local",
                                original=settings.langfuse_base_url,
                                converted=langfuse_url,
                            )
                    
                    _langfuse_client = Langfuse(
                        public_key=settings.langfuse_public_key,
                        secret_key=settings.langfuse_secret_key,
                        host=langfuse_url,
                    )
                    logger.info(
                        "langfuse_client_initialized",
                        env=env,
                        base_url=settings.langfuse_base_url,
                    )
                except Exception as e:
                    logger.error(
                        "langfuse_client_init_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        env=os.getenv("ENVIRONMENT", "unknown"),
                    )
                    # Don't raise - allow app to continue without Langfuse
                    return None
    
    return _langfuse_client


def get_langfuse_handler() -> CallbackHandler | None:
    """Get Langfuse callback handler if enabled, None otherwise.
    
    Returns:
        CallbackHandler instance or None if disabled/failed
    """
    if not settings.langfuse_enabled:
        return None
    
    try:
        # Ensure Langfuse client is initialized before creating handler
        get_langfuse_client()
        
        from langfuse.langchain import CallbackHandler
        # CallbackHandler uses the singleton client (now lazily initialized)
        handler = CallbackHandler()
        logger.debug("langfuse_callback_handler_created")
        return handler
    except Exception as e:
        logger.warning(
            "langfuse_callback_handler_creation_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None

