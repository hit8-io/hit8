"""
Chat endpoint with streaming support.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import structlog

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.agents.common import get_langfuse_handler
from app.agents.opgroeien.constants import NODE_AGENT, NODE_TOOLS
from app.agents.opgroeien.graph import AgentState
from app.api.constants import (
    EVENT_CONTENT_CHUNK,
    EVENT_GRAPH_END,
    EVENT_GRAPH_START,
    EVENT_LLM_END,
    EVENT_LLM_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_STATE_UPDATE,
    EVENT_TOOL_END,
    EVENT_TOOL_START,
    EVENT_ERROR,
    QUEUE_CHUNK,
    QUEUE_ERROR,
    QUEUE_EVENT,
)
from app.api.graph_manager import get_graph
from app.api.models import ChatRequest
from app.api.utils import extract_ai_message, extract_message_content
from app.config import get_metadata, settings
from app.deps import verify_google_token

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler

logger = structlog.get_logger(__name__)
router = APIRouter()


class EventCaptureCallbackHandler(BaseCallbackHandler):
    """Callback handler to capture LLM and tool events for real-time streaming."""
    
    def __init__(self, event_queue: queue.Queue, thread_id: str):
        super().__init__()
        self.event_queue = event_queue
        self.thread_id = thread_id
        # Store prompts and model name from on_llm_start to use in on_llm_end
        self._llm_prompts: dict[str, list[str]] = {}  # run_id -> prompts
        self._llm_model_names: dict[str, str] = {}  # run_id -> model_name
    
    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Capture LLM start event."""
        try:
            # Extract model name from invocation_params (most reliable source)
            model_name = "unknown"
            if "invocation_params" in kwargs:
                inv_params = kwargs["invocation_params"]
                if isinstance(inv_params, dict):
                    # Try various keys for model name
                    model_name = (
                        inv_params.get("model_name") or
                        inv_params.get("model") or
                        inv_params.get("model_id") or
                        model_name
                    )
            
            # Fallback to serialized config if invocation_params didn't have it
            if model_name == "unknown":
                if isinstance(serialized.get("id"), list) and serialized.get("id"):
                    # serialized.id is like ['langchain_google_genai', 'chat_models', 'ChatGoogleGenerativeAI']
                    # We want the actual model, not the class name
                    pass  # Skip this, it's just the class name
                elif serialized.get("name"):
                    model_name = serialized["name"]
                elif serialized.get("_type"):
                    model_name = serialized["_type"]
            
            # Store prompts and model name for use in on_llm_end
            run_id = kwargs.get("run_id", "")
            if run_id:
                if prompts:
                    self._llm_prompts[str(run_id)] = prompts
                if model_name != "unknown":
                    self._llm_model_names[str(run_id)] = model_name
            
            # Extract input preview from prompts
            input_preview = ""
            if prompts:
                # Join all prompts if multiple, otherwise use first
                if len(prompts) == 1:
                    input_preview = _truncate_preview(prompts[0], 300)
                else:
                    input_preview = _truncate_preview(f"[{len(prompts)} prompts]", 300)
            
            self.event_queue.put((QUEUE_EVENT, {
                "type": EVENT_LLM_START,
                "model": model_name,
                "input_preview": input_preview,
                "thread_id": self.thread_id,
            }))
        except Exception as e:
            logger.error("callback_llm_start_error", error=str(e), thread_id=self.thread_id, exc_info=True)
    
    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Capture LLM end event."""
        try:
            # Extract model name from stored value (from on_llm_start)
            model_name = "unknown"
            run_id = kwargs.get("run_id", "")
            if run_id and str(run_id) in self._llm_model_names:
                model_name = self._llm_model_names[str(run_id)]
                # Clean up stored model name
                del self._llm_model_names[str(run_id)]
            
            # Fallback: try invocation_params if not stored (shouldn't happen, but safety)
            if model_name == "unknown" and "invocation_params" in kwargs:
                inv_params = kwargs["invocation_params"]
                if isinstance(inv_params, dict):
                    model_name = (
                        inv_params.get("model_name") or
                        inv_params.get("model") or
                        inv_params.get("model_id") or
                        model_name
                    )
            
            # Extract input preview from stored prompts (from on_llm_start)
            input_preview = ""
            if run_id and str(run_id) in self._llm_prompts:
                prompts = self._llm_prompts[str(run_id)]
                if prompts and isinstance(prompts, list):
                    if len(prompts) == 1:
                        input_preview = _truncate_preview(prompts[0], 300)
                    else:
                        input_preview = _truncate_preview(f"[{len(prompts)} prompts]", 300)
                # Clean up stored prompts
                del self._llm_prompts[str(run_id)]
            
            # Extract output preview, token usage and tool calls from LLMResult
            output_preview = ""
            token_usage = None
            tool_calls = []
            
            if isinstance(response, LLMResult):
                # LLMResult has generations: list[list[Generation]]
                if response.generations and len(response.generations) > 0:
                    # Get first generation from first prompt
                    first_gen_list = response.generations[0]
                    if first_gen_list and len(first_gen_list) > 0:
                        first_gen = first_gen_list[0]
                        # Extract output preview and tool calls from message if available
                        if hasattr(first_gen, "message"):
                            msg = first_gen.message
                            # Extract output preview from message content
                            if hasattr(msg, "content"):
                                content = msg.content
                                if isinstance(content, str):
                                    output_preview = _truncate_preview(content, 500)
                                elif isinstance(content, list):
                                    # Content might be a list of content blocks (e.g., [{"type": "text", "text": "..."}])
                                    text_parts = []
                                    for block in content:
                                        if isinstance(block, dict):
                                            # Try various keys for text content
                                            text = (
                                                block.get("text") or
                                                block.get("content") or
                                                (str(block) if block else "")
                                            )
                                            if text:
                                                text_parts.append(str(text))
                                        elif isinstance(block, str):
                                            text_parts.append(block)
                                        else:
                                            # Fallback: convert to string
                                            text_parts.append(str(block))
                                    if text_parts:
                                        output_preview = _truncate_preview(" ".join(text_parts), 500)
                                else:
                                    output_preview = _truncate_preview(str(content), 500)
                            # Extract tool calls from message
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
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
                                    tool_calls.append(tool_call_dict)
                        # Fallback: try to extract text from generation
                        elif hasattr(first_gen, "text") and first_gen.text:
                            output_preview = _truncate_preview(first_gen.text, 500)
                
                # Extract token usage from llm_output
                if response.llm_output:
                    if isinstance(response.llm_output, dict):
                        token_usage = response.llm_output.get("token_usage") or response.llm_output.get("usage_metadata")
                        # Also check for model name in llm_output
                        if model_name == "unknown":
                            model_name = response.llm_output.get("model_name") or model_name
            elif hasattr(response, "content"):
                # Direct message-like object (AIMessage)
                output_preview = _truncate_preview(str(response.content), 500)
                if hasattr(response, "response_metadata"):
                    metadata = response.response_metadata or {}
                    token_usage = metadata.get("token_usage") or metadata.get("usage_metadata")
                    if model_name == "unknown":
                        model_name = metadata.get("model_name", model_name)
            elif hasattr(response, "text"):
                # Simple text response
                output_preview = _truncate_preview(str(response.text), 500)
            
            event_data = {
                "type": EVENT_LLM_END,
                "model": model_name,
                "input_preview": input_preview,
                "output_preview": output_preview,
                "thread_id": self.thread_id,
            }
            if token_usage:
                event_data["token_usage"] = token_usage
            if tool_calls:
                event_data["tool_calls"] = tool_calls
            
            self.event_queue.put((QUEUE_EVENT, event_data))
        except Exception as e:
            logger.error("callback_llm_end_error", error=str(e), thread_id=self.thread_id, exc_info=True)
    
    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Capture tool start event."""
        try:
            tool_name = serialized.get("name", "unknown")
            args_preview = _truncate_preview(input_str, 200)
            
            self.event_queue.put((QUEUE_EVENT, {
                "type": EVENT_TOOL_START,
                "tool_name": tool_name,
                "args_preview": args_preview,
                "thread_id": self.thread_id,
            }))
        except Exception as e:
            logger.error("callback_tool_start_error", error=str(e), thread_id=self.thread_id)
    
    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Capture tool end event."""
        try:
            tool_name = kwargs.get("name", "unknown")
            args_preview = _truncate_preview(str(kwargs.get("input", "")), 200)
            result_preview = _truncate_preview(str(output), 500)
            
            self.event_queue.put((QUEUE_EVENT, {
                "type": EVENT_TOOL_END,
                "tool_name": tool_name,
                "args_preview": args_preview,
                "result_preview": result_preview,
                "thread_id": self.thread_id,
            }))
        except Exception as e:
            logger.error("callback_tool_end_error", error=str(e), thread_id=self.thread_id)


def _truncate_preview(content: str, max_length: int = 200) -> str:
    """Truncate content to preview length."""
    if not content:
        return ""
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def _extract_llm_event_data(event: dict[str, Any], event_type: str) -> dict[str, Any] | None:
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
            input_preview = _truncate_preview(content, 200)
        else:
            input_preview = _truncate_preview(str(input_data), 200)
    elif input_data:
        input_preview = _truncate_preview(str(input_data), 200)
    
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
            output_preview = _truncate_preview(content, 200)
        elif output_data:
            output_preview = _truncate_preview(str(output_data), 200)
        
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


def _extract_tool_event_data(event: dict[str, Any], event_type: str) -> dict[str, Any] | None:
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
            args_preview = _truncate_preview(args_str, 200)
        else:
            args_preview = _truncate_preview(json.dumps(input_data), 200)
    elif input_data:
        args_str = json.dumps(input_data) if not isinstance(input_data, str) else str(input_data)
        args_preview = _truncate_preview(args_str, 200)
    
    # Extract output (tool result, only for on_tool_end)
    result_preview = ""
    if event_type == "on_tool_end":
        output_data = data.get("output", {})
        if isinstance(output_data, dict):
            result_preview = _truncate_preview(json.dumps(output_data), 500)
        elif output_data:
            result_str = json.dumps(output_data) if not isinstance(output_data, str) else str(output_data)
            result_preview = _truncate_preview(result_str, 500)
    
    return {
        "tool_name": tool_name,
        "args_preview": args_preview,
        "result_preview": result_preview if event_type == "on_tool_end" else "",
    }


def _extract_state_update(event: dict[str, Any]) -> dict[str, Any] | None:
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


def _run_content_stream(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    content_done: threading.Event,
    content_error: list[Exception | None],
) -> None:
    """Run stream() in a thread to extract content chunks from state updates.
    
    Args:
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        event_queue: Queue for events and chunks
        content_done: Event to signal content stream completion
        content_error: List to store any errors
    """
    try:
        previous_messages: list[Any] = initial_state.get("messages", [])
        previous_message_count = len(previous_messages)
        accumulated_content = ""
        
        logger.info(
            "content_stream_started",
            thread_id=thread_id,
            initial_message_count=previous_message_count,
            initial_state_keys=list(initial_state.keys()) if isinstance(initial_state, dict) else [],
        )
        
        # Use stream() which yields (node_name, state) tuples
        last_ai_message_content = ""
        try:
            logger.info("creating_stream_iterator", thread_id=thread_id, config_keys=list(config.keys()))
            stream_iter = get_graph().stream(initial_state, config=config)
            logger.info("stream_iterator_created", thread_id=thread_id, stream_type=type(stream_iter).__name__)
        except Exception as e:
            logger.exception("failed_to_create_stream", error=str(e), thread_id=thread_id, exc_info=True)
            raise
        
        stream_count = 0
        try:
            for stream_item in stream_iter:
                stream_count += 1
                logger.debug("stream_item_received", thread_id=thread_id, item_count=stream_count, item_type=type(stream_item).__name__)
                
                # stream() yields state dictionaries directly (not tuples)
                # Format: {"messages": [...], ...} - the full state after each node execution
                if isinstance(stream_item, dict):
                    state_update = stream_item
                    node_name = None  # We don't get node name from stream(), only from stream_events()
                elif isinstance(stream_item, tuple) and len(stream_item) == 2:
                    # Fallback: handle tuple format if it ever changes
                    node_name, state_update = stream_item
                else:
                    logger.debug(
                        "unexpected_stream_item_format",
                        thread_id=thread_id,
                        item_type=type(stream_item).__name__,
                    )
                    continue
                
                # Handle state updates that might not have messages (e.g., tools node execution)
                # ToolNode might return intermediate states with only 'tools' key
                # We should continue to wait for the next state update that has messages
                if not isinstance(state_update, dict):
                    logger.debug(
                        "state_update_not_dict",
                        thread_id=thread_id,
                        item_type=type(state_update).__name__,
                    )
                    continue
                
                # Send state update event for real-time updates
                messages = state_update.get("messages", [])
                message_count = len(messages) if isinstance(messages, list) else 0
                # Extract next nodes from state (if available)
                next_nodes = []
                # Note: stream() doesn't provide next nodes directly, but we can infer from execution
                
                if message_count > 0:
                    event_queue.put((QUEUE_EVENT, {
                        "type": EVENT_STATE_UPDATE,
                        "next": next_nodes,  # Will be updated by node tracking if available
                        "message_count": message_count,
                        "thread_id": thread_id,
                    }))
                
                # If state has 'tools' key but no 'messages', it's likely a tools node execution
                # The final state will have messages after tools complete
                if "messages" not in state_update:
                    if "tools" in state_update:
                        logger.debug(
                            "tools_node_executing",
                            thread_id=thread_id,
                            keys=list(state_update.keys()),
                        )
                    else:
                        logger.debug(
                            "state_update_missing_messages",
                            thread_id=thread_id,
                            keys=list(state_update.keys()),
                        )
                    continue
                
                current_messages = state_update["messages"]
                current_message_count = len(current_messages)
                
                logger.debug(
                    "stream_state_update",
                    thread_id=thread_id,
                    node_name=node_name,
                    message_count=current_message_count,
                    previous_count=previous_message_count,
                )
                
                # Find the last AI message (non-HumanMessage)
                last_ai_message = None
                for msg in reversed(current_messages):
                    if not isinstance(msg, HumanMessage):
                        last_ai_message = msg
                        break                
                if last_ai_message and hasattr(last_ai_message, "content"):
                    current_content = extract_message_content(last_ai_message.content)                    
                    # Check if content has changed (new message or content update)
                    if current_content != last_ai_message_content:
                        # Calculate incremental content
                        if current_content.startswith(last_ai_message_content):
                            # Content was appended
                            incremental_content = current_content[len(last_ai_message_content):]
                        else:
                            # New message or content replaced
                            incremental_content = current_content
                            accumulated_content = ""
                        
                        if incremental_content:
                            accumulated_content = current_content
                            last_ai_message_content = current_content
                            
                            # Queue content chunk for frontend
                            event_queue.put((QUEUE_CHUNK, {
                                "type": EVENT_CONTENT_CHUNK,
                                "content": incremental_content,
                                "accumulated": accumulated_content,
                                "thread_id": thread_id,
                            }))
                            
                            logger.info(
                                "content_chunk_sent",
                                thread_id=thread_id,
                                chunk_length=len(incremental_content),
                                accumulated_length=len(accumulated_content),
                                node_name=node_name,
                            )
                
                # Update previous state for next iteration
                previous_messages = current_messages
                previous_message_count = current_message_count
        except StopIteration:
            logger.info("stream_stopped_iteration", thread_id=thread_id, total_items=stream_count)
        except Exception as e:
            logger.exception("stream_iteration_error", error=str(e), thread_id=thread_id, item_count=stream_count, exc_info=True)
            raise
        
        logger.info(
            "stream_iteration_completed",
            thread_id=thread_id,
            total_stream_items=stream_count,
            final_message_count=previous_message_count,
        )
        
        # After stream completes, check if we have any final content
        # Get the last state to extract final message if we haven't already
        if not accumulated_content and not last_ai_message_content:
            try:
                final_state = get_graph().get_state(config)
                if hasattr(final_state, "values") and "messages" in final_state.values:
                    final_messages = final_state.values["messages"]
                    for msg in reversed(final_messages):
                        if not isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                            last_ai_message_content = extract_message_content(msg.content)
                            break
            except Exception as e:
                logger.warning(
                    "failed_to_get_final_state_for_content",
                    error=str(e),
                    thread_id=thread_id,
                )
        
        # Store final accumulated content for final response extraction
        # Use last_ai_message_content if accumulated_content is empty (in case we missed updates)
        final_content = accumulated_content or last_ai_message_content
        if final_content:
            # If we never sent any chunks, send the full content now
            if not accumulated_content:
                event_queue.put((QUEUE_CHUNK, {
                    "type": EVENT_CONTENT_CHUNK,
                    "content": final_content,
                    "accumulated": final_content,
                    "thread_id": thread_id,
                }))
                logger.info(
                    "full_content_sent_on_completion",
                    thread_id=thread_id,
                    content_length=len(final_content),
                )
            
            event_queue.put((QUEUE_CHUNK, {
                "__final_content__": True,
                "content": final_content,
            }))
            
            logger.info(
                "content_stream_completed",
                thread_id=thread_id,
                final_content_length=len(final_content),
                had_incremental_chunks=bool(accumulated_content),
            )
        else:
            logger.warning(
                "content_stream_completed_no_content",
                thread_id=thread_id,
                message_count=previous_message_count,
            )
            
    except Exception as e:
        content_error[0] = e
        event_queue.put((QUEUE_ERROR, e))
        logger.exception(
            "content_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
            exc_info=True,
        )
        import traceback
        logger.error(
            "content_stream_traceback",
            traceback=traceback.format_exc(),
            thread_id=thread_id,
        )
    finally:
        logger.info("content_stream_finally", thread_id=thread_id)
        content_done.set()

def _run_node_tracking_stream(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    node_done: threading.Event,
    node_error: list[Exception | None],
) -> None:
    """Run stream_events() in a thread to track node execution events.
    
    Args:
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        event_queue: Queue for events and chunks
        node_done: Event to signal node tracking completion
        node_error: List to store any errors
    """
    try:
        current_node: str | None = None
        seen_nodes: set[str] = set()
        
        logger.debug(
            "node_tracking_started",
            thread_id=thread_id,
        )
        
        # Use stream_events() to get node-level execution events
        graph = get_graph()
        
        # Try to get stream_events method - it might be available but not detected by hasattr
        stream_events_method = getattr(graph, "stream_events", None)
        if stream_events_method is None:
            logger.warning(
                "node_tracking_not_available",
                thread_id=thread_id,
                graph_type=type(graph).__name__,
            )
            return
        
        event_count = 0
        # Use the method we found (should be stream_events)
        for event in stream_events_method(initial_state, config=config, version="v2"):
            event_count += 1
            if not isinstance(event, dict):
                continue
            
            # Extract event type and node name
            event_type = event.get("event", "")
            node_name = event.get("name", "")
            
            # Handle LLM call events
            if event_type == "on_llm_start":
                llm_data = _extract_llm_event_data(event, "on_llm_start")
                if llm_data:
                    event_queue.put((QUEUE_EVENT, {
                        "type": EVENT_LLM_START,
                        "model": llm_data["model"],
                        "input_preview": llm_data["input_preview"],
                        "thread_id": thread_id,
                    }))
                    logger.debug(
                        "llm_start_event",
                        thread_id=thread_id,
                        model=llm_data["model"],
                    )
            
            elif event_type == "on_llm_end":
                llm_data = _extract_llm_event_data(event, "on_llm_end")
                if llm_data:
                    event_data = {
                        "type": EVENT_LLM_END,
                        "model": llm_data["model"],
                        "input_preview": llm_data["input_preview"],
                        "output_preview": llm_data["output_preview"],
                        "thread_id": thread_id,
                    }
                    if llm_data["token_usage"]:
                        event_data["token_usage"] = llm_data["token_usage"]
                    event_queue.put((QUEUE_EVENT, event_data))
                    logger.debug(
                        "llm_end_event",
                        thread_id=thread_id,
                        model=llm_data["model"],
                        has_token_usage=bool(llm_data["token_usage"]),
                    )
            
            # Handle tool invocation events
            elif event_type == "on_tool_start":
                tool_data = _extract_tool_event_data(event, "on_tool_start")
                if tool_data:
                    event_queue.put((QUEUE_EVENT, {
                        "type": EVENT_TOOL_START,
                        "tool_name": tool_data["tool_name"],
                        "args_preview": tool_data["args_preview"],
                        "thread_id": thread_id,
                    }))
                    logger.debug(
                        "tool_start_event",
                        thread_id=thread_id,
                        tool_name=tool_data["tool_name"],
                    )
            
            elif event_type == "on_tool_end":
                tool_data = _extract_tool_event_data(event, "on_tool_end")
                if tool_data:
                    event_queue.put((QUEUE_EVENT, {
                        "type": EVENT_TOOL_END,
                        "tool_name": tool_data["tool_name"],
                        "args_preview": tool_data["args_preview"],
                        "result_preview": tool_data["result_preview"],
                        "thread_id": thread_id,
                    }))
                    logger.debug(
                        "tool_end_event",
                        thread_id=thread_id,
                        tool_name=tool_data["tool_name"],
                    )
            
            # Handle state update events (from on_chain_stream or on_chain_end)
            # Extract state from both on_chain_stream (intermediate) and on_chain_end (final)
            if event_type in ("on_chain_stream", "on_chain_end"):
                state_data = _extract_state_update(event)
                if state_data:
                    event_queue.put((QUEUE_EVENT, {
                        "type": EVENT_STATE_UPDATE,
                        "next": state_data["next"],
                        "message_count": state_data["message_count"],
                        "thread_id": thread_id,
                    }))
                    logger.debug(
                        "state_update_event",
                        thread_id=thread_id,
                        event_type=event_type,
                        next_nodes=state_data["next"],
                        message_count=state_data["message_count"],
                    )
            
            # Handle node execution start events
            if event_type == "on_chain_start":
                if node_name in (NODE_AGENT, NODE_TOOLS):
                    if current_node != node_name:
                        # End previous node if any
                        if current_node:
                            event_queue.put((QUEUE_EVENT, {
                                "type": EVENT_NODE_END,
                                "node": current_node,
                                "thread_id": thread_id
                            }))
                        # Start new node
                        current_node = node_name
                        seen_nodes.add(node_name)
                        event_queue.put((QUEUE_EVENT, {
                            "type": EVENT_NODE_START,
                            "node": node_name,
                            "thread_id": thread_id
                        }))
                        
                        logger.debug(
                            "node_started",
                            thread_id=thread_id,
                            node=node_name,
                        )
            
            # Handle node execution end events
            elif event_type == "on_chain_end":
                if node_name in (NODE_AGENT, NODE_TOOLS):
                    if current_node == node_name:
                        event_queue.put((QUEUE_EVENT, {
                            "type": EVENT_NODE_END,
                            "node": node_name,
                            "thread_id": thread_id
                        }))
                        current_node = None
                        
                        logger.debug(
                            "node_ended",
                            thread_id=thread_id,
                            node=node_name,
                        )
                    seen_nodes.discard(node_name)
        
        # End any remaining active node
        if current_node:
            event_queue.put((QUEUE_EVENT, {
                "type": EVENT_NODE_END,
                "node": current_node,
                "thread_id": thread_id
            }))
            
            logger.debug(
                "node_ended_final",
                thread_id=thread_id,
                node=current_node,
            )
        
        logger.debug(
            "node_tracking_completed",
            thread_id=thread_id,
            seen_nodes=list(seen_nodes),
        )
            
    except Exception as e:
        node_error[0] = e
        event_queue.put((QUEUE_ERROR, e))
        logger.exception(
            "node_tracking_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )
    finally:
        node_done.set()


def _create_stream_thread(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
) -> tuple[list[threading.Thread], list[Exception | None]]:
    """Create and start dual threads for streaming: content and node tracking.
    
    Args:
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        event_queue: Queue for events and chunks
        stream_done: Event to signal stream completion
        
    Returns:
        Tuple of (list of threads, list with error slots for content and node tracking)
    """
    # Send graph start event
    event_queue.put((QUEUE_EVENT, {"type": EVENT_GRAPH_START, "thread_id": thread_id}))
    
    # Create event capture callback handler for LLM and tool events
    # This works even when stream_events is not available on the graph
    event_callback = EventCaptureCallbackHandler(event_queue, thread_id)
    
    # Add event callback to config callbacks (create list if needed)
    if "callbacks" not in config:
        config["callbacks"] = []
    if not isinstance(config["callbacks"], list):
        config["callbacks"] = [config["callbacks"]]
    config["callbacks"].append(event_callback)
    
    # Error tracking for both threads
    content_error: list[Exception | None] = [None]
    node_error: list[Exception | None] = [None]
    stream_errors = [content_error, node_error]
    
    # Completion events for both threads
    content_done = threading.Event()
    node_done = threading.Event()
    
    # Create and start content streaming thread
    content_thread = threading.Thread(
        target=_run_content_stream,
        args=(initial_state, config, thread_id, event_queue, content_done, content_error),
        daemon=True,
    )
    content_thread.start()
    
    # Create and start node tracking thread (may not work if stream_events unavailable, but try anyway)
    node_thread = threading.Thread(
        target=_run_node_tracking_stream,
        args=(initial_state, config, thread_id, event_queue, node_done, node_error),
        daemon=True,
    )
    node_thread.start()
    
    # Monitor both threads and signal stream_done when both complete
    def monitor_threads():
        """Wait for both threads to complete, then signal stream_done."""
        content_result = content_thread.join(timeout=30.0)
        node_result = node_thread.join(timeout=30.0)
        stream_done.set()
        
        logger.debug(
            "stream_threads_completed",
            thread_id=thread_id,
            content_completed=content_done.is_set(),
            node_completed=node_done.is_set(),
        )
    
    monitor_thread = threading.Thread(target=monitor_threads, daemon=True)
    monitor_thread.start()
    
    return [content_thread, node_thread, monitor_thread], stream_errors


async def _process_stream_queue(
    event_queue: queue.Queue,
    stream_done: threading.Event,
    final_response_ref: list[str | None],
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    """Process events and chunks from the stream queue.
    
    Args:
        event_queue: Queue containing events and chunks
        stream_done: Event signaling stream completion
        final_response_ref: List to store extracted final response
        
    Yields:
        Server-Sent Event strings
    """
    iteration_count = 0
    # Fix: Change condition to exit when stream_done is set AND queue is empty
    # Old: while not stream_done.is_set() or not event_queue.empty():
    # This continues if EITHER condition is true, causing infinite loop
    # New: Continue while stream is not done OR queue has items
    while True:
        # Check exit condition: stream done AND queue empty
        stream_done_state = stream_done.is_set()
        queue_empty = event_queue.empty()
        if stream_done_state and queue_empty:
            break
        iteration_count += 1
        
        try:
            # Wait for event/chunk with timeout
            item = event_queue.get(timeout=0.1)
            item_type, item_data = item
            
            if item_type == QUEUE_ERROR:
                # Log error and send error event to frontend
                error_obj = item_data
                error_message = str(error_obj) if error_obj else "Unknown error occurred"
                error_type = type(error_obj).__name__ if error_obj else "UnknownError"
                
                logger.error(
                    "stream_queue_error",
                    error=error_message,
                    error_type=error_type,
                    thread_id=thread_id,
                )
                
                # Send error event to frontend immediately
                error_data = {
                    "type": EVENT_ERROR,
                    "error": error_message,
                    "error_type": error_type,
                    "thread_id": thread_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                
                # Break out of loop - error occurred, don't continue processing
                break
            elif item_type == QUEUE_EVENT:
                # Send event to client
                yield f"data: {json.dumps(item_data)}\n\n"
            elif item_type == QUEUE_CHUNK:
                # Process chunk - could be content chunk or state chunk
                chunk = item_data
                
                # Handle content chunks (from content stream thread)
                if isinstance(chunk, dict) and chunk.get("type") == EVENT_CONTENT_CHUNK:
                    # Send content chunk to frontend
                    yield f"data: {json.dumps(chunk)}\n\n"
                    
                    # Update final response reference with accumulated content
                    if "accumulated" in chunk:
                        final_response_ref[0] = chunk["accumulated"]
                    
                    logger.debug(
                        "content_chunk_sent_to_frontend",
                        chunk_length=len(chunk.get("content", "")),
                        accumulated_length=len(chunk.get("accumulated", "")),
                    )
                
                # Handle final content marker (from content stream thread)
                elif chunk.get("__final_content__"):
                    # Store final content for final response
                    if "content" in chunk:
                        final_response_ref[0] = chunk["content"]
                        logger.debug(
                            "final_content_stored",
                            content_length=len(chunk["content"]),
                        )
                
                # Handle legacy state chunks (for backward compatibility, though we shouldn't get these now)
                elif chunk.get("__final_state__"):
                    # Skip final state marker chunks (they're just for reference)
                    continue
                elif "messages" in chunk and chunk["messages"]:
                    # Legacy: Extract from state chunk (shouldn't happen with new architecture)
                    last_message = chunk["messages"][-1]
                    if hasattr(last_message, "content") and not isinstance(last_message, HumanMessage):
                        # This is the AI response
                        final_response_ref[0] = extract_message_content(last_message.content)
                        logger.debug(
                            "legacy_state_chunk_processed",
                            content_length=len(final_response_ref[0]) if final_response_ref[0] else 0,
                        )
        except queue.Empty:
            # No item yet, continue waiting
            # Re-check exit condition (stream_done might have been set while we were waiting)
            if stream_done.is_set() and event_queue.empty():
                break
            await asyncio.sleep(0.01)
            continue
        except Exception as e:
            # Error from stream thread
            raise

def _extract_final_response(config: dict[str, Any], thread_id: str) -> str | None:
    """Extract final response from graph state.
    
    Args:
        config: Graph configuration
        thread_id: Thread identifier
        
    Returns:
        Final response string or None
    """
    try:
        final_state = get_graph().get_state(config)
        if hasattr(final_state, "values") and "messages" in final_state.values:
            ai_message = extract_ai_message(final_state.values["messages"])
            return extract_message_content(ai_message.content)
    except Exception as e:
        logger.error("failed_to_get_final_state", error=str(e), thread_id=thread_id)
    return None


def _flush_langfuse_traces(
    langfuse_handler: CallbackHandler | None,
    centralized_metadata: dict[str, str],
) -> None:
    """Flush Langfuse traces after streaming completes.
    
    Args:
        langfuse_handler: Langfuse callback handler
        centralized_metadata: Centralized metadata dict
    """
    if langfuse_handler and settings.langfuse_enabled:
        try:
            from langfuse import get_client
            langfuse_client = get_client()
            environment = centralized_metadata["environment"]
            if environment == "prd":
                langfuse_client.shutdown()
            else:
                langfuse_client.flush()
        except Exception as e:
            logger.error(
                "langfuse_flush_failed",
                error=str(e),
                error_type=type(e).__name__,
                environment=centralized_metadata["environment"],
            )


async def _stream_chat_events(
    request: ChatRequest,
    user_id: str,
    thread_id: str,
    initial_state: AgentState,
    config: dict[str, Any],
    langfuse_handler: CallbackHandler | None,
    centralized_metadata: dict[str, str],
):
    """Stream chat execution events using LangGraph stream_events (sync version for PostgresSaver compatibility).
    
    Args:
        request: Chat request
        user_id: User identifier
        thread_id: Thread identifier
        initial_state: Initial agent state
        config: Graph configuration
        langfuse_handler: Langfuse callback handler
        centralized_metadata: Centralized metadata dict
        
    Yields:
        Server-Sent Event strings
    """
    final_response: str | None = None
    
    try:
        # Use stream (sync) instead of async methods because
        # PostgresSaver doesn't fully support async checkpoint operations (aget_tuple raises NotImplementedError)
        # Run sync stream in a background thread to avoid blocking
        event_queue: queue.Queue = queue.Queue()
        stream_done = threading.Event()
        
        # Create and start streaming threads (content + node tracking)
        stream_threads, stream_errors = _create_stream_thread(
            initial_state, config, thread_id, event_queue, stream_done
        )
        
        # Process events and chunks from queue
        final_response_ref: list[str | None] = [None]
        async for event_str in _process_stream_queue(event_queue, stream_done, final_response_ref, thread_id):
            yield event_str
        
        # Wait for all threads to complete (increased timeout for complex tool operations)
        for thread in stream_threads:
            thread.join(timeout=30.0)        
        # Check for errors from both threads
        content_error = stream_errors[0][0] if len(stream_errors) > 0 and stream_errors[0] else None
        node_error = stream_errors[1][0] if len(stream_errors) > 1 and stream_errors[1] else None
        
        # If there was a content error, we've already sent an error event to the frontend
        # Don't raise here - instead, send graph_end with empty response to signal completion
        if content_error:
            logger.error(
                "content_stream_error",
                error=str(content_error),
                error_type=type(content_error).__name__,
                thread_id=thread_id,
            )
            # Don't raise - we've already sent error event, now send graph_end to complete stream
        
        if node_error:
            # Node tracking errors are non-fatal, but log them
            logger.warning(
                "node_tracking_error",
                error=str(node_error),
                error_type=type(node_error).__name__,
                thread_id=thread_id,
            )
            # Don't raise - node tracking is for visualization only
        
        # Get final response - prefer from queue, then from final state extraction
        if final_response_ref[0]:
            final_response = final_response_ref[0]
        else:
            # Try to get final state
            final_response = _extract_final_response(config, thread_id)
        
        # If still no response, try one more time to get final state
        if not final_response:
            final_response = _extract_final_response(config, thread_id)
        
        # Always send graph_end event (even if response is empty, to signal completion)
        logger.debug(
            "graph_end_event",
            thread_id=thread_id,
            response_length=len(final_response) if final_response else 0,
            has_response=bool(final_response),
        )
        
        state_data = {
            "type": EVENT_GRAPH_END,
            "thread_id": thread_id,
            "response": final_response or "",
        }
        yield f"data: {json.dumps(state_data)}\n\n"        
        # Flush Langfuse traces after streaming completes
        _flush_langfuse_traces(langfuse_handler, centralized_metadata)
        
    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_str = str(e) if str(e) else ""
        error_message = error_str if error_str else f"{error_type}: An error occurred during streaming"
        
        # Log full exception details for debugging
        logger.exception(
            "streaming_error",
            error=error_message,
            error_type=error_type,
            error_repr=repr(e),
            thread_id=thread_id,
            exc_info=True,
        )
        
        error_data = {
            "type": EVENT_ERROR,
            "error": error_message,
            "error_type": error_type,
            "thread_id": thread_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_payload: dict = Depends(verify_google_token)
):
    """Chat endpoint that processes user messages through LangGraph with streaming support."""
    user_id = user_payload["sub"]
    
    # Use provided thread_id or generate one for state tracking
    thread_id = request.thread_id if request.thread_id else str(uuid.uuid4())
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=request.message)]
    }
    
    # Get Langfuse callback handler if enabled
    langfuse_handler = get_langfuse_handler()
    
    # Prepare config with callbacks, metadata, and thread_id
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id}
    }
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        logger.debug(
            "langfuse_callback_handler_added",
            handler_type=type(langfuse_handler).__name__,
            thread_id=thread_id,
        )
    
    # Add metadata for Langfuse tracing using centralized metadata
    centralized_metadata = get_metadata()
    metadata: dict[str, Any] = {
        "langfuse_user_id": user_id,
        **centralized_metadata,  # Includes environment, account, org, project
    }
    logger.debug(
        "langfuse_metadata_constructed",
        environment=centralized_metadata["environment"],
        account=centralized_metadata["account"],
        org=centralized_metadata["org"],
        project=centralized_metadata["project"],
        thread_id=thread_id,
    )
    
    config["metadata"] = metadata
    
    # Log start of execution
    logger.debug(
        "graph_execution_started",
        thread_id=thread_id,
        message_length=len(request.message),
    )
    
    # Return streaming response with Server-Sent Events
    return StreamingResponse(
        _stream_chat_events(
            request=request,
            user_id=user_id,
            thread_id=thread_id,
            initial_state=initial_state,
            config=config,
            langfuse_handler=langfuse_handler,
            centralized_metadata=centralized_metadata,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

