"""
Stream finalization functions.
"""
from __future__ import annotations

import queue
from typing import Any

import structlog

from app.api.constants import EVENT_CONTENT_CHUNK, EVENT_NODE_END, EVENT_STATE_UPDATE
from app.api.graph_manager import get_graph
from app.api.streaming.constants import QUEUE_CHUNK, QUEUE_EVENT
from app.api.utils import extract_ai_message, extract_message_content

logger = structlog.get_logger(__name__)


def get_final_state_data(state: Any, visited_nodes: list[str]) -> dict[str, Any]:
    """Extract final state data including visited nodes, next nodes, and message count.
    
    Args:
        state: Final state object from graph
        visited_nodes: List of already visited nodes
        
    Returns:
        Dictionary with keys: visited_nodes, next_nodes, message_count
    """
    final_visited_nodes = visited_nodes.copy()
    
    # Extract visited nodes from tasks
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            task_name = None
            if hasattr(task, "name"):
                task_name = task.name
            elif isinstance(task, dict) and "name" in task:
                task_name = task["name"]
            if task_name and task_name not in final_visited_nodes:
                final_visited_nodes.append(task_name)
    
    # Extract next nodes
    final_next_nodes = []
    if hasattr(state, "next") and state.next:
        final_next_nodes = list(state.next) if isinstance(state.next, (list, set, tuple)) else []
    
    # Extract message count
    message_count = 0
    if hasattr(state, "values") and state.values:
        if isinstance(state.values, dict) and "messages" in state.values:
            messages = state.values.get("messages", [])
            if isinstance(messages, list):
                message_count = len(messages)
    
    return {
        "visited_nodes": final_visited_nodes,
        "next_nodes": final_next_nodes,
        "message_count": message_count,
    }


def get_final_content_from_state(state: Any) -> str | None:
    """Extract final AI message content from state.
    
    Args:
        state: State object from graph
        
    Returns:
        Final AI message content or None if not found
    """
    from langchain_core.messages import HumanMessage
    
    if hasattr(state, "values") and "messages" in state.values:
        final_messages = state.values["messages"]
        for msg in reversed(final_messages):
            if not isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                return extract_message_content(msg.content)
    return None


def finalize_stream(
    event_queue: queue.Queue,
    thread_id: str,
    config: dict[str, Any],
    current_node: str | None,
    visited_nodes: list[str],
    accumulated_content: str,
    last_ai_message_content: str,
    org: str,
    project: str,
) -> None:
    """Finalize stream by sending final state update and content."""
    # End any remaining active node
    if current_node:
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_NODE_END,
            "node": current_node,
            "thread_id": thread_id
        }))
    
    # Extract final state and content
    try:
        final_state = get_graph(org, project).get_state(config)
        
        # Send final state update
        state_data = get_final_state_data(final_state, visited_nodes)
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_STATE_UPDATE,
            "next": state_data["next_nodes"],
            "message_count": state_data["message_count"],
            "thread_id": thread_id,
            "visited_nodes": state_data["visited_nodes"],
        }))
        
        # Get final content if not already accumulated
        if not accumulated_content and not last_ai_message_content:
            last_ai_message_content = get_final_content_from_state(final_state)
    except Exception as e:
        logger.debug(
            "failed_to_get_final_state",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )
    
    # Send final content
    final_content = accumulated_content or last_ai_message_content
    if final_content:
        if not accumulated_content:
            event_queue.put((QUEUE_CHUNK, {
                "type": EVENT_CONTENT_CHUNK,
                "content": final_content,
                "accumulated": final_content,
                "thread_id": thread_id,
            }))
        
        event_queue.put((QUEUE_CHUNK, {
            "__final_content__": True,
            "content": final_content,
        }))
        
        logger.info(
            "stream_completed",
            thread_id=thread_id,
            final_content_length=len(final_content),
            had_incremental_chunks=bool(accumulated_content),
        )
    else:
        logger.warning(
            "stream_completed_no_content",
            thread_id=thread_id,
        )


async def extract_final_response(config: dict[str, Any], thread_id: str, org: str, project: str) -> str | None:
    """Extract final response from graph state."""
    try:
        import asyncio
        # Use asyncio.to_thread to avoid AsyncPostgresSaver sync call error
        final_state = await asyncio.to_thread(get_graph(org, project).get_state, config)
        if hasattr(final_state, "values") and "messages" in final_state.values:
            ai_message = extract_ai_message(final_state.values["messages"])
            return extract_message_content(ai_message.content)
    except Exception as e:
        logger.error("failed_to_get_final_state", error=str(e), thread_id=thread_id)
    return None
