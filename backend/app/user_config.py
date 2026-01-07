"""
User configuration service for managing user accounts, orgs, and projects.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Cache for user configuration
_user_config_cache: dict[str, dict[str, Any]] | None = None


def _load_users_config() -> dict[str, dict[str, Any]]:
    """Load and parse users.json configuration file.
    
    Returns:
        Dictionary mapping email addresses to user configuration.
        
    Raises:
        FileNotFoundError: If users.json file doesn't exist.
        ValueError: If users.json is invalid JSON or missing required fields.
    """
    global _user_config_cache
    
    if _user_config_cache is not None:
        return _user_config_cache
    
    # Get the path to users.json (in app directory)
    app_dir = Path(__file__).parent
    users_file = app_dir / "users.json"
    
    if not users_file.exists():
        raise FileNotFoundError(
            f"users.json not found at {users_file}. "
            "Please create the configuration file."
        )
    
    try:
        with open(users_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in users.json: {e}") from e
    
    if "users" not in config_data:
        raise ValueError("users.json must contain a 'users' array")
    
    if not isinstance(config_data["users"], list):
        raise ValueError("users.json 'users' field must be an array")
    
    # Build email -> user config mapping
    user_map: dict[str, dict[str, Any]] = {}
    
    for user in config_data["users"]:
        if not isinstance(user, dict):
            raise ValueError("Each user in users.json must be an object")
        
        if "email" not in user:
            raise ValueError("Each user must have an 'email' field")
        
        email = user["email"].lower().strip()
        
        if "account" not in user:
            raise ValueError(f"User {email} must have an 'account' field")
        
        if "projects" not in user:
            raise ValueError(f"User {email} must have a 'projects' field")
        
        if not isinstance(user["projects"], dict):
            raise ValueError(f"User {email} 'projects' field must be an object")
        
        # Validate that projects for each org is a list
        for org, projects in user["projects"].items():
            if not isinstance(projects, list):
                raise ValueError(
                    f"User {email} projects for org '{org}' must be an array"
                )
        
        # Derive orgs from projects keys
        orgs = list(user["projects"].keys())
        
        user_map[email] = {
            "email": email,
            "account": user["account"],
            "orgs": orgs,  # Derived from projects keys
            "projects": user["projects"],
        }
    
    _user_config_cache = user_map
    logger.info(
        "users_config_loaded",
        user_count=len(user_map),
    )
    
    return user_map


def get_user_config(email: str) -> dict[str, Any] | None:
    """Get user configuration by email address.
    
    Args:
        email: User email address (case-insensitive).
        
    Returns:
        User configuration dict with 'account', 'orgs', and 'projects' keys,
        or None if user not found.
    """
    try:
        users_config = _load_users_config()
        email_lower = email.lower().strip()
        return users_config.get(email_lower)
    except Exception as e:
        logger.error(
            "get_user_config_failed",
            email=email,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def validate_user_access(email: str, org: str, project: str) -> bool:
    """Validate that a user has access to a specific org/project combination.
    
    Args:
        email: User email address (case-insensitive).
        org: Organization name.
        project: Project name.
        
    Returns:
        True if user has access, False otherwise.
    """
    user_config = get_user_config(email)
    
    if user_config is None:
        logger.warning(
            "user_not_found",
            email=email,
        )
        return False
    
    # Check if org exists in user's projects (orgs are derived from projects keys)
    if org not in user_config["projects"]:
        logger.warning(
            "user_org_access_denied",
            email=email,
            org=org,
            accessible_orgs=list(user_config["projects"].keys()),
        )
        return False
    
    # Check if project is in user's projects for this org
    org_projects = user_config["projects"].get(org, [])
    if project not in org_projects:
        logger.warning(
            "user_project_access_denied",
            email=email,
            org=org,
            project=project,
            accessible_projects=org_projects,
        )
        return False
    
    return True


def get_user_orgs_projects(email: str) -> dict[str, Any] | None:
    """Get user's accessible orgs and projects.
    
    Args:
        email: User email address (case-insensitive).
        
    Returns:
        Dictionary with 'account', 'orgs', and 'projects' keys,
        or None if user not found.
        Note: 'orgs' is derived from 'projects' keys.
    """
    user_config = get_user_config(email)
    
    if user_config is None:
        return None
    
    # Derive orgs from projects keys
    orgs = list(user_config["projects"].keys())
    
    return {
        "account": user_config["account"],
        "orgs": orgs,
        "projects": user_config["projects"],
    }

