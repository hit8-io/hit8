"""
User configuration service for managing user accounts, orgs, and projects.

Supports both individual user entries (by email) and domain-based entries
(by email domain). Individual entries take precedence over domain entries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Cache for user configuration
_user_config_cache: dict[str, dict[str, Any]] | None = None
_domain_config_cache: dict[str, dict[str, Any]] | None = None


def _extract_domain_from_email(email: str) -> str | None:
    """Extract domain from email address.
    
    Args:
        email: Email address (e.g., "user@example.com").
        
    Returns:
        Domain with @ prefix (e.g., "@example.com"), or None if invalid.
    """
    if "@" not in email:
        return None
    # Split on first @ only to handle edge cases
    _, domain = email.split("@", 1)
    return f"@{domain.lower()}"


def _validate_entry(entry: dict[str, Any], entry_index: int) -> None:
    """Validate a single configuration entry.
    
    Args:
        entry: Configuration entry dictionary.
        entry_index: Index of entry in users array (for error messages).
        
    Raises:
        ValueError: If entry is invalid.
    """
    if "account" not in entry:
        raise ValueError(f"Entry at index {entry_index} must have an 'account' field")
    
    if "projects" not in entry:
        raise ValueError(f"Entry at index {entry_index} must have a 'projects' field")
    
    if not isinstance(entry["projects"], dict):
        raise ValueError(f"Entry at index {entry_index} 'projects' field must be an object")
    
    # Validate nested structure: each org maps to an object where keys are project names
    # and values are flow arrays (must be non-empty arrays)
    for org, org_projects in entry["projects"].items():
        if not isinstance(org_projects, dict):
            raise ValueError(
                f"Entry at index {entry_index}: projects for org '{org}' must be an object"
            )
        
        # Validate each project has a flows array
        for project, flows in org_projects.items():
            if not isinstance(flows, list):
                raise ValueError(
                    f"Entry at index {entry_index}: flows for org '{org}' project '{project}' must be an array"
                )
            if len(flows) == 0:
                raise ValueError(
                    f"Entry at index {entry_index}: flows for org '{org}' project '{project}' must be a non-empty array"
                )
            # Validate each flow is a string
            for flow in flows:
                if not isinstance(flow, str):
                    raise ValueError(
                        f"Entry at index {entry_index}: flow in org '{org}' project '{project}' must be a string"
                    )


def _load_users_config() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load and parse users.json configuration file.
    
    Returns:
        Tuple of (user_map, domain_map):
        - user_map: Dictionary mapping email addresses to user configuration
        - domain_map: Dictionary mapping domains to domain-based configurations
        
    Raises:
        FileNotFoundError: If users.json file doesn't exist.
        ValueError: If users.json is invalid JSON or missing required fields.
    """
    global _user_config_cache, _domain_config_cache
    
    if _user_config_cache is not None and _domain_config_cache is not None:
        return _user_config_cache, _domain_config_cache
    
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
    
    # Build email -> user config mapping and domain -> config mapping
    user_map: dict[str, dict[str, Any]] = {}
    domain_map: dict[str, dict[str, Any]] = {}
    
    for index, entry in enumerate(config_data["users"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry at index {index} in users.json must be an object")
        
        _validate_entry(entry, index)
        
        # Derive orgs from projects keys
        orgs = list(entry["projects"].keys())
        
        config_entry = {
            "account": entry["account"],
            "orgs": orgs,
            "projects": entry["projects"],
        }
        
        # Check if this is a domain-based entry or individual user
        if "domain" in entry:
            # Domain-based entry
            domain = entry["domain"].lower().strip()
            if not domain.startswith("@"):
                raise ValueError(
                    f"Entry at index {index}: domain must start with '@', got: {domain}"
                )
            config_entry["domain"] = domain
            domain_map[domain] = config_entry
        elif "email" in entry:
            # Individual user entry
            email = entry["email"].lower().strip()
            config_entry["email"] = email
            user_map[email] = config_entry
        else:
            raise ValueError(
                f"Entry at index {index} must have either an 'email' or 'domain' field"
            )
    
    _user_config_cache = user_map
    _domain_config_cache = domain_map
    logger.info(
        "users_config_loaded",
        user_count=len(user_map),
        domain_count=len(domain_map),
    )
    
    return user_map, domain_map


def get_user_config(email: str) -> dict[str, Any] | None:
    """Get user configuration by email address.
    
    Checks individual user entries first, then domain-based entries.
    Individual entries take precedence over domain entries.
    
    Args:
        email: User email address (case-insensitive).
        
    Returns:
        User configuration dict with 'account', 'orgs', and 'projects' keys,
        or None if user not found.
    """
    try:
        users_config, domain_map = _load_users_config()
        email_lower = email.lower().strip()
        
        # First, check for individual user entry (takes precedence)
        if email_lower in users_config:
            return users_config[email_lower]
        
        # Then, check domain-based entries
        email_domain = _extract_domain_from_email(email_lower)
        if email_domain and email_domain in domain_map:
            logger.info(
                "user_matched_domain",
                email=email_lower,
                domain=email_domain,
            )
            return domain_map[email_domain]
        
        return None
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
    
    # Check if project exists in user's projects for this org
    # projects[org] is now a dict where keys are project names
    org_projects = user_config["projects"][org]
    if not isinstance(org_projects, dict):
        logger.warning(
            "user_project_structure_invalid",
            email=email,
            org=org,
        )
        return False
    
    if project not in org_projects:
        logger.warning(
            "user_project_access_denied",
            email=email,
            org=org,
            project=project,
            accessible_projects=list(org_projects.keys()),
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
        Note: 'orgs' is already derived and stored in the config.
        Projects structure: projects[org][project] = flows[]
    """
    user_config = get_user_config(email)
    
    if user_config is None:
        return None
    
    # orgs is already stored in the config, no need to re-derive
    return {
        "account": user_config["account"],
        "orgs": user_config["orgs"],
        "projects": user_config["projects"],
    }


def get_user_flows(email: str, org: str, project: str) -> list[str]:
    """Get available flows for a specific org/project combination.
    
    Args:
        email: User email address (case-insensitive).
        org: Organization name.
        project: Project name.
        
    Returns:
        List of available flow names, or empty list if user/org/project not found.
    """
    user_config = get_user_config(email)
    
    if user_config is None:
        return []
    
    # Check if org exists
    if org not in user_config["projects"]:
        return []
    
    org_projects = user_config["projects"][org]
    if not isinstance(org_projects, dict):
        return []
    
    # Check if project exists and return its flows
    if project not in org_projects:
        return []
    
    flows = org_projects[project]
    if not isinstance(flows, list):
        return []
    
    return flows


def validate_user_flow_access(email: str, org: str, project: str, flow: str) -> bool:
    """Validate that a user has access to a specific flow for an org/project combination.
    
    Args:
        email: User email address (case-insensitive).
        org: Organization name.
        project: Project name.
        flow: Flow name (e.g., "chat", "report").
        
    Returns:
        True if user has access to the flow, False otherwise.
    """
    if not validate_user_access(email, org, project):
        return False
    
    available_flows = get_user_flows(email, org, project)
    return flow in available_flows

