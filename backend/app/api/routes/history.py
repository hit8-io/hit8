"""
History endpoint for retrieving user chat threads.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.user_threads import get_user_threads
from app.auth import verify_google_token
from app.user_config import validate_user_access

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("")
async def get_history(
    user_payload: dict = Depends(verify_google_token),
    x_org: str = Header(..., alias="X-Org"),
    x_project: str = Header(..., alias="X-Project"),
):
    """Get chat thread history for the authenticated user.
    
    Returns threads sorted by last_accessed_at in descending order (most recent first).
    Requires X-Org and X-Project headers to specify which org/project to use.
    
    Returns:
        JSON array of thread objects with:
        - thread_id (str)
        - user_id (str)
        - title (str | None)
        - created_at (str, ISO format)
        - last_accessed_at (str, ISO format)
    """
    user_id = user_payload["sub"]
    email = user_payload["email"]
    org = x_org.strip()
    project = x_project.strip()
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    try:
        threads = await get_user_threads(user_id)
        logger.debug(
            "history_retrieved",
            user_id=user_id,
            thread_count=len(threads),
            org=org,
            project=project,
        )
        return threads
    except Exception as e:
        logger.error(
            "history_retrieval_failed",
            user_id=user_id,
            org=org,
            project=project,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return empty array on error (with logging) to avoid breaking the frontend
        return []
