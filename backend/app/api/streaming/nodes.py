"""
Node event processing functions.
"""
from __future__ import annotations

from typing import Any

import queue

import structlog

from app.api.constants import EVENT_NODE_END, EVENT_NODE_START, EVENT_STATE_UPDATE
from app.api.streaming.constants import QUEUE_EVENT

logger = structlog.get_logger(__name__)


def extract_state_update(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract state update information from stream_events event.
    
    Args:
        event: Event dictionary from stream_events
        
    Returns:
        Dictionary with state update data or None if not applicable
    """
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Try to extract state from different possible locations
    # on_chain_stream might have chunk in data.output or data.chunk
    # on_chain_end might have output with state information
    state_info = data.get("output", {})
    if not isinstance(state_info, dict):
        state_info = data
    
    # Extract next nodes from various possible locations
    next_nodes = []
    if "next" in state_info:
        next_nodes = state_info.get("next", [])
        if not isinstance(next_nodes, list):
            next_nodes = []
    elif "next" in data:
        next_nodes = data.get("next", [])
        if not isinstance(next_nodes, list):
            next_nodes = []
    
    # Extract message count from various possible locations
    message_count = 0
    if "messages" in state_info:
        messages = state_info.get("messages", [])
        if isinstance(messages, list):
            message_count = len(messages)
    elif "messages" in data:
        messages = data.get("messages", [])
        if isinstance(messages, list):
            message_count = len(messages)
    elif "message_count" in state_info:
        message_count = state_info.get("message_count", 0)
    elif "message_count" in data:
        message_count = data.get("message_count", 0)
    
    # Only send state update if we have meaningful data
    if next_nodes or message_count > 0:
        return {
            "next": next_nodes,
            "message_count": message_count,
        }
    
    return None


def process_node_event(
    event: dict[str, Any],
    event_queue: queue.Queue,
    thread_id: str,
    current_node: str | None,
    visited_nodes: list[str],
) -> tuple[str | None, list[str]]:
    """Process events from astream_events() for node tracking.
    
    Tracks ALL nodes via on_chain_start/on_chain_end events, not just specific nodes.
    
    Returns:
        Tuple of (updated_current_node, updated_visited_nodes)
    """
    event_type = event.get("event", "")
    node_name = event.get("name", "")
    
    if not node_name:
        return current_node, visited_nodes
    
    # Handle chain start (node start)
    if event_type == "on_chain_start":
        if current_node != node_name:
            # End previous node if different
            if current_node:
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_NODE_END,
                    "node": current_node,
                    "thread_id": thread_id
                }))
            # Start new node
            current_node = node_name
            if node_name not in visited_nodes:
                visited_nodes.append(node_name)
            event_queue.put((QUEUE_EVENT, {
                "type": EVENT_NODE_START,
                "node": node_name,
                "thread_id": thread_id
            }))
    
    # Handle chain end (node end + state update)
    elif event_type == "on_chain_end":
        if current_node == node_name:
            event_queue.put((QUEUE_EVENT, {
                "type": EVENT_NODE_END,
                "node": node_name,
                "thread_id": thread_id
            }))
            current_node = None
        
        # Extract and send state update
        state_data = extract_state_update(event)
        if state_data:
            logger.debug(
                "state_update_from_node_event",
                node_name=node_name,
                visited_nodes=visited_nodes.copy(),
                visited_nodes_count=len(visited_nodes),
                thread_id=thread_id,
            )
            event_queue.put((QUEUE_EVENT, {
                "type": EVENT_STATE_UPDATE,
                "next": state_data["next"],
                "message_count": state_data["message_count"],
                "thread_id": thread_id,
                "visited_nodes": visited_nodes.copy(),
            }))
    
    return current_node, visited_nodes
