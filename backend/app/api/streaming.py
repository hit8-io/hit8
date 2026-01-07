"""
Streaming functions for chat endpoint.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.messages import AIMessage, ToolMessage

from app.flows.opgroeien.poc.constants import NODE_AGENT, NODE_TOOLS
from app.flows.opgroeien.poc.chat.graph import AgentState
from app.api.constants import (
    EVENT_CONTENT_CHUNK,
    EVENT_ERROR,
    EVENT_GRAPH_START,
    EVENT_LLM_END,
    EVENT_LLM_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_STATE_UPDATE,
    EVENT_TOOL_END,
    EVENT_TOOL_START,
)

# Queue item types for streaming (only used in this module)
QUEUE_EVENT = "__event__"
QUEUE_CHUNK = "__chunk__"
QUEUE_ERROR = "__error__"
from app.api.graph_manager import get_graph
from app.api.streaming_utils import (
    extract_incremental_content,
    extract_state_update,
    get_final_content_from_state,
    get_final_state_data,
    truncate_preview,
)
from app.api.utils import extract_ai_message, extract_message_content
from app.config import settings

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler

logger = structlog.get_logger(__name__)


def stream(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
    stream_error: list[Exception | None],
) -> None:
    """Stream content, LLM/tool events, and node tracking using astream() and astream_events().
    
    Uses astream(stream_mode="messages") for content chunks and LLM/tool info (simpler),
    and astream_events() only for node execution tracking.
    """
    accumulated_content = ""
    last_ai_message_content = ""
    visited_nodes: list[str] = []
    current_node: str | None = None
    
    try:
        logger.info(
            "stream_started",
            thread_id=thread_id,
            initial_message_count=len(initial_state.get("messages", [])),
        )
        
        graph = get_graph()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Queues for messages and events
        messages_queue: asyncio.Queue = asyncio.Queue()
        events_queue: asyncio.Queue = asyncio.Queue()
        messages_done = threading.Event()
        events_done = threading.Event()
        async_error: Exception | None = None
        
        async def stream_messages():
            """Stream messages for content chunks and LLM/tool info."""
            nonlocal async_error
            try:
                async for msg in graph.astream(initial_state, config=config, stream_mode="messages"):
                    await messages_queue.put(msg)
            except Exception as e:
                async_error = e
            finally:
                messages_done.set()
        
        async def stream_events():
            """Stream events only for node tracking."""
            nonlocal async_error
            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    await events_queue.put(event)
            except Exception as e:
                if not async_error:  # Don't overwrite if messages stream already failed
                    async_error = e
            finally:
                events_done.set()
        
        # Start both streams in parallel
        messages_task = loop.create_task(stream_messages())
        events_task = loop.create_task(stream_events())
        
        try:
            # Process both queues until both are done
            while True:
                streams_done = messages_done.is_set() and events_done.is_set()
                queues_empty = messages_queue.empty() and events_queue.empty()
                
                if streams_done and queues_empty:
                    break
                
                # Run event loop briefly to process async tasks
                loop.run_until_complete(asyncio.sleep(0))
                
                # Process messages (content, LLM, tools)
                result = _process_messages_queue(
                    messages_queue, event_queue, thread_id,
                    accumulated_content, last_ai_message_content
                )
                if result:
                    accumulated_content, last_ai_message_content = result
                
                # Process events (node tracking)
                current_node, visited_nodes = _process_events_queue(
                    events_queue, event_queue, thread_id, current_node, visited_nodes
                )
            
            # Check for async errors
            if async_error:
                raise async_error
        finally:
            # Clean up
            for task in [messages_task, events_task]:
                if not task.done():
                    task.cancel()
                    try:
                        loop.run_until_complete(task)
                    except asyncio.CancelledError:
                        pass
            loop.close()
        
        # Finalize stream: send final state and content
        _finalize_stream(
            event_queue, thread_id, config,
            current_node, visited_nodes,
            accumulated_content, last_ai_message_content
        )
            
    except Exception as e:
        stream_error[0] = e
        event_queue.put((QUEUE_ERROR, e))
        logger.exception(
            "stream_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
            exc_info=True,
        )
    finally:
        logger.info("stream_finally", thread_id=thread_id)
        stream_done.set()


def _process_messages_queue(
    messages_queue: asyncio.Queue,
    event_queue: queue.Queue,
    thread_id: str,
    accumulated_content: str,
    last_ai_message_content: str,
) -> tuple[str, str] | None:
    """Process messages from the messages queue.
    
    Handles LLM events, tool events, and content chunks from message objects.
    
    Returns:
        Updated (accumulated_content, last_ai_message_content) if changed, None otherwise
    """
    while True:
        try:
            msg = messages_queue.get_nowait()
            
            # Handle AI messages (LLM events, tool calls, and content chunks)
            if isinstance(msg, AIMessage):
                content = extract_message_content(msg.content)
                
                # Extract LLM metadata from response_metadata
                if hasattr(msg, "response_metadata") and msg.response_metadata:
                    metadata = msg.response_metadata
                    if isinstance(metadata, dict):
                        model_name = (
                            metadata.get("model_name") or
                            metadata.get("model") or
                            "unknown"
                        )
                        token_usage = metadata.get("token_usage") or metadata.get("usage_metadata")
                        
                        event_data = {
                            "type": EVENT_LLM_END,
                            "model": model_name,
                            "input_preview": "",  # Not available from message alone
                            "output_preview": truncate_preview(content, 200),
                            "thread_id": thread_id,
                        }
                        if token_usage:
                            event_data["token_usage"] = token_usage
                        event_queue.put((QUEUE_EVENT, event_data))
                
                # Handle tool calls from AIMessage
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_name = getattr(tool_call, "name", "unknown")
                        tool_args = getattr(tool_call, "args", {})
                        
                        event_queue.put((QUEUE_EVENT, {
                            "type": EVENT_TOOL_START,
                            "tool_name": tool_name,
                            "args_preview": truncate_preview(json.dumps(tool_args), 200),
                            "thread_id": thread_id,
                        }))
                
                # Handle content chunks for AI messages
                if content != last_ai_message_content:
                    incremental, new_accumulated = extract_incremental_content(
                        content, last_ai_message_content, accumulated_content
                    )
                    if incremental:
                        event_queue.put((QUEUE_CHUNK, {
                            "type": EVENT_CONTENT_CHUNK,
                            "content": incremental,
                            "accumulated": new_accumulated,
                            "thread_id": thread_id,
                        }))
                        return new_accumulated, content
            
            # Handle tool results (ToolMessage)
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", "unknown")
                tool_result = extract_message_content(msg.content)
                
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_TOOL_END,
                    "tool_name": tool_name,
                    "args_preview": "",  # Not available from ToolMessage alone
                    "result_preview": truncate_preview(tool_result, 500),
                    "thread_id": thread_id,
                }))
                
        except asyncio.QueueEmpty:
            break
    return None


def _process_events_queue(
    events_queue: asyncio.Queue,
    event_queue: queue.Queue,
    thread_id: str,
    current_node: str | None,
    visited_nodes: list[str],
) -> tuple[str | None, list[str]]:
    """Process events from the events queue.
    
    Returns:
        Updated (current_node, visited_nodes)
    """
    while True:
        try:
            event = events_queue.get_nowait()
            if isinstance(event, dict):
                current_node, visited_nodes = _process_node_event(
                    event, event_queue, thread_id, current_node, visited_nodes
                )
        except asyncio.QueueEmpty:
            break
    return current_node, visited_nodes


def _finalize_stream(
    event_queue: queue.Queue,
    thread_id: str,
    config: dict[str, Any],
    current_node: str | None,
    visited_nodes: list[str],
    accumulated_content: str,
    last_ai_message_content: str,
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
        final_state = get_graph().get_state(config)
        
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


def _extract_llm_start_event(event: dict[str, Any], thread_id: str) -> dict[str, Any] | None:
    """Extract LLM start event data from astream_events() event.
    
    Returns:
        Event data dict or None if not an LLM start event
    """
    event_type = event.get("event", "")
    if event_type != "on_llm_start":
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
    
    return {
        "type": EVENT_LLM_START,
        "model": model_name,
        "input_preview": input_preview,
        "thread_id": thread_id,
    }


def _process_node_event(
    event: dict[str, Any],
    event_queue: queue.Queue,
    thread_id: str,
    current_node: str | None,
    visited_nodes: list[str],
) -> tuple[str | None, list[str]]:
    """Process events from astream_events() for node tracking.
    
    Returns:
        Tuple of (updated_current_node, updated_visited_nodes)
    """
    event_type = event.get("event", "")
    node_name = event.get("name", "")
    
    # Handle LLM start events (needed for frontend)
    llm_start_data = _extract_llm_start_event(event, thread_id)
    if llm_start_data:
        event_queue.put((QUEUE_EVENT, llm_start_data))
        return current_node, visited_nodes
    
    # Only track agent and tools nodes for chain events
    if node_name not in (NODE_AGENT, NODE_TOOLS):
        return current_node, visited_nodes
    
    # Handle chain start (node start)
    if event_type == "on_chain_start":
        if current_node != node_name:
            if current_node:
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_NODE_END,
                    "node": current_node,
                    "thread_id": thread_id
                }))
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
            event_queue.put((QUEUE_EVENT, {
                "type": EVENT_STATE_UPDATE,
                "next": state_data["next"],
                "message_count": state_data["message_count"],
                "thread_id": thread_id,
                "visited_nodes": visited_nodes.copy(),
            }))
    
    return current_node, visited_nodes


def create_stream_thread(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
) -> tuple[list[threading.Thread], list[Exception | None]]:
    """Create and start streaming thread using astream() and astream_events()."""
    event_queue.put((QUEUE_EVENT, {"type": EVENT_GRAPH_START, "thread_id": thread_id}))
    
    stream_error: list[Exception | None] = [None]
    stream_errors = [stream_error]
    
    stream_thread = threading.Thread(
        target=stream,
        args=(initial_state, config, thread_id, event_queue, stream_done, stream_error),
        daemon=True,
    )
    stream_thread.start()
    
    return [stream_thread], stream_errors


def _process_chunk(
    chunk: dict[str, Any], final_response_ref: list[str | None]
) -> str | None:
    """Process a chunk and update final response reference.
    
    Args:
        chunk: Chunk dictionary
        final_response_ref: Reference to store final response
        
    Returns:
        SSE string to yield, or None if chunk should be skipped
    """
    if isinstance(chunk, dict) and chunk.get("type") == EVENT_CONTENT_CHUNK:
        if "accumulated" in chunk:
            final_response_ref[0] = chunk["accumulated"]
        return f"data: {json.dumps(chunk)}\n\n"
    
    if chunk.get("__final_content__"):
        if "content" in chunk:
            final_response_ref[0] = chunk["content"]
        return None  # Skip final content marker
    
    if chunk.get("__final_state__"):
        return None  # Skip final state marker
    
    return None


async def process_stream_queue(
    event_queue: queue.Queue,
    stream_done: threading.Event,
    final_response_ref: list[str | None],
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    """Process events and chunks from the stream queue."""
    while True:
        if stream_done.is_set() and event_queue.empty():
            break
        
        try:
            item = event_queue.get(timeout=0.1)
            item_type, item_data = item
            
            if item_type == QUEUE_ERROR:
                error_obj = item_data
                error_message = str(error_obj) if error_obj else "Unknown error occurred"
                error_type = type(error_obj).__name__ if error_obj else "UnknownError"
                
                logger.error(
                    "stream_queue_error",
                    error=error_message,
                    error_type=error_type,
                    thread_id=thread_id,
                )
                
                error_data = {
                    "type": EVENT_ERROR,
                    "error": error_message,
                    "error_type": error_type,
                    "thread_id": thread_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                break
            
            if item_type == QUEUE_EVENT:
                yield f"data: {json.dumps(item_data)}\n\n"
                continue
            
            if item_type == QUEUE_CHUNK:
                sse_str = _process_chunk(item_data, final_response_ref)
                if sse_str:
                    yield sse_str
                continue
                
        except queue.Empty:
            if stream_done.is_set() and event_queue.empty():
                break
            await asyncio.sleep(0.01)
            continue
        except Exception as e:
            raise


def extract_final_response(config: dict[str, Any], thread_id: str) -> str | None:
    """Extract final response from graph state."""
    try:
        final_state = get_graph().get_state(config)
        if hasattr(final_state, "values") and "messages" in final_state.values:
            ai_message = extract_ai_message(final_state.values["messages"])
            return extract_message_content(ai_message.content)
    except Exception as e:
        logger.error("failed_to_get_final_state", error=str(e), thread_id=thread_id)
    return None


