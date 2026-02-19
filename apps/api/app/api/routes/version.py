"""
Version endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/version")
async def get_version():
    """Get the application version."""
    return {
        "version": settings.APP_VERSION,
    }

