"""
API routes package.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import chat, graph, health, metadata, version

# Create main API router
api_router = APIRouter()

# Health and version (no auth)
api_router.include_router(health.router, tags=["health"])
api_router.include_router(version.router, tags=["version"])

# Authenticated routes
api_router.include_router(metadata.router, tags=["metadata"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

