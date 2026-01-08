"""
Event queue processing functions.
"""
from __future__ import annotations

import asyncio
import queue
from typing import Any

from app.api.streaming.constants import QUEUE_CHUNK, QUEUE_EVENT
from app.api.streaming.llm import extract_llm_end_event, extract_llm_start_event
from app.api.streaming.nodes import process_node_event
from app.api.streaming.tools import process_tool_event
from app.api.utils import extract_message_content


def process_chat_model_stream_event(
    event: dict[str, Any],
    event_queue: queue.Queue,
    thread_id: str,
    accumulated_content: str,
    last_ai_message_content: str,
) -> tuple[str, str] | None:
    """Process on_chat_model_stream event to extract incremental content chunks.
    
    Each on_chat_model_stream event contains a delta/chunk that should be appended
    to the accumulated content.
    
    Args:
        event: Event dictionary from astream_events
        event_queue: Queue to emit content chunk events
        thread_id: Thread identifier
        accumulated_content: Currently accumulated content
        last_ai_message_content: Last known AI message content (for comparison)
        
    Returns:
        Updated (accumulated_content, last_ai_message_content) if content changed, None otherwise
    """
    from app.api.constants import EVENT_CONTENT_CHUNK
    
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Extract chunk/delta from event data
    # LangGraph v2 on_chat_model_stream events have chunk in data.chunk
    chunk = data.get("chunk")
    if not chunk:
        return None
    
    # Extract incremental content from chunk
    # Chunk can be a message delta or dict with content/text
    incremental_chunk = ""
    if isinstance(chunk, dict):
        # Try different possible content locations in delta
        if "content" in chunk:
            chunk_content = chunk.get("content", "")
            if isinstance(chunk_content, str):
                incremental_chunk = chunk_content
            elif isinstance(chunk_content, list):
                # Content might be a list of content blocks
                for block in chunk_content:
                    if isinstance(block, dict) and "text" in block:
                        incremental_chunk += block.get("text", "")
                    elif isinstance(block, str):
                        incremental_chunk += block
        elif "text" in chunk:
            incremental_chunk = str(chunk.get("text", ""))
        elif "delta" in chunk:
            # Some formats have delta nested
            delta = chunk.get("delta", {})
            if isinstance(delta, dict) and "content" in delta:
                incremental_chunk = str(delta.get("content", ""))
    elif hasattr(chunk, "content"):
        chunk_content = chunk.content
        if isinstance(chunk_content, str):
            incremental_chunk = chunk_content
        else:
            incremental_chunk = extract_message_content(chunk_content)
    elif hasattr(chunk, "text"):
        incremental_chunk = str(chunk.text)
    elif hasattr(chunk, "delta"):
        delta = chunk.delta
        if hasattr(delta, "content"):
            incremental_chunk = extract_message_content(delta.content)
        elif isinstance(delta, dict):
            incremental_chunk = str(delta.get("content", ""))
    else:
        # Fallback: convert to string
        incremental_chunk = str(chunk)
    
    if not incremental_chunk:
        return None
    
    # Append incremental chunk to accumulated content
    new_accumulated = accumulated_content + incremental_chunk
    
    # Emit content chunk event
    event_queue.put((QUEUE_CHUNK, {
        "type": EVENT_CONTENT_CHUNK,
        "content": incremental_chunk,
        "accumulated": new_accumulated,
        "thread_id": thread_id,
    }))
    
    # Update last_ai_message_content to match new accumulated
    return new_accumulated, new_accumulated


def process_events_queue(
    events_queue: asyncio.Queue,
    event_queue: queue.Queue,
    thread_id: str,
    accumulated_content: str,
    last_ai_message_content: str,
    current_node: str | None,
    visited_nodes: list[str],
    org: str,
    project: str,
) -> tuple[str, str, str | None, list[str]] | None:
    """Process events from the events queue.
    
    Handles all event types from astream_events v2:
    - on_chat_model_stream: content chunks
    - on_llm_start: LLM start event
    - on_llm_end: LLM end event with token usage
    - on_chain_start: node start
    - on_chain_end: node end + state update
    - on_tool_start: tool start
    - on_tool_end: tool end
    
    Returns:
        Updated (accumulated_content, last_ai_message_content, current_node, visited_nodes) if changed, None otherwise
    """
    content_updated = False
    while True:
        try:
            event = events_queue.get_nowait()
            if not isinstance(event, dict):
                continue
                
            event_type = event.get("event", "")
            
            # Handle content chunks from chat model stream
            if event_type == "on_chat_model_stream":
                # Track first token arrival for TTFT calculation
                if not accumulated_content:  # This is the first chunk
                    try:
                        from app.api.observability import record_first_token
                        run_id = event.get("run", {}).get("id", "")
                        record_first_token(thread_id, run_id=run_id if run_id else None)
                    except Exception:
                        # Don't fail if observability is not available
                        pass
                
                result = process_chat_model_stream_event(
                    event, event_queue, thread_id,
                    accumulated_content, last_ai_message_content
                )
                if result:
                    accumulated_content, last_ai_message_content = result
                    content_updated = True
            
            # Handle LLM events
            # LangGraph emits on_chat_model_start/on_chat_model_end, not on_llm_start/on_llm_end
            elif event_type in ("on_llm_start", "on_chat_model_start"):
                llm_start_data = extract_llm_start_event(event, thread_id)
                if llm_start_data:
                    event_queue.put((QUEUE_EVENT, llm_start_data))
            
            elif event_type in ("on_llm_end", "on_chat_model_end"):
                llm_end_data = extract_llm_end_event(event, thread_id)
                if llm_end_data:
                    event_queue.put((QUEUE_EVENT, llm_end_data))
            
            # Handle tool events
            elif event_type in ("on_tool_start", "on_tool_end"):
                visited_nodes = process_tool_event(
                    event, event_queue, thread_id, visited_nodes, org, project
                )
            
            # Handle node events (chain start/end)
            elif event_type in ("on_chain_start", "on_chain_end"):
                current_node, visited_nodes = process_node_event(
                    event, event_queue, thread_id, current_node, visited_nodes
                )
                
        except asyncio.QueueEmpty:
            break
    
    # Return updated state if content was updated
    if content_updated:
        return accumulated_content, last_ai_message_content, current_node, visited_nodes
    return None
