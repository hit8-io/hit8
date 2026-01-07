"""
Configuration endpoints for user account, org, and project management.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_google_token
from app.user_config import get_user_orgs_projects

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/user")
async def get_user_config_endpoint(
    user_payload: dict = Depends(verify_google_token)
):
    """Get user's account and accessible orgs/projects.
    
    Returns:
        Dictionary with:
        - account: User's account name
        - orgs: List of accessible organization names
        - projects: Dictionary mapping org names to lists of project names
        
    Raises:
        HTTPException: 404 if user not found in configuration.
    """
    email = user_payload["email"]
    
    user_config = get_user_orgs_projects(email)
    
    if user_config is None:
        logger.warning(
            "user_config_not_found",
            email=email,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User configuration not found for email: {email}",
        )
    
    logger.debug(
        "user_config_retrieved",
        email=email,
        account=user_config["account"],
        org_count=len(user_config["orgs"]),  # orgs derived from projects keys
    )
    
    return user_config

