"""
Application entrypoint.

Initializes the application and creates the FastAPI app.
"""
from __future__ import annotations

import structlog

from app.config import settings
from app.logging import configure_structlog, setup_logging

# Initialize structlog before other imports that might use logging
configure_structlog()

logger = structlog.get_logger(__name__)


# Initialize application
setup_logging()
logger.info("application_initialized")

# Import and expose the FastAPI app
from app.api import app

__all__ = ["app"]
