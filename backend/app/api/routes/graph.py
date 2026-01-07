"""
Graph-related endpoints.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.graph_manager import get_graph
from app.auth import verify_google_token
from app.user_config import validate_user_access

logger = structlog.get_logger(__name__)
router = APIRouter()


from app.api.utils import serialize_messages


def _extract_graph_history(state: Any, state_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract graph execution history from state."""
    history: list[dict[str, Any]] = []
    
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            task_name = None
            if hasattr(task, "name"):
                task_name = task.name
            elif isinstance(task, dict) and "name" in task:
                task_name = task["name"]
            if task_name:
                history.append({"node": task_name})
    
    return history


@router.get("/structure")
async def get_graph_structure(
    user_payload: dict = Depends(verify_google_token),
    x_org: str = Header(..., alias="X-Org"),
    x_project: str = Header(..., alias="X-Project"),
):
    """Get the LangGraph structure as JSON.
    
    Requires X-Org and X-Project headers to specify which org/project to use.
    """
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
        return get_graph(org, project).get_graph().to_json()
    except Exception as e:
        logger.exception("graph_structure_export_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export graph structure: {str(e)}"
        )


@router.get("/state")
async def get_graph_state(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str = Header(..., alias="X-Org"),
    x_project: str = Header(..., alias="X-Project"),
):
    """Get the current execution state for a thread.
    
    Requires X-Org and X-Project headers to specify which org/project to use.
    """
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
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    try:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        
        # Get state with history to track visited nodes
        try:
            state = get_graph(org, project).get_state(config)
        except Exception as state_error:
            # If state retrieval fails, return empty state
            logger.debug(
                "graph_state_not_found",
                thread_id=thread_id,
                error=str(state_error),
                error_type=type(state_error).__name__,
            )
            return {
                "values": {},
                "next": [],
                "history": [],
            }
        
        # Convert state to dict, handling serialization
        state_dict: dict[str, Any] = {
            "values": {},
            "next": state.next if hasattr(state, "next") else [],
        }
        
        # Serialize messages if present
        messages = serialize_messages(state)
        if messages:
            state_dict["values"]["messages"] = messages
            state_dict["values"]["message_count"] = len(messages)
        
        # Add next nodes
        if hasattr(state, "next"):
            state_dict["next"] = list(state.next) if state.next else []
        
        # Get history by examining state and checkpoints
        try:
            state_dict["history"] = _extract_graph_history(state, state_dict)
        except Exception:
            state_dict["history"] = []
        
        return state_dict
    except Exception as e:
        logger.error(
            "graph_state_retrieval_failed",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve graph state: {str(e)}"
        )

