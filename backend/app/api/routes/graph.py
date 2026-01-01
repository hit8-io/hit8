"""
Graph-related endpoints.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.graph_manager import get_graph
from app.deps import verify_google_token

logger = structlog.get_logger(__name__)
router = APIRouter()


def _serialize_messages(state: Any) -> list[dict[str, Any]]:
    """Serialize messages from state to dictionary format.
    
    Args:
        state: Graph state object
        
    Returns:
        List of serialized message dictionaries
    """
    messages = []
    if hasattr(state, "values") and "messages" in state.values:
        for msg in state.values["messages"]:
            if hasattr(msg, "content"):
                messages.append({
                    "type": type(msg).__name__,
                    "content": str(msg.content) if hasattr(msg, "content") else str(msg)
                })
    return messages


def _extract_graph_history(state: Any, state_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract graph execution history from state.
    
    Args:
        state: Graph state object
        state_dict: Partially constructed state dictionary
        
    Returns:
        List of history entries
    """
    history: list[dict[str, Any]] = []
    
    # Method 1: Check if state has task information
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            if hasattr(task, "name"):
                history.append({"node": task.name})
            elif isinstance(task, dict) and "name" in task:
                history.append({"node": task["name"]})
    
    # Method 2: Fallback - infer from state values
    if not history:
        messages = state_dict.get("values", {}).get("messages", [])
        has_human = any(msg.get("type") == "HumanMessage" for msg in messages)
        has_ai = any(msg.get("type") == "AIMessage" for msg in messages)
        if has_human and has_ai:
            history.append({"node": "generate"})
    
    return history


@router.get("/graph/structure")
async def get_graph_structure(
    user_payload: dict = Depends(verify_google_token)
):
    """Get the LangGraph structure as JSON."""
    try:
        return get_graph().get_graph().to_json()
    except Exception as e:
        logger.exception("graph_structure_export_failed", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export graph structure: {str(e)}"
        )


@router.get("/graph/state")
async def get_graph_state(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token)
):
    """Get the current execution state for a thread."""
    try:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        
        # Get state with history to track visited nodes
        try:
            state = get_graph().get_state(config)
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
        messages = _serialize_messages(state)
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

