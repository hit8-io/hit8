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

from app.flows.opgroeien.poc.constants import (
    NODE_AGENT,
    NODE_TOOLS,
    NODE_PROCEDURES_VECTOR_SEARCH,
    NODE_REGELGEVING_VECTOR_SEARCH,
)
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
    org: str,
    project: str,
) -> None:
    """Stream content, LLM/tool events, and node tracking using astream() and astream_events().
    
    Uses astream(stream_mode="messages") for content chunks and LLM/tool info (simpler),
    and astream_events() only for node execution tracking.
    """
    accumulated_content = ""
    last_ai_message_content = ""
    visited_nodes: list[str] = []
    current_node: str | None = None
    tool_call_id_to_name: dict[str, str] = {}  # Map tool_call_id to tool_name
    
    try:
        logger.info(
            "stream_started",
            thread_id=thread_id,
            initial_message_count=len(initial_state.get("messages", [])),
        )
        
        graph = get_graph(org, project)
        
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
                # Always update visited_nodes since _process_messages_queue may add individual tool nodes
                result = _process_messages_queue(
                    messages_queue, event_queue, thread_id,
                    accumulated_content, last_ai_message_content, visited_nodes, tool_call_id_to_name
                )
                if result:
                    accumulated_content, last_ai_message_content, visited_nodes, tool_call_id_to_name = result
                # Note: visited_nodes is modified in place, so changes persist even if result is None
                # But we now always return visited_nodes to ensure consistency
                
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
            accumulated_content, last_ai_message_content,
            org, project
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
    visited_nodes: list[str],
    tool_call_id_to_name: dict[str, str],
) -> tuple[str, str, list[str], dict[str, str]] | None:
    """Process messages from the messages queue.
    
    Handles LLM events, tool events, and content chunks from message objects.
    
    Returns:
        Updated (accumulated_content, last_ai_message_content, visited_nodes) if changed, None otherwise
    """
    while True:
        try:
            msg = messages_queue.get_nowait()
            
            # LangGraph's astream(stream_mode="messages") returns tuples (node_name, message)
            # Unpack if it's a tuple
            if isinstance(msg, tuple) and len(msg) == 2:
                node_name, msg = msg
            elif isinstance(msg, tuple):
                # Handle other tuple formats
                logger.warning(
                    "unexpected_tuple_format",
                    tuple_length=len(msg),
                    thread_id=thread_id,
                )
                continue
            
            # Handle dict messages (LangGraph may serialize messages as dicts)
            is_ai_message = False
            is_tool_message = False
            if isinstance(msg, dict):
                # Check if it's an AI message (has tool_calls or type indicates AIMessage)
                if msg.get("type") == "AIMessage" or "tool_calls" in msg:
                    is_ai_message = True
                # Check if it's a ToolMessage (has tool_call_id or type indicates ToolMessage)
                elif msg.get("type") == "ToolMessage" or "tool_call_id" in msg:
                    is_tool_message = True
                else:
                    # Skip if we can't identify the message type
                    continue
            elif isinstance(msg, AIMessage):
                is_ai_message = True
            elif isinstance(msg, ToolMessage):
                is_tool_message = True
            else:
                # Skip unknown message types
                continue
            
            # Handle AI messages (LLM events, tool calls, and content chunks)
            if is_ai_message:
                # Extract content from dict or message object
                if isinstance(msg, dict):
                    content = str(msg.get("content", ""))
                else:
                    content = extract_message_content(msg.content)
                
                # Extract LLM metadata from response_metadata
                if isinstance(msg, dict):
                    metadata = msg.get("response_metadata") or {}
                    if not metadata:
                        metadata = msg.get("usage_metadata") or {}
                elif hasattr(msg, "response_metadata") and msg.response_metadata:
                    metadata = msg.response_metadata
                else:
                    metadata = {}
                
                if metadata and isinstance(metadata, dict):
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
                tool_calls = msg.get("tool_calls", []) if isinstance(msg, dict) else (getattr(msg, "tool_calls", []) or [])
                if tool_calls:
                    # Map tool name to node name for graph view
                    tool_to_node_map = {
                        "procedures_vector_search": NODE_PROCEDURES_VECTOR_SEARCH,
                        "regelgeving_vector_search": NODE_REGELGEVING_VECTOR_SEARCH,
                    }
                    
                    for tool_call in tool_calls:
                        # Handle both dict and object tool calls
                        if isinstance(tool_call, dict):
                            tool_name = tool_call.get("name", "unknown")
                            tool_args = tool_call.get("args", {})
                            tool_call_id = tool_call.get("id", "")
                        else:
                            tool_name = getattr(tool_call, "name", "unknown")
                            tool_args = getattr(tool_call, "args", {})
                            tool_call_id = getattr(tool_call, "id", "")
                        
                        # Map tool_call_id to tool_name for later lookup in ToolMessages
                        if tool_call_id:
                            tool_call_id_to_name[tool_call_id] = tool_name
                        
                        tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
                        
                        # Track individual tool node in visited_nodes
                        if tool_node_name not in visited_nodes:
                            visited_nodes.append(tool_node_name)
                        
                        # Emit node_start for the tool
                        event_queue.put((QUEUE_EVENT, {
                            "type": EVENT_NODE_START,
                            "node": tool_node_name,
                            "thread_id": thread_id,
                        }))
                        
                        # Emit tool_start event
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
                        return new_accumulated, content, visited_nodes, tool_call_id_to_name
            
            # Handle tool results (ToolMessage)
            elif is_tool_message:
                # Extract tool_call_id from dict or message object
                if isinstance(msg, dict):
                    tool_call_id = msg.get("tool_call_id", "")
                    tool_result = str(msg.get("content", ""))
                else:
                    tool_call_id = getattr(msg, "tool_call_id", "")
                    tool_result = extract_message_content(msg.content)
                
                # Look up tool name from tool_call_id mapping
                tool_name = tool_call_id_to_name.get(tool_call_id, "unknown")
                
                # Map tool name to node name for graph view
                tool_to_node_map = {
                    "procedures_vector_search": NODE_PROCEDURES_VECTOR_SEARCH,
                    "regelgeving_vector_search": NODE_REGELGEVING_VECTOR_SEARCH,
                }
                tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
                
                # Track individual tool node in visited_nodes
                if tool_node_name not in visited_nodes:
                    visited_nodes.append(tool_node_name)
                
                # Emit node_start for the tool (if not already started)
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_NODE_START,
                    "node": tool_node_name,
                    "thread_id": thread_id,
                }))
                
                # Emit tool_end event
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_TOOL_END,
                    "tool_name": tool_name,
                    "args_preview": "",  # Not available from ToolMessage alone
                    "result_preview": truncate_preview(tool_result, 500),
                    "thread_id": thread_id,
                }))
                
                # Emit node_end for the tool
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_NODE_END,
                    "node": tool_node_name,
                    "thread_id": thread_id,
                }))
                
                # Send state update with individual tool nodes in visited_nodes
                event_queue.put((QUEUE_EVENT, {
                    "type": EVENT_STATE_UPDATE,
                    "next": [],
                    "message_count": 0,
                    "thread_id": thread_id,
                    "visited_nodes": visited_nodes.copy(),
                }))
                
        except asyncio.QueueEmpty:
            break
    # Return visited_nodes even if no content update, so individual tool nodes are preserved
    # Return the same accumulated_content and last_ai_message_content, but updated visited_nodes and tool_call_id_to_name
    return accumulated_content, last_ai_message_content, visited_nodes, tool_call_id_to_name


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
                event_type = event.get("event", "")
                # Process tool events separately to track individual tool nodes
                if event_type in ("on_tool_start", "on_tool_end"):
                    visited_nodes = _process_tool_event(
                        event, event_queue, thread_id, visited_nodes
                    )
                else:
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


