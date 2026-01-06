"""
Utility functions for streaming operations.
"""
from __future__ import annotations

import json
from typing import Any



def truncate_preview(content: str, max_length: int = 200) -> str:
    """Truncate content to preview length."""
    if not content:
        return ""
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def extract_llm_event_data(event: dict[str, Any], event_type: str) -> dict[str, Any] | None:
    """Extract LLM call details from stream_events event.
    
    Args:
        event: Event dictionary from stream_events
        event_type: "on_llm_start" or "on_llm_end"
        
    Returns:
        Dictionary with LLM event data or None if not applicable
    """
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Extract model information
    model_name = data.get("name", "") or data.get("model_name", "") or "unknown"
    
    # Extract input (prompts/messages)
    input_data = data.get("input", {})
    input_preview = ""
    if isinstance(input_data, dict):
        # Try to extract messages or prompts
        messages = input_data.get("messages", input_data.get("prompts", []))
        if messages and isinstance(messages, list) and len(messages) > 0:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                content = last_msg.get("content", "")
            elif hasattr(last_msg, "content"):
                content = str(last_msg.content)
            else:
                content = str(last_msg)
            input_preview = truncate_preview(content, 200)
        else:
            input_preview = truncate_preview(str(input_data), 200)
    elif input_data:
        input_preview = truncate_preview(str(input_data), 200)
    
    # Extract output (only for on_llm_end)
    output_preview = ""
    token_usage = None
    if event_type == "on_llm_end":
        output_data = data.get("output", {})
        if isinstance(output_data, dict):
            content = output_data.get("content", "")
            if not content and "messages" in output_data:
                messages = output_data.get("messages", [])
                if messages and len(messages) > 0:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        content = last_msg.get("content", "")
                    elif hasattr(last_msg, "content"):
                        content = str(last_msg.content)
            output_preview = truncate_preview(content, 200)
        elif output_data:
            output_preview = truncate_preview(str(output_data), 200)
        
        # Extract token usage if available
        token_usage = data.get("token_usage") or data.get("usage_metadata")
        if not token_usage and "response_metadata" in data:
            metadata = data.get("response_metadata", {})
            token_usage = metadata.get("token_usage") or metadata.get("usage_metadata")
    
    return {
        "model": model_name,
        "input_preview": input_preview,
        "output_preview": output_preview if event_type == "on_llm_end" else "",
        "token_usage": token_usage if isinstance(token_usage, dict) else None,
    }


def extract_tool_event_data(event: dict[str, Any], event_type: str) -> dict[str, Any] | None:
    """Extract tool invocation details from stream_events event.
    
    Args:
        event: Event dictionary from stream_events
        event_type: "on_tool_start" or "on_tool_end"
        
    Returns:
        Dictionary with tool event data or None if not applicable
    """
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Extract tool name
    tool_name = data.get("name", "") or event.get("name", "") or "unknown"
    
    # Extract input (tool arguments)
    input_data = data.get("input", {})
    args_preview = ""
    if isinstance(input_data, dict):
        # Try to extract arguments
        args = input_data.get("input", input_data.get("args", input_data))
        if args:
            args_str = json.dumps(args) if not isinstance(args, str) else args
            args_preview = truncate_preview(args_str, 200)
        else:
            args_preview = truncate_preview(json.dumps(input_data), 200)
    elif input_data:
        args_str = json.dumps(input_data) if not isinstance(input_data, str) else str(input_data)
        args_preview = truncate_preview(args_str, 200)
    
    # Extract output (tool result, only for on_tool_end)
    result_preview = ""
    if event_type == "on_tool_end":
        output_data = data.get("output", {})
        if isinstance(output_data, dict):
            result_preview = truncate_preview(json.dumps(output_data), 500)
        elif output_data:
            result_str = json.dumps(output_data) if not isinstance(output_data, str) else str(output_data)
            result_preview = truncate_preview(result_str, 500)
    
    return {
        "tool_name": tool_name,
        "args_preview": args_preview,
        "result_preview": result_preview if event_type == "on_tool_end" else "",
    }


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
    
    from app.api.utils import extract_message_content
    
    if hasattr(state, "values") and "messages" in state.values:
        final_messages = state.values["messages"]
        for msg in reversed(final_messages):
            if not isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                return extract_message_content(msg.content)
    return None


def extract_incremental_content(
    current: str, previous: str, accumulated: str
) -> tuple[str, str]:
    """Extract incremental content from current message.
    
    Args:
        current: Current message content
        previous: Previous message content
        accumulated: Accumulated content so far
        
    Returns:
        Tuple of (incremental_content, new_accumulated)
    """
    if current.startswith(previous):
        # Content was appended
        incremental_content = current[len(previous):]
        new_accumulated = current
    else:
        # New message or content replaced
        incremental_content = current
        new_accumulated = current
    
    return incremental_content, new_accumulated

