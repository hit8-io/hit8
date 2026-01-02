"""
API routes package.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import chat, graph, health, metadata, version

# Create main API router
api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router)
api_router.include_router(metadata.router)
api_router.include_router(version.router)
api_router.include_router(graph.router)
api_router.include_router(chat.router)

