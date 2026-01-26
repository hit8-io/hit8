"""
FastAPI application and API initialization.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.lifecycle import shutdown, startup
from app.api.middleware import setup_cors, setup_exception_handlers, setup_api_token_middleware, setup_security_headers
from app.api.routes import api_router
from app.config import settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    await startup()
    yield
    await shutdown()


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
