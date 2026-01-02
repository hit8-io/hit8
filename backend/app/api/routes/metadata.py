"""
Metadata endpoint.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import get_metadata, settings
from app.deps import verify_google_token

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/metadata")
async def get_metadata_endpoint(
    user_payload: dict = Depends(verify_google_token)
):
    """Get application metadata (account, org, project, environment, log_level)."""
    try:
        metadata = get_metadata()
        # Add log_level to metadata
        metadata["log_level"] = settings.log_level
        return metadata
    except Exception as e:
        logger.error(
            "metadata_retrieval_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metadata: {str(e)}"
        )

