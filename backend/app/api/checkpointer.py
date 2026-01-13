"""
Checkpointer management for LangGraph with AsyncPostgresSaver.

Provides AsyncPostgresSaver instance for persistent checkpoint storage
across all graph instances. Uses the shared connection pool from database module.

Initialized once at application startup via FastAPI lifespan.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import-untyped]

from app.api.database import get_pool, initialize_pool

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as AsyncPostgresSaverType  # type: ignore[import-untyped]

logger = structlog.get_logger(__name__)

# Global variable to hold the checkpointer
# Initialized once at application startup via FastAPI lifespan
checkpointer: AsyncPostgresSaverType | None = None


async def initialize_checkpointer() -> None:
    """
    Initialize the checkpointer using the shared connection pool.
    
    This should be called once at application startup via FastAPI lifespan.
    The checkpointer is stored in a module-level global variable.
    The connection pool must be initialized first via initialize_pool().
    
    Raises:
        Exception: If checkpointer initialization fails
    """
    global checkpointer
    
    if checkpointer is not None:
        logger.warning("checkpointer_already_initialized")
        return
    
    # Ensure pool is initialized first
    pool = get_pool()
    
    logger.info(
        "initializing_checkpointer",
    )
    
    # Initialize checkpointer with the shared pool
    checkpointer = AsyncPostgresSaver(pool)
    
    logger.info(
        "checkpointer_initialized",
        checkpointer_type="AsyncPostgresSaver",
    )


async def cleanup_checkpointer() -> None:
    """
    Cleanup the checkpointer on application shutdown.
    
    Note: The connection pool cleanup is handled separately in database module.
    This only cleans up the checkpointer reference.
    
    This should be called in the FastAPI lifespan shutdown phase.
    """
    global checkpointer
    
    if checkpointer is not None:
        logger.info("cleaning_up_checkpointer")
        checkpointer = None
        logger.info("checkpointer_cleaned_up")


def get_checkpointer() -> AsyncPostgresSaverType:
    """
    Get the AsyncPostgresSaver checkpointer instance.
    
    The checkpointer must be initialized via initialize_checkpointer() 
    at application startup before this function is called.
    
    Returns:
        AsyncPostgresSaver: The checkpointer instance
        
    Raises:
        RuntimeError: If checkpointer has not been initialized
    """
    global checkpointer
    
    if checkpointer is None:
        raise RuntimeError(
            "Checkpointer has not been initialized. "
            "Ensure initialize_checkpointer() is called at application startup via FastAPI lifespan."
        )
    
    return checkpointer


async def setup_checkpointer() -> None:
    """
    Run checkpointer.setup() to create database tables.
    
    This should be called manually via the setup script before using the checkpointer
    in production. The tables are created once and persist across application restarts.
    
    Raises:
        Exception: If setup fails
    """
    # Initialize checkpointer if not already initialized
    if checkpointer is None:
        await initialize_checkpointer()
    
    logger.info("running_checkpointer_setup")
    
    try:
        await checkpointer.setup()
        logger.info("checkpointer_setup_completed")
    except Exception as e:
        logger.error(
            "checkpointer_setup_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
