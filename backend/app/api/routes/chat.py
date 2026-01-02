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

from app.agents.common import get_langfuse_handler
from app.agents.opgroeien.constants import NODE_AGENT, NODE_TOOLS
from app.agents.opgroeien.graph import AgentState
from app.api.constants import (
    EVENT_CONTENT_CHUNK,
    EVENT_GRAPH_END,
    EVENT_GRAPH_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
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
        # Check if stream_events method exists (may not be available on all graph types)
        graph = get_graph()
        if not hasattr(graph, "stream_events"):
            logger.warning(
                "node_tracking_not_available",
                thread_id=thread_id,
                graph_type=type(graph).__name__,
            )
            return
        
        for event in graph.stream_events(initial_state, config=config, version="v2"):
            if not isinstance(event, dict):
                continue
            
            # Extract event type and node name
            event_type = event.get("event", "")
            node_name = event.get("name", "")
            
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
    
    # Create and start node tracking thread
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

