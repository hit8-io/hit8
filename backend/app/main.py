"""
Application entrypoint.

Initializes the application and creates the FastAPI app.
"""
from __future__ import annotations

from app.startup import initialize_app

# Initialize application (secrets, logging, etc.)
initialize_app()

# Import and expose the FastAPI app
from app.api import app

__all__ = ["app"]
