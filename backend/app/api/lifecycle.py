"""Shared application lifecycle management for FastAPI and Cloud Run Jobs."""
from __future__ import annotations

import structlog

from app.api.database import cleanup_pool, initialize_pool
from app.api.checkpointer import cleanup_checkpointer, initialize_checkpointer

logger = structlog.get_logger(__name__)


async def startup() -> None:
    """Initialize application resources (pool and checkpointer)."""
    try:
        await initialize_pool()
        await initialize_checkpointer()
        logger.info("application_startup_complete")
    except Exception as e:
        logger.error(
            "application_startup_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def shutdown() -> None:
    """Cleanup application resources (checkpointer and pool)."""
    try:
        await cleanup_checkpointer()
        await cleanup_pool()
        logger.info("application_shutdown_complete")
    except Exception as e:
        logger.error(
            "application_shutdown_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
