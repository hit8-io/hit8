"""
LLM event extraction functions.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.api.constants import EVENT_LLM_END, EVENT_LLM_START
from app.api.streaming.constants import QUEUE_EVENT


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


def extract_llm_start_event(event: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    """Extract LLM start event data from astream_events() event.
    
    Returns:
        Event data dict or None if not an LLM start event
    """
    event_type = event.get("event", "")
    # LangGraph emits on_chat_model_start, not on_llm_start
    if event_type not in ("on_llm_start", "on_chat_model_start"):
        return None
    
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    model_name = data.get("name", "") or data.get("model_name", "") or "unknown"
    input_data = data.get("input", {})
    
    # Extract input preview
    input_preview = ""
    if isinstance(input_data, dict):
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
    
    # Extract model config from runnable config or metadata
    config = {}
    runnable_config = event.get("run", {}).get("tags", {})
    if "temperature" in runnable_config:
        config["temperature"] = runnable_config["temperature"]
    if "thinking_level" in runnable_config:
        config["thinking_level"] = runnable_config["thinking_level"]
    
    # Also check model_kwargs if available
    model_kwargs = data.get("kwargs", {}).get("model_kwargs", {})
    if "temperature" in model_kwargs and "temperature" not in config:
        config["temperature"] = model_kwargs["temperature"]
    if "thinking_level" in model_kwargs and "thinking_level" not in config:
        config["thinking_level"] = model_kwargs["thinking_level"]
    
    # Generate unique call ID for this LLM call
    call_id = str(uuid.uuid4())
    
    # Extract run_id from event for mapping stream events to this call
    run_id = event.get("run", {}).get("id", "")
    
    # Record LLM start for metrics tracking
    try:
        from app.api.observability import record_llm_start
        record_llm_start(thread_id, call_id, model_name, config if config else None, run_id if run_id else None)
    except Exception:
        # Don't fail if observability is not available
        pass
    
    return {
        "type": EVENT_LLM_START,
        "model": model_name,
        "input_preview": input_preview,
        "thread_id": thread_id,
        "call_id": call_id,  # Include call_id for tracking
    }


def extract_llm_end_event(event: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    """Extract LLM end event data from astream_events() event.
    
    Returns:
        Event data dict or None if not an LLM end event
    """
    event_type = event.get("event", "")
    # LangGraph emits on_chat_model_end, not on_llm_end
    if event_type not in ("on_llm_end", "on_chat_model_end"):
        return None
    
    llm_data = extract_llm_event_data(event, "on_llm_end")
    if not llm_data:
        return None
    
    model_name = llm_data.get("model", "unknown")
    token_usage = llm_data.get("token_usage")
    
    data = event.get("data", {})
    output = data.get("output")
    
    # Extract model name from output.response_metadata if model is still unknown
    if (not model_name or model_name == "unknown") and output:
        if hasattr(output, "response_metadata") and hasattr(output.response_metadata, "get"):
            model_name = output.response_metadata.get("model_name") or model_name
        elif isinstance(output, dict) and "response_metadata" in output:
            model_name = output.get("response_metadata", {}).get("model_name") or model_name
    
    # Extract model config
    config = {}
    runnable_config = event.get("run", {}).get("tags", {})
    if "temperature" in runnable_config:
        config["temperature"] = runnable_config["temperature"]
    if "thinking_level" in runnable_config:
        config["thinking_level"] = runnable_config["thinking_level"]
    
    data = event.get("data", {})
    model_kwargs = data.get("kwargs", {}).get("model_kwargs", {})
    if "temperature" in model_kwargs and "temperature" not in config:
        config["temperature"] = model_kwargs["temperature"]
    if "thinking_level" in model_kwargs and "thinking_level" not in config:
        config["thinking_level"] = model_kwargs["thinking_level"]
    
    # Get call_id from run_id mapping (created in start event)
    run_id = event.get("run", {}).get("id", "")
    call_id = None
    
    if run_id and thread_id:
        try:
            from app.api.observability import _run_id_to_call_id, _run_id_to_call_id_lock
            with _run_id_to_call_id_lock:
                if thread_id in _run_id_to_call_id and run_id in _run_id_to_call_id[thread_id]:
                    call_id = _run_id_to_call_id[thread_id][run_id]
        except Exception:
            pass
    
    # If no call_id found, try to use the most recent call_id for this thread
    # This handles cases where run_id mapping failed (e.g., run_id is empty)
    if not call_id:
        try:
            from app.api.observability import _llm_call_starts, _llm_call_starts_lock
            with _llm_call_starts_lock:
                if thread_id in _llm_call_starts and _llm_call_starts[thread_id]:
                    # Use the most recent call_id (last one in dict)
                    # This assumes events arrive in order, which should be true for streaming
                    call_id = list(_llm_call_starts[thread_id].keys())[-1]
        except Exception:
            pass
    
    # If still no call_id found, generate one (shouldn't happen in normal flow)
    if not call_id:
        call_id = str(uuid.uuid4())
    
    # Check output.usage_metadata first (LangChain AIMessage has usage_metadata directly)
    if not token_usage and output:
        # Priority 1: Check usage_metadata attribute directly (LangChain AIMessage)
        if hasattr(output, "usage_metadata"):
            try:
                usage_meta = output.usage_metadata
                if usage_meta:
                    token_usage = usage_meta
            except Exception:
                pass
        # Priority 2: Check response_metadata.get("token_usage") or response_metadata.get("usage_metadata")
        if not token_usage and hasattr(output, "response_metadata") and hasattr(output.response_metadata, "get"):
            token_usage_from_output = output.response_metadata.get("token_usage") or output.response_metadata.get("usage_metadata")
            if token_usage_from_output:
                token_usage = token_usage_from_output
        # Priority 3: Check if output is a dict with response_metadata
        if not token_usage and isinstance(output, dict) and "response_metadata" in output:
            token_usage_from_dict = output.get("response_metadata", {}).get("token_usage") or output.get("response_metadata", {}).get("usage_metadata")
            if token_usage_from_dict:
                token_usage = token_usage_from_dict
    
    # Extract token counts
    input_tokens = 0
    output_tokens = 0
    thinking_tokens = None
    
    if token_usage:
        # Handle different token usage formats
        if isinstance(token_usage, dict):
            # Standard format
            input_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
            output_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0))
            thinking_tokens = token_usage.get("thinking_tokens", token_usage.get("cached_tokens"))
            
            # Also check for total_tokens if individual counts missing
            if input_tokens == 0 and output_tokens == 0:
                total = token_usage.get("total_tokens", 0)
                # Estimate split (rough approximation)
                input_tokens = int(total * 0.6)
                output_tokens = total - input_tokens
        elif hasattr(token_usage, "prompt_tokens") or hasattr(token_usage, "input_tokens"):
            # TokenUsage object from LangChain
            input_tokens = getattr(token_usage, "prompt_tokens", 0) or getattr(token_usage, "input_tokens", 0)
            output_tokens = getattr(token_usage, "completion_tokens", 0) or getattr(token_usage, "output_tokens", 0)
            thinking_tokens = getattr(token_usage, "thinking_tokens", None)
    
    # Record LLM usage metrics
    current_metrics = None
    try:
        from app.api.observability import record_llm_usage, get_execution_metrics
        record_llm_usage(
            thread_id=thread_id,
            call_id=call_id,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            config=config if config else None,
        )
        # Get current metrics after recording to include in event
        # Metrics should exist after record_llm_usage() since initialize_execution() is called in chat.py
        current_metrics = get_execution_metrics(thread_id)
    except Exception as e:
        # Don't fail if observability is not available
        pass
    
    event_data = {
        "type": EVENT_LLM_END,
        "model": model_name,
        "input_preview": llm_data.get("input_preview", ""),
        "output_preview": llm_data.get("output_preview", ""),
        "thread_id": thread_id,
    }
    
    # Add token usage if available
    if token_usage:
        event_data["token_usage"] = token_usage
    
    # Include current execution metrics in the event (pushed through stream, no polling needed)
    # model_dump() serializes Pydantic model to dict (as used in observability.py endpoint)
    if current_metrics:
        event_data["execution_metrics"] = current_metrics.model_dump(mode='json')
    
    return event_data
