"""
Metadata endpoint.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.auth import verify_google_token

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/metadata")
async def get_metadata_endpoint(
    user_payload: dict = Depends(verify_google_token)
):
    """Get application metadata (account, org, project, environment, log_level)."""
    metadata = settings.metadata.copy()
    metadata["log_level"] = settings.log_level
    return metadata

