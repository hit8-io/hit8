"""
Pure async event processing for LangGraph streaming.

This module processes astream_events() directly in the FastAPI event loop,
eliminating the need for background threads and event loop synchronization.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

from app.api.constants import (
    EVENT_CONTENT_CHUNK,
    EVENT_GRAPH_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_STATE_UPDATE,
    EVENT_TOOL_END,
    EVENT_TOOL_START,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph  # type: ignore[import-untyped]
from app.api.streaming.llm import extract_llm_end_event, extract_llm_start_event
from app.api.streaming.nodes import extract_state_update
from app.api.streaming.tools import extract_tool_event_data, get_tool_to_node_map
from app.api.utils import extract_message_content

logger = structlog.get_logger(__name__)


async def process_async_stream_events(
    graph: "CompiledGraph",
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    org: str,
    project: str,
    accumulated_content_ref: dict[str, str] | None = None,
) -> AsyncIterator[str]:
    """
    Process astream_events() and yield SSE strings directly.
    
    This runs entirely in the FastAPI event loop, so checkpointer operations
    work natively without event loop synchronization issues.
    
    Args:
        graph: Compiled LangGraph instance
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        org: Organization name
        project: Project name
        accumulated_content_ref: Optional mutable dict to store accumulated content
                                (key: "content"). If provided, will be updated as chunks arrive.
        
    Yields:
        SSE-formatted strings (compatible with FastAPI StreamingResponse)
    """
    # Send graph_start event
    yield f"data: {json.dumps({'type': EVENT_GRAPH_START, 'thread_id': thread_id})}\n\n"
    
    accumulated_content = ""
    last_ai_message_content = ""
    visited_nodes: list[str] = []
    current_node: str | None = None
    
    # Track first token for TTFT
    first_token_recorded = False
    
    try:
        # Stream events directly from graph - runs in main event loop
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            if not isinstance(event, dict):
                continue
            
            event_type = event.get("event", "")
            
            # Handle content chunks from chat model stream
            if event_type == "on_chat_model_stream":
                # Track first token arrival for TTFT calculation
                if not first_token_recorded and not accumulated_content:
                    first_token_recorded = True
                    try:
                        from app.api.observability import record_first_token
                        run_id = event.get("run", {}).get("id", "")
                        record_first_token(thread_id, run_id=run_id if run_id else None)
                    except Exception:
                        # Don't fail if observability is not available
                        pass
                
                # Process content chunk
                chunk_data = _process_chat_model_stream_event(event, thread_id, accumulated_content)
                if chunk_data:
                    incremental_chunk, new_accumulated = chunk_data
                    accumulated_content = new_accumulated
                    last_ai_message_content = new_accumulated
                    
                    # Update accumulated content reference if provided
                    if accumulated_content_ref is not None:
                        accumulated_content_ref["content"] = new_accumulated
                    
                    # Yield content chunk event
                    chunk_event = {
                        "type": EVENT_CONTENT_CHUNK,
                        "content": incremental_chunk,
                        "accumulated": new_accumulated,
                        "thread_id": thread_id,
                    }
                    yield f"data: {json.dumps(chunk_event)}\n\n"
            
            # Handle LLM events
            elif event_type in ("on_llm_start", "on_chat_model_start"):
                llm_start_data = extract_llm_start_event(event, thread_id)
                if llm_start_data:
                    yield f"data: {json.dumps(llm_start_data)}\n\n"
            
            elif event_type in ("on_llm_end", "on_chat_model_end"):
                llm_end_data = extract_llm_end_event(event, thread_id)
                if llm_end_data:
                    yield f"data: {json.dumps(llm_end_data)}\n\n"
            
            # Handle tool events
            elif event_type in ("on_tool_start", "on_tool_end"):
                tool_events = _process_tool_event_async(
                    event, event_type, thread_id, visited_nodes, org, project
                )
                for tool_event in tool_events:
                    yield f"data: {json.dumps(tool_event)}\n\n"
            
            # Handle node events (chain start/end)
            elif event_type in ("on_chain_start", "on_chain_end"):
                node_events, current_node, visited_nodes = _process_node_event_async(
                    event, event_type, thread_id, current_node, visited_nodes
                )
                for node_event in node_events:
                    yield f"data: {json.dumps(node_event)}\n\n"
    
    except Exception as e:
        logger.exception(
            "async_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
            exc_info=True,
        )
        # Error event will be handled by caller
        raise
    
    # Send final state update
    try:
        final_state = graph.get_state(config)
        state_data = _extract_final_state_data(final_state, visited_nodes)
        if state_data:
            final_state_event = {
                "type": EVENT_STATE_UPDATE,
                "next": state_data["next_nodes"],
                "message_count": state_data["message_count"],
                "thread_id": thread_id,
                "visited_nodes": state_data["visited_nodes"],
            }
            yield f"data: {json.dumps(final_state_event)}\n\n"
    except Exception as e:
        logger.debug(
            "failed_to_get_final_state",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )


def _process_chat_model_stream_event(
    event: dict[str, Any],
    thread_id: str,
    accumulated_content: str,
) -> tuple[str, str] | None:
    """Process on_chat_model_stream event to extract incremental content chunks."""
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    chunk = data.get("chunk")
    if not chunk:
        return None
    
    # Extract incremental content from chunk
    # Skip tool_call_chunks - we only want content chunks
    incremental_chunk = ""
    
    if isinstance(chunk, dict):
        # Check if this is a tool call chunk (has tool_call_chunks but no content)
        if "tool_call_chunks" in chunk and not chunk.get("content"):
            return None
        
        if "content" in chunk:
            chunk_content = chunk.get("content", "")
            # Explicitly ignore empty content strings
            if not chunk_content:
                return None
            if isinstance(chunk_content, str):
                incremental_chunk = chunk_content
            elif isinstance(chunk_content, list):
                for block in chunk_content:
                    if isinstance(block, dict) and "text" in block:
                        incremental_chunk += block.get("text", "")
                    elif isinstance(block, str):
                        incremental_chunk += block
        elif "text" in chunk:
            text_content = chunk.get("text", "")
            if not text_content:
                return None
            incremental_chunk = str(text_content)
        elif "delta" in chunk:
            delta = chunk.get("delta", {})
            if isinstance(delta, dict) and "content" in delta:
                delta_content = delta.get("content", "")
                if not delta_content:
                    return None
                incremental_chunk = str(delta_content)
    elif hasattr(chunk, "content"):
        chunk_content = chunk.content
        # Explicitly ignore empty content
        if not chunk_content:
            return None
        if isinstance(chunk_content, str):
            incremental_chunk = chunk_content
        else:
            incremental_chunk = extract_message_content(chunk_content)
    elif hasattr(chunk, "text"):
        text_content = chunk.text
        if not text_content:
            return None
        incremental_chunk = str(text_content)
    elif hasattr(chunk, "delta"):
        delta = chunk.delta
        if hasattr(delta, "content"):
            delta_content = delta.content
            if not delta_content:
                return None
            incremental_chunk = extract_message_content(delta_content)
        elif isinstance(delta, dict):
            delta_content = delta.get("content", "")
            if not delta_content:
                return None
            incremental_chunk = str(delta_content)
    else:
        chunk_str = str(chunk)
        if not chunk_str:
            return None
        incremental_chunk = chunk_str
    
    # Final check: ensure we have non-empty content
    if not incremental_chunk:
        return None
    
    new_accumulated = accumulated_content + incremental_chunk
    return incremental_chunk, new_accumulated


def _process_tool_event_async(
    event: dict[str, Any],
    event_type: str,
    thread_id: str,
    visited_nodes: list[str],
    org: str,
    project: str,
) -> list[dict[str, Any]]:
    """Process tool events and return list of events to yield."""
    events = []
    tool_data = extract_tool_event_data(event, event_type)
    
    if not tool_data:
        return events
    
    tool_name = tool_data.get("tool_name", "unknown")
    tool_to_node_map = get_tool_to_node_map(org, project)
    tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
    
    # Track individual tool node
    if tool_node_name not in visited_nodes:
        visited_nodes.append(tool_node_name)
        
        # Emit node_start for the tool
        events.append({
            "type": EVENT_NODE_START,
            "node": tool_node_name,
            "thread_id": thread_id,
        })
        
        # Send state update with tool node as active
        events.append({
            "type": EVENT_STATE_UPDATE,
            "next": [tool_node_name],
            "message_count": 0,
            "thread_id": thread_id,
            "visited_nodes": visited_nodes.copy(),
        })
    
    # Emit tool_start or tool_end event
    tool_event = {
        "type": EVENT_TOOL_START if event_type == "on_tool_start" else EVENT_TOOL_END,
        "tool_name": tool_name,
        "args_preview": tool_data.get("args_preview", ""),
        "result_preview": tool_data.get("result_preview", "") if event_type == "on_tool_end" else "",
        "thread_id": thread_id,
    }
    events.append(tool_event)
    
    # Emit node_end when tool ends
    if event_type == "on_tool_end":
        events.append({
            "type": EVENT_NODE_END,
            "node": tool_node_name,
            "thread_id": thread_id,
        })
    
    return events


def _process_node_event_async(
    event: dict[str, Any],
    event_type: str,
    thread_id: str,
    current_node: str | None,
    visited_nodes: list[str],
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Process node events and return list of events to yield."""
    events = []
    node_name = event.get("name", "")
    
    if not node_name:
        return events, current_node, visited_nodes
    
    # Filter out internal LangGraph nodes and special nodes
    # Only process actual graph nodes (check metadata for langgraph_node)
    if event_type == "on_chain_start":
        # Skip internal nodes like __start__, __end__, and nested subgraph nodes
        if node_name in ("__start__", "__end__"):
            return events, current_node, visited_nodes
        
        # Check if this is a real graph node by looking at metadata
        metadata = event.get("metadata", {})
        langgraph_node = metadata.get("langgraph_node")
        
        # Only process if this matches the langgraph_node or if langgraph_node is not set
        # (some events don't have langgraph_node metadata, so we include those)
        if langgraph_node is not None and langgraph_node != node_name:
            # This is likely an internal chain/subgraph, skip it
            return events, current_node, visited_nodes
    
    # Handle chain start (node start)
    if event_type == "on_chain_start":
        if current_node != node_name:
            # End previous node if different
            if current_node:
                events.append({
                    "type": EVENT_NODE_END,
                    "node": current_node,
                    "thread_id": thread_id,
                })
            # Start new node
            current_node = node_name
            if node_name not in visited_nodes:
                visited_nodes.append(node_name)
            events.append({
                "type": EVENT_NODE_START,
                "node": node_name,
                "thread_id": thread_id,
            })
    
    # Handle chain end (node end + state update)
    elif event_type == "on_chain_end":
        if current_node == node_name:
            events.append({
                "type": EVENT_NODE_END,
                "node": node_name,
                "thread_id": thread_id,
            })
            current_node = None
        
        # Extract and send state update
        state_data = extract_state_update(event)
        if state_data:
            events.append({
                "type": EVENT_STATE_UPDATE,
                "next": state_data["next"],
                "message_count": state_data["message_count"],
                "thread_id": thread_id,
                "visited_nodes": visited_nodes.copy(),
            })
    
    return events, current_node, visited_nodes


def _extract_final_state_data(state: Any, visited_nodes: list[str]) -> dict[str, Any] | None:
    """Extract final state data including visited nodes, next nodes, and message count."""
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
