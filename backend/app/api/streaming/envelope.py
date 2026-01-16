"""
Event envelope and protocol definitions.

Defines the unified SSE protocol envelope structure and event type mappings.
"""
from __future__ import annotations

import time
from typing import Any

# Event type mapping from LangGraph events to our protocol
EVENT_TYPE_MAPPING: dict[str, str] = {
    "on_chain_start": "node_start",
    "on_chain_end": "node_end",
    "on_chat_model_start": "llm_start",
    "on_chat_model_end": "llm_end",
    "on_tool_start": "tool_start",
    "on_tool_end": "tool_end",
    "on_chat_model_stream": "content_chunk",
}


def create_event_envelope(
    event_type: str,
    thread_id: str,
    flow: str,
    seq: int,
    run_id: str | None = None,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a unified event envelope.
    
    Args:
        event_type: One of graph_start, graph_end, node_start, node_end, llm_start, llm_end, 
                   tool_start, tool_end, state_snapshot, error, keepalive
        thread_id: Thread identifier
        flow: Flow type ("chat" or "report")
        seq: Monotonic sequence number for this stream
        run_id: LangGraph run_id (when available)
        task_id: Task identifier (when available)
        payload: Event-specific payload data
        
    Returns:
        Event envelope dictionary
    """
    envelope: dict[str, Any] = {
        "type": event_type,
        "thread_id": thread_id,
        "ts": int(time.time() * 1000),  # Server timestamp in milliseconds
        "seq": seq,
        "flow": flow,
    }
    
    if run_id:
        envelope["run_id"] = run_id
    if task_id:
        envelope["task_id"] = task_id
    if payload:
        envelope["payload"] = payload
    
    return envelope
