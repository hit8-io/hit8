"""
Health check endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint that doesn't require database or Firebase."""
    return {
        "status": "healthy",
        "service": "hit8-api",
        "version": settings.app_version,
    }