def _process_tool_event(
    event: dict[str, Any],
    event_queue: queue.Queue,
    thread_id: str,
    visited_nodes: list[str],
) -> list[str]:
    """Process tool events from astream_events() to track individual tool nodes.
    
    Returns:
        Updated visited_nodes with individual tool nodes added
    """
    from app.api.streaming_utils import extract_tool_event_data
    from app.flows.opgroeien.poc.constants import (
        NODE_PROCEDURES_VECTOR_SEARCH,
        NODE_REGELGEVING_VECTOR_SEARCH,
    )
    
    event_type = event.get("event", "")
    tool_data = extract_tool_event_data(event, event_type)
    
    if not tool_data:
        return visited_nodes
    
    tool_name = tool_data.get("tool_name", "unknown")
    
    # Map tool name to node name for graph view
    tool_to_node_map = {
        "procedures_vector_search": NODE_PROCEDURES_VECTOR_SEARCH,
        "regelgeving_vector_search": NODE_REGELGEVING_VECTOR_SEARCH,
    }
    tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
    
    # Track individual tool node in visited_nodes
    if tool_node_name not in visited_nodes:
        visited_nodes.append(tool_node_name)
        
        # Emit node_start for the tool
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_NODE_START,
            "node": tool_node_name,
            "thread_id": thread_id,
        }))
        
        # Send state update with individual tool nodes
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_STATE_UPDATE,
            "next": [],
            "message_count": 0,
            "thread_id": thread_id,
            "visited_nodes": visited_nodes.copy(),
        }))
    
    # Emit tool_start or tool_end event for frontend
    if event_type == "on_tool_start":
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_TOOL_START,
            "tool_name": tool_name,
            "args_preview": tool_data.get("args_preview", ""),
            "thread_id": thread_id,
        }))
    elif event_type == "on_tool_end":
        # Emit node_end for the tool
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_NODE_END,
            "node": tool_node_name,
            "thread_id": thread_id,
        }))
        
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_TOOL_END,
            "tool_name": tool_name,
            "args_preview": tool_data.get("args_preview", ""),
            "result_preview": tool_data.get("result_preview", ""),
            "thread_id": thread_id,
        }))
        
        # Send state update with individual tool nodes
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_STATE_UPDATE,
            "next": [],
            "message_count": 0,
            "thread_id": thread_id,
            "visited_nodes": visited_nodes.copy(),
        }))
    
    return visited_nodes


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
        # Note: visited_nodes may already contain individual tool nodes from _process_messages_queue
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
                "visited_nodes": visited_nodes.copy(),  # Includes individual tool nodes
            }))
    
    return current_node, visited_nodes


def create_stream_thread(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
    org: str,
    project: str,
) -> tuple[list[threading.Thread], list[Exception | None]]:
    """Create and start streaming thread using astream() and astream_events()."""
    event_queue.put((QUEUE_EVENT, {"type": EVENT_GRAPH_START, "thread_id": thread_id}))
    
    stream_error: list[Exception | None] = [None]
    stream_errors = [stream_error]
    
    stream_thread = threading.Thread(
        target=stream,
        args=(initial_state, config, thread_id, event_queue, stream_done, stream_error, org, project),
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


def extract_final_response(config: dict[str, Any], thread_id: str, org: str, project: str) -> str | None:
    """Extract final response from graph state."""
    try:
        final_state = get_graph(org, project).get_state(config)
        if hasattr(final_state, "values") and "messages" in final_state.values:
            ai_message = extract_ai_message(final_state.values["messages"])
            return extract_message_content(ai_message.content)
    except Exception as e:
        logger.error("failed_to_get_final_state", error=str(e), thread_id=thread_id)
    return None


