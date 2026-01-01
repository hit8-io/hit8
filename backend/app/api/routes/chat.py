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
from app.agents.opgroeien.graph import AgentState
from app.api.constants import (
    EVENT_GRAPH_END,
    EVENT_GRAPH_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_ERROR,
    NODE_GENERATE,
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


def _create_stream_thread(
    initial_state: AgentState,
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
) -> tuple[threading.Thread, list[Exception | None]]:
    """Create and start a thread for streaming graph execution.
    
    Args:
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        event_queue: Queue for events and chunks
        stream_done: Event to signal stream completion
        
    Returns:
        Tuple of (thread, list with single error slot)
    """
    stream_error: list[Exception | None] = [None]
    
    def run_stream():
        """Run sync stream in a thread and put state chunks in queue."""
        try:
            # Send graph start event
            event_queue.put((QUEUE_EVENT, {"type": EVENT_GRAPH_START, "thread_id": thread_id}))
            # Send node start event
            event_queue.put((QUEUE_EVENT, {"type": EVENT_NODE_START, "node": NODE_GENERATE, "thread_id": thread_id}))
            
            # Stream the graph execution (sync)
            for chunk in get_graph().stream(initial_state, config=config):
                event_queue.put((QUEUE_CHUNK, chunk))
            
            # Send node end event
            event_queue.put((QUEUE_EVENT, {"type": EVENT_NODE_END, "node": NODE_GENERATE, "thread_id": thread_id}))
        except Exception as e:
            stream_error[0] = e
            event_queue.put((QUEUE_ERROR, e))
        finally:
            stream_done.set()
    
    stream_thread = threading.Thread(target=run_stream, daemon=True)
    stream_thread.start()
    return stream_thread, stream_error


async def _process_stream_queue(
    event_queue: queue.Queue,
    stream_done: threading.Event,
    final_response_ref: list[str | None],
) -> AsyncIterator[str]:
    """Process events and chunks from the stream queue.
    
    Args:
        event_queue: Queue containing events and chunks
        stream_done: Event signaling stream completion
        final_response_ref: List to store extracted final response
        
    Yields:
        Server-Sent Event strings
    """
    while not stream_done.is_set() or not event_queue.empty():
        try:
            # Wait for event/chunk with timeout
            item = event_queue.get(timeout=0.1)
            item_type, item_data = item
            
            if item_type == QUEUE_ERROR:
                raise item_data
            elif item_type == QUEUE_EVENT:
                # Send event to client
                yield f"data: {json.dumps(item_data)}\n\n"
            elif item_type == QUEUE_CHUNK:
                # Process state chunk and extract response
                chunk = item_data
                if "messages" in chunk and chunk["messages"]:
                    # Get the last message (should be AI response)
                    last_message = chunk["messages"][-1]
                    if hasattr(last_message, "content") and not isinstance(last_message, HumanMessage):
                        # This is the AI response
                        final_response_ref[0] = extract_message_content(last_message.content)
        except queue.Empty:
            # No item yet, continue waiting
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
        
        # Create and start streaming thread
        stream_thread, stream_error = _create_stream_thread(
            initial_state, config, thread_id, event_queue, stream_done
        )
        
        # Process events and chunks from queue
        final_response_ref: list[str | None] = [None]
        async for event_str in _process_stream_queue(event_queue, stream_done, final_response_ref):
            yield event_str
        
        # Get extracted response if available
        if final_response_ref[0]:
            final_response = final_response_ref[0]
        
        # Wait for thread to complete
        stream_thread.join(timeout=5.0)
        
        # Check for errors
        if stream_error[0]:
            raise stream_error[0]
        
        # Get final state and send graph end event
        final_response = _extract_final_response(config, thread_id)
        if final_response:
            logger.debug(
                "graph_end_event",
                thread_id=thread_id,
                response_length=len(final_response),
            )
            
            # Send final state update
            state_data = {
                "type": EVENT_GRAPH_END,
                "thread_id": thread_id,
                "response": final_response,
            }
            yield f"data: {json.dumps(state_data)}\n\n"
        
        # Ensure we send the final response even if graph_end event wasn't caught
        if not final_response:
            logger.warning("graph_end_not_received", thread_id=thread_id)
            # Try to get the final state one more time
            final_response = _extract_final_response(config, thread_id)
            if final_response:
                logger.debug(
                    "graph_end_fallback",
                    thread_id=thread_id,
                    response_length=len(final_response),
                )
                
                state_data = {
                    "type": EVENT_GRAPH_END,
                    "thread_id": thread_id,
                    "response": final_response,
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
        **centralized_metadata,  # Includes environment, customer, project
    }
    logger.debug(
        "langfuse_metadata_constructed",
        environment=centralized_metadata["environment"],
        customer=centralized_metadata["customer"],
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

