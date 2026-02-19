"""Shared application lifecycle management for FastAPI and Cloud Run Jobs."""
from __future__ import annotations

import structlog

from app.api.database import cleanup_pool, initialize_pool
from app.api.checkpointer import cleanup_checkpointer, initialize_checkpointer

logger = structlog.get_logger(__name__)


async def startup() -> None:
    """Initialize application resources (pool and checkpointer)."""
    # Initialize database pool - non-blocking so app can start even if DB is temporarily unavailable
    # Health endpoint doesn't require DB, so we allow startup to succeed
    try:
        await initialize_pool()
    except Exception as e:
        logger.error(
            "database_pool_initialization_failed",
            error=str(e),
            error_type=type(e).__name__,
            message="Application will start but database-dependent endpoints will fail. "
                    "Check DATABASE_CONNECTION_STRING, network/firewall, and SSL configuration.",
        )
        # Don't raise - allow app to start so /health endpoint is available
    
    # Initialize checkpointer - requires pool, so skip if pool failed
    try:
        await initialize_checkpointer()
    except Exception as e:
        logger.error(
            "checkpointer_initialization_failed",
            error=str(e),
            error_type=type(e).__name__,
            message="Checkpointer initialization failed. Graph state persistence will not work.",
        )
        # Don't raise - allow app to start
    
    logger.info("application_startup_complete")


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
