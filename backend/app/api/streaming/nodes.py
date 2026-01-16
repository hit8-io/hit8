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


def extract_state_update(event: dict[str, Any], flow: str = "chat") -> dict[str, Any] | None:
    """Extract state update information from stream_events event.
    
    Args:
        event: Event dictionary from stream_events
        flow: Flow type ("chat" or "report") to determine what state to extract
        
    Returns:
        Dictionary with state update data or None if not applicable
    """
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Try to extract state from different possible locations
    # on_chain_stream might have chunk in data.output or data.chunk
    # on_chain_end might have output with state information
    # For report flow, we need the actual merged state, not just node output
    # LangGraph provides state snapshot in data.data (for v2 events) or data.output
    state_info = {}
    if flow == "report":
        # For report flow, try to get the actual state snapshot
        # LangGraph v2 events may have state in data.data or data.output
        if "data" in data and isinstance(data["data"], dict):
            # Check if this is a state snapshot
            state_snapshot = data["data"]
            if isinstance(state_snapshot, dict) and ("pending_clusters" in state_snapshot or "chapters" in state_snapshot):
                state_info = state_snapshot
        # Fallback to output if no state snapshot found
        if not state_info:
            state_info = data.get("output", {})
    else:
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
    # Note: We don't include the actual messages array because it may contain
    # ToolMessage objects which are not JSON serializable
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
    
    # Ensure we don't accidentally include non-serializable objects
    # Filter out any ToolMessage or other LangChain message objects from state_info
    # by only extracting the fields we need
    
    result: dict[str, Any] = {
        "next": next_nodes,
        "message_count": message_count,
    }
    
    # Extract report-specific state if flow is "report"
    if flow == "report":
        report_state: dict[str, Any] = {}
        
        # Extract from state_info (output) or data
        # Create a clean copy to avoid including non-serializable objects like ToolMessage
        state_values = {}
        if isinstance(state_info, dict):
            # Only copy the fields we need, avoiding messages which may contain ToolMessage objects
            for key in ["raw_procedures", "pending_clusters", "chapters", "chapters_by_file_id", "final_report"]:
                if key in state_info:
                    state_values[key] = state_info[key]
        elif isinstance(data, dict):
            for key in ["raw_procedures", "pending_clusters", "chapters", "chapters_by_file_id", "final_report"]:
                if key in data:
                    state_values[key] = data[key]
        
        # Extract raw_procedures - always include if present (even if empty list)
        if "raw_procedures" in state_values:
            raw_procedures = state_values.get("raw_procedures", [])
            if raw_procedures is not None:
                report_state["raw_procedures"] = raw_procedures
        
        # Extract pending_clusters
        if "pending_clusters" in state_values:
            report_state["pending_clusters"] = state_values.get("pending_clusters", [])
        
        # Extract chapters
        if "chapters" in state_values:
            chapters = state_values.get("chapters", [])
            if isinstance(chapters, list):
                report_state["chapters"] = chapters
        
        # Extract chapters_by_file_id (for accurate chapter-to-cluster matching)
        if "chapters_by_file_id" in state_values:
            chapters_by_file_id = state_values.get("chapters_by_file_id")
            if isinstance(chapters_by_file_id, dict):
                report_state["chapters_by_file_id"] = chapters_by_file_id
        
        # Extract final_report (only if present)
        if "final_report" in state_values:
            final_report = state_values.get("final_report")
            if final_report is not None:
                report_state["final_report"] = final_report
        
        # Always include report_state if it has any data (including empty lists)
        if report_state:
            result["report_state"] = report_state
    
    # Only send state update if we have meaningful data
    if next_nodes or message_count > 0 or (flow == "report" and result.get("report_state")):
        return result
    
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
        # Note: process_node_event is used by old queue-based system which defaults to "chat" flow
        state_data = extract_state_update(event, flow="chat")
        if state_data:
            logger.debug(
                "state_update_from_node_event",
                node_name=node_name,
                visited_nodes=visited_nodes.copy(),
                visited_nodes_count=len(visited_nodes),
                thread_id=thread_id,
            )
            state_update_event = {
                "type": EVENT_STATE_UPDATE,
                "next": state_data["next"],
                "message_count": state_data["message_count"],
                "thread_id": thread_id,
                "visited_nodes": visited_nodes.copy(),
            }
            # Include report_state if available (though unlikely in queue-based system)
            if "report_state" in state_data:
                state_update_event["report_state"] = state_data["report_state"]
            event_queue.put((QUEUE_EVENT, state_update_event))
    
    return current_node, visited_nodes
