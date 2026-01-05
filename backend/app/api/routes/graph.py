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
        List of serialized message dictionaries with full details including tool_calls
    """
    from langchain_core.messages import AIMessage, ToolMessage
    
    messages = []
    if hasattr(state, "values") and "messages" in state.values:
        for msg in state.values["messages"]:
            msg_dict: dict[str, Any] = {
                "type": type(msg).__name__,
            }
            
            # Add content
            if hasattr(msg, "content"):
                msg_dict["content"] = str(msg.content) if msg.content is not None else ""
            
            # Add tool_calls for AIMessage
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_dict["tool_calls"] = []
                for tool_call in msg.tool_calls:
                    tool_call_dict: dict[str, Any] = {}
                    if hasattr(tool_call, "name"):
                        tool_call_dict["name"] = tool_call.name
                    if hasattr(tool_call, "args"):
                        tool_call_dict["args"] = tool_call.args
                    if hasattr(tool_call, "id"):
                        tool_call_dict["id"] = tool_call.id
                    # Also check for function format
                    if hasattr(tool_call, "function"):
                        func = tool_call.function
                        if hasattr(func, "name"):
                            tool_call_dict["name"] = func.name
                        if hasattr(func, "arguments"):
                            import json
                            try:
                                tool_call_dict["args"] = json.loads(func.arguments)
                            except (json.JSONDecodeError, TypeError):
                                tool_call_dict["args"] = func.arguments
                    msg_dict["tool_calls"].append(tool_call_dict)
            
            # Add tool_call_id and name for ToolMessage
            if isinstance(msg, ToolMessage):
                if hasattr(msg, "tool_call_id"):
                    msg_dict["tool_call_id"] = msg.tool_call_id
                if hasattr(msg, "name"):
                    msg_dict["name"] = msg.name
            
            # Add usage_metadata if available (for token counts)
            if hasattr(msg, "response_metadata") and msg.response_metadata:
                metadata = msg.response_metadata
                if isinstance(metadata, dict):
                    if "token_usage" in metadata:
                        msg_dict["usage_metadata"] = metadata["token_usage"]
                    elif "usage_metadata" in metadata:
                        msg_dict["usage_metadata"] = metadata["usage_metadata"]
            
            messages.append(msg_dict)
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

