"""
FastAPI application and API initialization.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.database import cleanup_pool, initialize_pool
from app.api.checkpointer import cleanup_checkpointer, initialize_checkpointer
from app.api.middleware import setup_cors, setup_exception_handlers, setup_api_token_middleware, setup_security_headers
from app.api.routes import api_router
from app.config import settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    # Startup: Initialize connection pool and checkpointer
    try:
        await initialize_pool()
        await initialize_checkpointer()
        logger.info("database_startup_complete")
    except Exception as e:
        logger.error(
            "database_startup_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
    
    logger.info("application_startup_complete")
    
    # Application runs here
    yield
    
    # Shutdown: Cleanup checkpointer and connection pool
    try:
        await cleanup_checkpointer()
        await cleanup_pool()
        logger.info("database_shutdown_complete")
    except Exception as e:
        logger.error(
            "database_shutdown_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
    
    logger.info("application_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )
    
    # Setup middleware
    setup_cors(app)
    setup_security_headers(app)
    setup_api_token_middleware(app)
    setup_exception_handlers(app)
    
    # Include API routes
    app.include_router(api_router)
    
    return app


# Create the app instance
app = create_app()
