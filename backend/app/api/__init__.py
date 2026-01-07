"""
FastAPI application and API initialization.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.api.middleware import setup_cors, setup_exception_handlers, setup_api_token_middleware
from app.api.routes import api_router
from app.config import settings

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
    )
    
    # Setup middleware
    setup_cors(app)
    setup_api_token_middleware(app)
    setup_exception_handlers(app)
    
    # Include API routes
    app.include_router(api_router)
    
    # Startup event
    @app.on_event("startup")
    async def startup_event():
        """Log that the application has started successfully."""
        logger.info("application_startup_complete")
    
    return app


# Create the app instance
app = create_app()
